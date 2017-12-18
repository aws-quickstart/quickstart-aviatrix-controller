import os, boto3
from urllib2 import Request, urlopen, URLError
from time import sleep
import urllib, ssl, json, logging
#Needed to load Aviatrix Python API.
from aviatrix import Aviatrix

#logging configuration
logger = logging.getLogger()
logger.setLevel(logging.INFO)


#Test deployhub Event JSON
# {
#     "action": "deployhub",
#     "vpcid_hub": "vpc-19d25d61",
#     "region_hub": "us-east-1",
#     "gwsize_hub": "t2.small",
#     "subnet_hub": "10.1.0.0/24"
# }

#Test deploygateway Event JSON
# {
#     "action": "deploygateway",
#     "subnet_spoke": "192.168.1.0/24",
#     "vpcid_spoke": "vpc-f940a381",
#     "region_spoke": "us-east-1",
#     "gwsize_spoke": "t2.micro",
#     "vpcid_hub": "vpc-b53cb1cd"
# }

#Test deployhagateway Event JSON
# {
# 	"Records": [{
# 		"Sns": {
# 			"Message": {
# 				"action": "deployhagateway",
#                 "vpcid_ha": "hub-vpc-31fc7349",
#                 "region_ha": "us-east-1",
#                 "subnet_ha": "10.1.1.0/24"
# 			}
# 		}
# 	}]
# }


#Testing Data:
# Deploying a t2.micro takes ~3 minutes
# Deploying a m4.xlarge takes ~3 minutes 30 seconds
#

#Test deletegateway Event JSON
# {
#     "action": "deletegateway",
#     "region_spoke": "us-east-1",
#     "vpcid_hub": "vpc-b53cb1cd",
#     "vpcid_spoke": "vpc-f940a381"
# }

#Testing Data:
# Destroying a t2.micro takes ~1 Min 30 seconds

def tag_spoke(region_spoke,vpcid_spoke,tag):
    ec2=boto3.client('ec2',region_name=region_spoke)
    ec2.create_tags(Resources = [ vpcid_spoke ], Tags = [ { 'Key': 'aviatrix-spoke', 'Value': tag } ])

def find_other_spokes(vpc_pairs):
    ec2=boto3.client('ec2',region_name='us-east-1')
    regions=ec2.describe_regions()
    if vpc_pairs:
        existing_spokes=[]
        for vpc_name in vpc_pairs['pair_list']:
            vpc_name_temp = {}
            vpc_name_temp['vpc_name'] = vpc_name['vpc_name2']
            for region in regions['Regions']:
                region_id=region['RegionName']
                ec2=boto3.client('ec2',region_name=region_id)
                vpc_info=ec2.describe_vpcs(Filters=[
                    { 'Name': 'vpc-id', 'Values':[ vpc_name['vpc_name2'][6:] ]}
                    ])
                if vpc_info['Vpcs']:
                    vpc_name_temp['subnet'] = vpc_info['Vpcs'][0]['CidrBlock']
                    existing_spokes.append(vpc_name_temp)
    return existing_spokes

def test_find_other_spokes():
    test_vpc_pairs = {
                        "pair_list": [
                            {
                                "vpc_name2": "spoke-vpc-7a169913",
                                "vpc_name1": "hub-vpc-7c246404",
                                "peering_link": ""
                            }
                        ]
                    }
    assert find_other_spokes(test_vpc_pairs) == [{'subnet': '172.31.0.0/16', 'vpc_name': 'spoke-vpc-7a169913'}]

