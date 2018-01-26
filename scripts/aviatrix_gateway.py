import os, sys, boto3, urllib, ssl, json, logging
from urllib.request import urlopen, URLError
from time import sleep
#Needed to load Aviatrix Python API.
from aviatrix3 import Aviatrix
import cfnresponse

#logging configuration
logger = logging.getLogger()
logger.setLevel(logging.INFO)

#Read environment Variables
controller_ip = os.environ.get("Controller_IP")
username = os.environ.get("Username")
password = os.environ.get("Password")
queue_url = os.environ.get("GatewayQueueURL")
spoketag = os.environ.get("SpokeTag")
OtherAccountRoleApp = os.environ.get("OtherAccountRoleApp")
gatewaytopic = ""

class original_context_class():
    def __init__(self,original_context):
        self.log_stream_name=original_context

def tag_spoke(ec2,region_spoke,vpcid_spoke,spoketag, tag):
    ec2.create_tags(Resources = [ vpcid_spoke ], Tags = [ { 'Key': spoketag, 'Value': tag } ])

def find_other_spokes(vpc_pairs,other_credentials=""):
    ec2 = boto3.client('ec2',region_name='us-east-1')
    regions=ec2.describe_regions()
    existing_spokes=[]
    if vpc_pairs:
        for region in regions['Regions']:
            region_id=region['RegionName']
            #Find spokes in primary account
            ec2=create_aws_session(region_id)
            for vpc_name in vpc_pairs['pair_list']:
                vpc_name_temp = {}
                vpc_name_temp['vpc_name'] = vpc_name['vpc_name2']
                vpc_info=ec2.describe_vpcs(Filters=[
                    { 'Name': 'vpc-id', 'Values':[ vpc_name['vpc_name2'][6:] ]}
                    ])
                if vpc_info['Vpcs']:
                    vpc_name_temp['subnet'] = vpc_info['Vpcs'][0]['CidrBlock']
                    existing_spokes.append(vpc_name_temp)
            #Find Spokes in Secondary account if otheraccount=TRUE
            if other_credentials != "":
                ec2=create_aws_session(region_id,other_credentials)
                for vpc_name in vpc_pairs['pair_list']:
                    vpc_name_temp = {}
                    vpc_name_temp['vpc_name'] = vpc_name['vpc_name2']
                    vpc_info=ec2.describe_vpcs(Filters=[
                        { 'Name': 'vpc-id', 'Values':[ vpc_name['vpc_name2'][6:] ]}
                        ])
                    if vpc_info['Vpcs']:
                        vpc_name_temp['subnet'] = vpc_info['Vpcs'][0]['CidrBlock']
                        existing_spokes.append(vpc_name_temp)
    return existing_spokes

def create_aws_session(region_id,other_credentials=""):
    if other_credentials != "":
        ec2=boto3.client('ec2',
                         region_name=region_id,
                         aws_access_key_id=other_credentials['Credentials']['AccessKeyId'],
                         aws_secret_access_key=other_credentials['Credentials']['SecretAccessKey'],
                         aws_session_token=other_credentials['Credentials']['SessionToken'] )

    else:
        ec2=boto3.client('ec2',region_name=region_id)
    return ec2

def get_aws_session(body,region_spoke):
    primary_account = body['primary_account']
    try:
        otheraccount = body['otheraccount']
        if primary_account:
            awsaccount = "AWSAccount"
            other_credentials = ""
        else:
            awsaccount = "AWSOtherAccount"
            other_credentials = get_credentials(OtherAccountRoleApp)
        region_id=region_spoke
    except KeyError:
        otheraccount = False
        awsaccount = "AWSAccount"
        other_credentials=""
        region_id=region_spoke

    ec2=create_aws_session(region_id,other_credentials)
    return { 'ec2': ec2,
             'awsaccount': awsaccount,
             'otheraccount': otheraccount,
             'primary_account': primary_account
    }

def get_credentials(rolearn):
    session = boto3.session.Session()
    client = session.client('sts')
    assume_role_response = client.assume_role(RoleArn=rolearn,
                                              RoleSessionName="aviatrix_poller" )
    return assume_role_response

