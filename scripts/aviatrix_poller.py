from __future__ import print_function
import os, boto3, json, logging

lambda_client = boto3.client('lambda')

#logging configuration
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def find_subnets(region_id,vpc_id):
    ec2=boto3.client('ec2',region_name=region_id)
    subnets_with_igw=ec2.describe_route_tables(Filters=[
        { 'Name': 'vpc-id', 'Values':[ vpc_id ]},
        { 'Name': 'route.gateway-id', 'Values': [ 'igw-*' ] }
    ])
    subnetids=[]
    for association in subnets_with_igw['RouteTables'][0]['Associations']:
      if association['Main'] == False:
          subnet_temp = {}
          subnet_temp['SubnetId'] = association['SubnetId']
          subnetids.append(subnet_temp)
    for subnet in subnetids:
      subnet_info=ec2.describe_subnets(Filters=[
      { 'Name': 'subnet-id', 'Values': [ subnet['SubnetId'] ] }
      ])
      subnet['CidrBlock'] = subnet_info['Subnets'][0]['CidrBlock']
      for tag in subnet_info['Subnets'][0]['Tags']:
          if tag['Key'] == 'Name':
              subnet['Name'] = tag['Value']
    return subnetids

def handler(event, context):
    #Read environment Variables
    gatewayqueue = os.environ.get("GatewayQueue")
    vpcid_hub = os.environ.get("HubVPC")
    gatewaytopic = os.environ.get("GatewayTopic")
    ec2=boto3.client('ec2',region_name='us-east-1')
    regions=ec2.describe_regions()
    for region in regions['Regions']:
        region_id=region['RegionName']
        logger.info('Checking region: %s',region_id)
        ec2=boto3.client('ec2',region_name=region_id)

        #Find VPCs with Tag:aviatrix-spoke = true
        #Create Gateway for it and Peer, when done change the Tag:aviatrix-spoke = peered
        vpcs=ec2.describe_vpcs(Filters=[
            { 'Name': 'state', 'Values': [ 'available' ] },
            { 'Name': 'tag:aviatrix-spoke', 'Values': [ 'true', 'True', 'TRUE', 'test' ] }
        ])
        for vpc_peering in vpcs['Vpcs']:
            message = {}
            message['action'] = 'deploygateway'
            message['vpcid_spoke'] = vpc_peering['VpcId']
            message['region_spoke'] = region_id
            message['gwsize_spoke'] = 't2.micro'
            message['vpcid_hub'] = vpcid_hub
            #Finding the Public Subnet
            subnets=find_subnets(message['region_spoke'],message['vpcid_spoke'])
            message['subnet_spoke'] = subnets[0]['CidrBlock']
            message['subnet_spoke_ha'] = subnets[1]['CidrBlock']
            message['subnet_spoke_name'] = subnets[1]['Name']
            logger.info('Found VPC %s waiting to be peered. Sending SQS message to Queue %s' % (message['vpcid_spoke'],gatewayqueue))
            #Add New Gateway to SNS
            sns = boto3.client('sns')
            sns.publish(
                TopicArn=gatewaytopic,
                Subject='New Spoke Gateway',
                Message=json.dumps(message)
            )
        vpcs=ec2.describe_vpcs(Filters=[
            { 'Name': 'state', 'Values': [ 'available' ] },
            { 'Name': 'tag:aviatrix-spoke', 'Values': [ 'false', 'False', 'FALSE' ] }
        ])
        for vpc_peering in vpcs['Vpcs']:
            message = {}
            message['action'] = 'deletegateway'
            message['subnet_spoke'] = vpc_peering['CidrBlock']
            message['vpcid_spoke'] = vpc_peering['VpcId']
            message['region_spoke'] = region_id
            message['gwsize_spoke'] = 't2.micro'
            message['vpcid_hub'] = vpcid_hub
            logger.info('Found VPC %s waiting to be peered. Sending SQS message to Queue %s' % (message['vpcid_spoke'],gatewayqueue))
            #Add New Gateway to SQS
            #sqs = boto3.resource('sqs')
            sns = boto3.client('sns')
            #queue = sqs.get_queue_by_name(QueueName=gatewayqueue)
            #response = queue.send_message(MessageBody=json.dumps(message))
            sns.publish(
                TopicArn=gatewaytopic,
                Subject='Delete Spoke Gateway',
                Message=json.dumps(message)
            )
    return {
        'Status' : 'SUCCESS'
    }