def handler(event, context):
    #Read environment Variables
    controller_ip = os.environ.get("Controller_IP")
    username = os.environ.get("Username")
    password = os.environ.get("Password")
    queue_url = os.environ.get("GatewayQueueURL")
    gatewaytopic = event['Records'][0]['EventSubscriptionArn'][:55]
    # Receive message from SQS queue
    #body=read_queue(queue_url)
    logger.info('Received Message: %s', event)
    body=json.loads(event['Records'][0]['Sns']['Message'])
    logger.info('Received Message: %s', body)
    #Case Deploy Hub
    if body['action'] == 'deployhub':
        #Variables
        vpcid_hub = body['vpcid_hub']
        region_hub = body['region_hub']
        gwsize_hub = body['gwsize_hub']
        subnet_hub = body['subnet_hub']
        subnet_hubHA= body['subnet_hubHA']
        #Processing
        try:
            #Open connection to controller
            controller = Aviatrix(controller_ip)
            controller.login(username,password)
            #Hub Gateway Creation
            logger.info('Creating Gateway: hub-%s', vpcid_hub)
            controller.create_gateway("AWSAccount",
                                      "1",
                                      "hub-" + vpcid_hub,
                                      vpcid_hub,
                                      region_hub,
                                      gwsize_hub,
                                      subnet_hub)
            #Send message to start HA gateway Deployment
            message = {}
            message['action'] = 'deploygatewayha'
            message['vpcid_ha'] = 'hub-' + vpcid_hub
            message['region_ha'] = region_hub
            message['subnet_ha'] = subnet_hubHA
            message['subnet_name'] = "Aviatrix VPC-Public Subnet HA"
            #Add New Gateway to SNS
            sns = boto3.client('sns')
            sns.publish(
                TopicArn=gatewaytopic,
                Subject='New Hub HA Gateway',
                Message=json.dumps(message)
            )
            logger.info('Done with Hub Gateway Deployment')

            return {
                'Status' : 'SUCCESS'
            }
        except URLError, e:
            logger.info('Failed request. Error: %s', controller.results)
            return {
                'Status' : 'FAILURE',
                'Error' : controller.results
            }
    #Case Deploy Gateway HA
    elif body['action'] == 'deploygatewayha':
        #Variables for HA GW
        vpcid_ha = body['vpcid_ha']
        region_ha = body['region_ha']
        subnet_ha = body['subnet_ha']
        subnet_name = body['subnet_name']
        specific_subnet = subnet_ha + "~~" + region_ha + "~~" + subnet_name
        #Processing
        logger.info('Processing HA Gateway %s.', vpcid_ha)
        #Open connection to controller
        controller = Aviatrix(controller_ip)
        controller.login(username,password)
        #HA Gateway Creation
        logger.info('Creating HA Gateway: %s', vpcid_ha)
        controller.enable_vpc_ha(vpcid_ha,specific_subnet)
        logger.info('Created HA Gateway: %s', vpcid_ha)
        logger.info('Done with HA Gateway Deployment')
    #Case Deploy Gateway
    elif body['action'] == 'deploygateway':
        #Variables
        subnet_spoke = body['subnet_spoke']
        subnet_spoke_ha = body['subnet_spoke_ha']
        subnet_spoke_name = body['subnet_spoke_name']
        vpcid_spoke = body['vpcid_spoke']
        region_spoke = body['region_spoke']
        gwsize_spoke = body['gwsize_spoke']
        vpcid_hub = body['vpcid_hub']
        #Processing
        logger.info('Processing VPC %s. Updating tag:aviatrix-spoke to processing', vpcid_spoke)
        tag_spoke(region_spoke,vpcid_spoke,'processing')
        try:
            #Open connection to controller
            controller = Aviatrix(controller_ip)
            controller.login(username,password)
            #get the list of existing Spokes
            controller.list_peers_vpc_pairs()
            found_pairs = controller.results
            #Spoke Gateway Creation
            logger.info('Creating Gateway: spoke-%s', vpcid_spoke)
            controller.create_gateway("AWSAccount",
                                      "1",
                                      "spoke-"+vpcid_spoke,
                                      vpcid_spoke,
                                      region_spoke,
                                      gwsize_spoke,
                                      subnet_spoke)
            logger.info('Creating HA Gateway: spoke-%s', vpcid_spoke)
            #Send message to start HA gateway Deployment
            message = {}
            message['action'] = 'deploygatewayha'
            message['vpcid_ha'] = 'spoke-' + vpcid_spoke
            message['region_ha'] = region_spoke
            message['subnet_ha'] = subnet_spoke_ha
            message['subnet_name'] = subnet_spoke_name
            #Add New Gateway to SNS
            sns = boto3.client('sns')
            sns.publish(
                TopicArn=gatewaytopic,
                Subject='New Hub HA Gateway',
                Message=json.dumps(message)
            )
            #Peering Hub/Spoke
            logger.info('Peering: hub-%s --> spoke-%s' % (vpcid_hub, vpcid_spoke))
            controller.peering("hub-"+vpcid_hub, "spoke-"+vpcid_spoke)
            #Creating the transitive connections
            existing_spokes = find_other_spokes(found_pairs)
            logger.info('Creating Transitive routes, Data: %s' % existing_spokes)
            if existing_spokes:
                for existing_spoke in existing_spokes:
                    controller.extended_vpc_peer('add','spoke-'+vpcid_spoke,'hub-'+vpcid_hub,existing_spoke['subnet'])
                    controller.extended_vpc_peer('add',existing_spoke['vpc_name'],'hub-'+vpcid_hub,subnet_spoke)
            logger.info('Finished creating Transitive routes')
            #if len(existing_spokes) != 0:
                #Create transitive routes for each spoke
                #for spoke in existing_spokes:
                    #controller.extended_vpc_peer(Args)

            logger.info('Done Peering %s. Updating tag:aviatrix-spoke to peered', vpcid_spoke)
            tag_spoke(region_spoke,vpcid_spoke,'peered')
            return {
            'Status' : 'SUCCESS'
            }
        except URLError, e:
            logger.info('Failed request. Error: %s', controller.results)
            return {
                'Status' : 'FAILURE',
                'Error' : controller.results
            }
    #Case Delete Gateway
    elif body['action'] == 'deletegateway':
        #Variables
        region_spoke = body['region_spoke']
        vpcid_hub = body['vpcid_hub']
        vpcid_spoke = body['vpcid_spoke']
        #Processing
        logger.info('Processing unpeer of VPC %s. Updating tag:aviatrix-spoke to processing', vpcid_spoke)
        tag_spoke(region_spoke,vpcid_spoke,'processing')

        try:
            #Open connection to controller
            controller = Aviatrix(controller_ip)
            controller.login(username,password)
            #Unpeering
            logger.info('UnPeering: hub-%s --> spoke-%s' % (vpcid_hub, vpcid_spoke))
            controller.unpeering("hub-"+vpcid_hub, "spoke-"+vpcid_spoke)
            #get the list of existing Spokes
            controller.list_peers_vpc_pairs()
            existing_spokes=[]
            for peers in controller.results['pair_list']:
                existing_spokes.append(peers['vpc_name2'])
            #Delete Transitive routers

            #Spoke Gateway Delete
            logger.info('Deleting Gateway: spoke-%s', vpcid_spoke)
            controller.delete_gateway("1", "spoke-"+vpcid_spoke)

            logger.info('Done unPeering %s. Updating tag:aviatrix-spoke to unpeered', vpcid_spoke)
            tag_spoke(region_spoke,vpcid_spoke,'unpeering')
            return {
                'Status' : 'SUCCESS'
            }
        except URLError, e:
            logger.info('Failed request. Error: %s', controller.results)
            return {
                'Status' : 'FAILURE',
                'Error' : controller.results
            }