def deploy_hub(controller,body,gatewaytopic):
    #Variables
    vpcid_hub = body['vpcid_hub']
    region_hub = body['region_hub']
    gwsize_hub = body['gwsize_hub']
    subnet_hub = body['subnet_hub']
    subnet_hubHA= body['subnet_hubHA']
    original_event = body['original_event']
    original_context = body['original_context']
    #Processing
    try:
        #Hub Gateway Creation
        logger.info('Creating Gateway: hub-%s', vpcid_hub)
        controller.create_gateway("AWSAccount",
                                  "1",
                                  "hub-" + vpcid_hub,
                                  vpcid_hub,
                                  region_hub,
                                  gwsize_hub,
                                  subnet_hub)
        logger.info('Done with Hub Gateway Deployment')
        #Send message to start HA gateway Deployment
        message = {}
        message['action'] = 'deployhubha'
        message['vpcid_ha'] = 'hub-' + vpcid_hub
        message['region_ha'] = region_hub
        message['subnet_ha'] = subnet_hubHA
        message['subnet_name'] = "Aviatrix VPC-Public Subnet HA"
        message['original_event'] = original_event
        message['original_context'] = original_context
        #Add New Gateway to SNS
        logger.info('Sending message to create Hub HA GW')
        logger.info('Message sent: %s: ' % json.dumps(message))
        sns = boto3.client('sns')
        logger.info("Temp: %s" % gatewaytopic)
        sns.publish(
            TopicArn=gatewaytopic,
            Subject='New Hub HA Gateway',
            Message=json.dumps(message)
        )
        return {
            'Status' : 'SUCCESS'
        }
    except URLError:
        logger.info('Failed request. Error: %s', controller.results)
        responseData = {
            "PhysicalResourceId": "arn:aws:fake:myID",
            "Cause" : controller.results
        }
        original_event=eval(original_event)
        original_context=original_context_class(original_context)
        cfnresponse.send(original_event, original_context, cfnresponse.FAILURE, responseData)
        sys.exit(1)

def deploy_hub_ha(controller,body):
    #Variables for HA GW
    vpcid_ha = body['vpcid_ha']
    region_ha = body['region_ha']
    subnet_ha = body['subnet_ha']
    subnet_name = body['subnet_name']
    specific_subnet = subnet_ha + "~~" + region_ha + "~~" + subnet_name
    original_event = body['original_event']
    original_context = body['original_context']
    try:
        #Processing
        logger.info('Processing HA Gateway %s.', vpcid_ha)
        #HA Gateway Creation
        logger.info('Creating HA Gateway: %s', vpcid_ha)
        controller.enable_vpc_ha(vpcid_ha,specific_subnet)
        logger.info('Created HA Gateway: %s', vpcid_ha)
        sleep(10)
        logger.info('Done with HA Hub Gateway Deployment')
        #responseData
        logger.info('Sending Message for Cloudformation Custom Resource: CREATE_COMPLETE')
        responseData = {
            "PhysicalResourceId": "arn:aws:fake:myID"
        }
        original_event=eval(original_event)
        original_context=original_context_class(original_context)
        cfnresponse.send(original_event, original_context, cfnresponse.SUCCESS, responseData)
    except URLError:
        logger.info('Failed request. Error: %s', controller.results)
        responseData = {
            "PhysicalResourceId": "arn:aws:fake:myID",
            "Cause" : controller.results
        }
        original_event=eval(original_event)
        original_context=original_context_class(original_context)
        cfnresponse.send(original_event, original_context, cfnresponse.FAILURE, responseData)
        sys.exit(1)

def deploy_gw (controller,body,gatewaytopic):
    #Variables
    subnet_spoke = body['subnet_spoke']
    subnet_spoke_ha = body['subnet_spoke_ha']
    subnet_spoke_name = body['subnet_spoke_name']
    vpcid_spoke = body['vpcid_spoke']
    region_spoke = body['region_spoke']
    gwsize_spoke = body['gwsize_spoke']
    vpcid_hub = body['vpcid_hub']
    vpc_cidr_spoke = body['vpc_cidr_spoke']
    #Get the right account
    result= get_aws_session(body,region_spoke)
    ec2=result['ec2']
    awsaccount=result['awsaccount']
    primary_account = result['primary_account']
    #Processing
    logger.info('Processing VPC %s. Updating tag:%s to processing' % (vpcid_spoke, spoketag))
    tag_spoke(ec2,region_spoke,vpcid_spoke,spoketag,'processing')
    try:
        #Spoke Gateway Creation
        logger.info('Creating Gateway: spoke-%s', vpcid_spoke)
        controller.create_gateway(awsaccount,
                                  "1",
                                  "spoke-"+vpcid_spoke,
                                  vpcid_spoke,
                                  region_spoke,
                                  gwsize_spoke,
                                  subnet_spoke)
        sleep(20)
        logger.info('Created Gateway: spoke-%s', vpcid_spoke)
        #Send message to start HA gateway Deployment
        message = {}
        message['action'] = 'deploygatewayha'
        message['vpcid_ha'] = 'spoke-' + vpcid_spoke
        message['region_ha'] = region_spoke
        message['subnet_ha'] = subnet_spoke_ha
        message['subnet_name'] = subnet_spoke_name
        message['vpcid_spoke'] = vpcid_spoke
        message['vpcid_hub'] = vpcid_hub
        message['vpc_cidr_spoke'] = vpc_cidr_spoke
        message['primary_account'] = primary_account
        if awsaccount == 'AWSOtherAccount':
            message['otheraccount'] = True
        #Add New Gateway to SNS
        sns = boto3.client('sns')
        sns.publish(
            TopicArn=gatewaytopic,
            Subject='New Hub HA Gateway',
            Message=json.dumps(message)
        )
        return {
            'Status' : 'SUCCESS'
        }
    except URLError:
        logger.info('Failed request. Error: %s', controller.results)
        return {
            'Status' : 'FAILURE',
            'Error' : controller.results
        }

def deploy_gw_ha(controller,body,gatewaytopic):
    #Variables for HA GW
    vpcid_ha = body['vpcid_ha']
    region_ha = body['region_ha']
    subnet_ha = body['subnet_ha']
    subnet_name = body['subnet_name']
    vpcid_spoke = body['vpcid_spoke']
    vpcid_hub = body['vpcid_hub']
    vpc_cidr_spoke = body['vpc_cidr_spoke']
    specific_subnet = subnet_ha + "~~" + region_ha + "~~" + subnet_name
    #Get the right account
    result= get_aws_session(body,vpcid_spoke)
    ec2=result['ec2']
    awsaccount=result['awsaccount']
    primary_account = result['primary_account']
    logger.info('AWS Account: %s' % awsaccount)
    #Processing
    logger.info('Processing HA Gateway %s.', vpcid_ha)
    #HA Gateway Creation
    logger.info('Creating HA Gateway: %s', vpcid_ha)
    try:
        controller.enable_vpc_ha(vpcid_ha,specific_subnet)
        logger.info('Created HA Gateway: %s', vpcid_ha)
        sleep(10)
        #Call to create the peering And routing
        message = {}
        message['action'] = 'create_peering'
        message['vpcid_ha'] = 'spoke-' + vpcid_spoke
        message['region_spoke'] = region_ha
        message['vpcid_spoke'] = vpcid_spoke
        message['vpcid_hub'] = vpcid_hub
        message['vpc_cidr_spoke'] = vpc_cidr_spoke
        message['primary_account'] = primary_account
        if awsaccount == 'AWSOtherAccount':
            message['otheraccount'] = True
        #Add New Gateway to SNS
        sns = boto3.client('sns')
        sns.publish(
            TopicArn=gatewaytopic,
            Subject='Create Peering and Routing for new GW',
            Message=json.dumps(message)
        )
        logger.info('Done with HA Gateway Deployment')
        return {
            'Status' : 'SUCCESS'
        }
    except URLError:
        logger.info('Failed request. Error: %s', controller.results)
        return {
            'Status' : 'FAILURE',
            'Error' : controller.results
        }

def create_peering(controller,body):
    #Variables
    vpcid_spoke = body['vpcid_spoke']
    region_spoke = body['region_spoke']
    vpcid_hub = body['vpcid_hub']
    vpc_cidr_spoke = body['vpc_cidr_spoke']
    #Get the right account
    result= get_aws_session(body,region_spoke)
    ec2 = result['ec2']
    awsaccount = result['awsaccount']
    otheraccount = result['otheraccount']
    logger.info('AWS Account: %s' % awsaccount)
    try:
        #Peering Hub/Spoke
        logger.info('Peering: hub-%s --> spoke-%s' % (vpcid_hub, vpcid_spoke))
        controller.peering("hub-"+vpcid_hub, "spoke-"+vpcid_spoke)
        #get the list of existing Spokes
        controller.list_peers_vpc_pairs()
        found_pairs = controller.results
        if OtherAccountRoleApp:
            other_credentials = get_credentials(OtherAccountRoleApp)
            existing_spokes = find_other_spokes(found_pairs,other_credentials)
        else:
            existing_spokes = find_other_spokes(found_pairs)
        #Creating the transitive connections
        logger.info('Creating Transitive routes, Data: %s' % existing_spokes)
        if existing_spokes:
            for existing_spoke in existing_spokes:
                if existing_spoke['vpc_name'] != 'spoke-' + vpcid_spoke:
                    controller.add_extended_vpc_peer('spoke-' + vpcid_spoke, 'hub-' + vpcid_hub, existing_spoke['subnet'])
                    controller.add_extended_vpc_peer(existing_spoke['vpc_name'],'hub-' + vpcid_hub, vpc_cidr_spoke)
        logger.info('Finished creating Transitive routes')

        logger.info('Done Peering %s. Updating tag:%s to peered' %  (vpcid_spoke, spoketag))
        #reconnect to right Account:
        result = get_aws_session(body,region_spoke)
        ec2 = result['ec2']
        awsaccount = result['awsaccount']
        tag_spoke(ec2,region_spoke,vpcid_spoke,spoketag,'peered')
        return {
        'Status' : 'SUCCESS'
        }
    except URLError:
        logger.info('Failed request. Error: %s', controller.results)
        return {
            'Status' : 'FAILURE',
            'Error' : controller.results
        }

def delete_gw(controller,body):
    #Variables
    region_spoke = body['region_spoke']
    vpcid_hub = body['vpcid_hub']
    vpcid_spoke = body['vpcid_spoke']
    subnet_spoke = body['subnet_spoke']
    result = get_aws_session(body,region_spoke)
    ec2 = result['ec2']
    awsaccount = result['awsaccount']
    otheraccount = result['otheraccount']
    #Processing
    logger.info('Processing unpeer of VPC %s. Updating tag:%s to processing' %  (vpcid_spoke,spoketag))
    tag_spoke(ec2,region_spoke,vpcid_spoke,spoketag,'processing')
    try:
        #get the list of existing Spokes
        controller.list_peers_vpc_pairs()
        found_pairs = controller.results
        if OtherAccountRoleApp:
            other_credentials = get_credentials(OtherAccountRoleApp)
            existing_spokes = find_other_spokes(found_pairs,other_credentials)
        else:
            existing_spokes = find_other_spokes(found_pairs)
        #Delete Transitive routes
        if existing_spokes:
            for existing_spoke in existing_spokes:
                if existing_spoke['vpc_name'] != 'spoke-' + vpcid_spoke:
                    controller.delete_extended_vpc_peer('spoke-' + vpcid_spoke, 'hub-' + vpcid_hub, existing_spoke['subnet'])
                    controller.delete_extended_vpc_peer(existing_spoke['vpc_name'],'hub-' + vpcid_hub, subnet_spoke)
        #Reconnect with right account:
        result = get_aws_session(body,region_spoke)
        ec2 = result['ec2']
        awsaccount = result['awsaccount']
        #Unpeering
        logger.info('UnPeering: hub-%s --> spoke-%s' % (vpcid_hub, vpcid_spoke))
        tag_spoke(ec2,region_spoke,vpcid_spoke,spoketag,'unpeering')
        controller.unpeering("hub-"+vpcid_hub, "spoke-"+vpcid_spoke)
        #Spoke Gateway Delete
        logger.info('Deleting Gateway: spoke-%s', vpcid_spoke)
        controller.delete_gateway("1", "spoke-"+vpcid_spoke)
        logger.info('Done unPeering %s. Updating tag:%s to unpeered' % (vpcid_spoke,spoketag))
        tag_spoke(ec2,region_spoke,vpcid_spoke,spoketag,'unpeered')
        return {
            'Status' : 'SUCCESS'
        }
    except URLError:
        logger.info('Failed request. Error: %s', controller.results)
        return {
            'Status' : 'FAILURE',
            'Error' : controller.results
        }

def handler(event, context):
    #Grab GWtopic from SNS
    gatewaytopic = event['Records'][0]['EventSubscriptionArn'][:-37]
    # Receive message from SQS queue
    #body=read_queue(queue_url)
    logger.info('Received Message: %s', event)
    body=json.loads(event['Records'][0]['Sns']['Message'])
    logger.info('Received Message: %s', body)
    try:
        #Open connection to controller
        controller = Aviatrix(controller_ip)
        controller.login(username,password)
        #Case Deploy Hub
        if body['action'] == 'deployhub':
            response = deploy_hub(controller,body,gatewaytopic)
        #Case Deploy Hub HA
        elif body['action'] == 'deployhubha':
            response = deploy_hub_ha(controller,body)
        #Case Deploy Gateway
        elif body['action'] == 'deploygateway':
            response = deploy_gw(controller,body,gatewaytopic)
        #Case Deploy Gateway HA
        elif body['action'] == 'deploygatewayha':
            response = deploy_gw_ha(controller,body,gatewaytopic)
        #Case Deploy peering
        elif body['action'] == 'create_peering':
            response = create_peering(controller,body)
        #Case Delete Gateway
        elif body['action'] == 'deletegateway':
            response = delete_gw(controller,body)
    except URLError:
        logger.info('Failed request. Error: %s', controller.results)
        return {
            'Status' : 'FAILURE',
            'Error' : controller.results
        }
