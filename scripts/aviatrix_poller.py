from __future__ import print_function
import os, boto3, json, logging

lambda_client = boto3.client('lambda')

#logging configuration
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def find_subnets(ec2,region_id,vpc_id):
    subnets_with_igw=ec2.describe_route_tables(Filters=[
        { 'Name': 'vpc-id', 'Values':[ vpc_id ]},
        { 'Name': 'route.gateway-id', 'Values': [ 'igw-*' ] }
    ])
    subnetids=[]
    for association in subnets_with_igw['RouteTables'][0]['Associations']:
      if 'SubnetId' in association:
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

def get_credentials(rolearn):
    session = boto3.session.Session()
    client = session.client('sts')
    assume_role_response = client.assume_role(RoleArn=rolearn,
                                              RoleSessionName="aviatrix_poller" )
    return assume_role_response

def handler(event, context):
    #Read environment Variables
    gatewayqueue = os.environ.get("GatewayQueue")
    vpcid_hub = os.environ.get("HubVPC")
    gwsize_spoke = os.environ.get("SpokeGWSizeParam")
    gatewaytopic = os.environ.get("GatewayTopic")
    spoketag = os.environ.get("SpokeTag")
    OtherAccountRoleApp = os.environ.get("OtherAccountRoleApp")

    #Gather all the regions:
    ec2=boto3.client('ec2',region_name='us-east-1')
    regions=ec2.describe_regions()
    #Get Access information for OtherAccountRoleApp
    if OtherAccountRoleApp:
        logger.info('[Other Account]: Secondary aws account found.')
        try:
            other_credentials = get_credentials(OtherAccountRoleApp)
        except:
            logger.warning('!!!you might not have the right permissions!!!. Moving on...')
    else:
        logger.info('[Other Account]: Secondary aws account NOT found.')
    #Findout if controller is busy:
    for region in regions['Regions']:
        region_id=region['RegionName']
        logger.info('Checking region: %s for VPC that are processing or unpeering',region_id)
        ec2=boto3.client('ec2',region_name=region_id)
        #Find VPCs with Tag:spoketag = processing
        #Create Gateway for it and Peer, when done change the Tag:spoketag = peered
        vpcs=ec2.describe_vpcs(Filters=[
            { 'Name': 'state', 'Values': [ 'available' ] },
            { 'Name': 'tag:'+spoketag, 'Values': [ 'processing', 'unpeering' ] }
        ])
        #logger.info('vpcs with tag:spoketag is processing or unpeering: %s:' % str(vpcs))
        if vpcs['Vpcs']: # ucc is busy now
            logger.info('ucc is busy in adding/removing spoke of %s:' % str(vpcs['Vpcs']))
            return {
                'Status' : 'SUCCESS'
            }
    #Findout if controller is busy in OtherAccountRoleApp
    if OtherAccountRoleApp:
        if other_credentials:
            for region in regions['Regions']:
                region_id=region['RegionName']
                logger.info('[Other Account] Checking region: %s for VPC that are processing or unpeering',region_id)
                ec2=boto3.client('ec2',
                                 region_name=region_id,
                                 aws_access_key_id=other_credentials['Credentials']['AccessKeyId'],
                                 aws_secret_access_key=other_credentials['Credentials']['SecretAccessKey'],
                                 aws_session_token=other_credentials['Credentials']['SessionToken'] )
                #Find VPCs with Tag:spoketag = processing
                #Create Gateway for it and Peer, when done change the Tag:spoketag = peered
                vpcs=ec2.describe_vpcs(Filters=[
                    { 'Name': 'state', 'Values': [ 'available' ] },
                    { 'Name': 'tag:'+spoketag, 'Values': [ 'processing', 'unpeering' ] }
                ])
                #logger.info('vpcs with tag:spoketag is processing or unpeering: %s:' % str(vpcs))
                if vpcs['Vpcs']: # ucc is busy now
                    logger.info('[Other Account] ucc is busy in adding/removing spoke of %s:' % str(vpcs['Vpcs']))
                    return {
                        'Status' : 'SUCCESS'
                    }
    #Find Spokes waiting to be peered or unpeered
    for region in regions['Regions']:
        region_id=region['RegionName']
        logger.info('Checking region: %s for VPC tagged %s' % (region_id,spoketag))
        ec2=boto3.client('ec2',region_name=region_id)
        #Find VPCs with Tag:spoketag = true
        #Create Gateway for it and Peer, when done change the Tag:spoketag = peered
        vpcs=ec2.describe_vpcs(Filters=[
            { 'Name': 'state', 'Values': [ 'available' ] },
            { 'Name': 'tag:'+spoketag, 'Values': [ 'true', 'True', 'TRUE', 'test' ] }
        ])
        for vpc_peering in vpcs['Vpcs']:
            message = {}
            message['action'] = 'deploygateway'
            message['vpcid_spoke'] = vpc_peering['VpcId']
            message['region_spoke'] = region_id
            message['gwsize_spoke'] = gwsize_spoke
            message['vpcid_hub'] = vpcid_hub
            #Finding the Public Subnet
            try:

                subnets=find_subnets(ec2, message['region_spoke'],message['vpcid_spoke'])
                if subnets:
                    logger.warning('Subnets found: %s ' % (subnets))
                message['subnet_spoke'] = subnets[0]['CidrBlock']
                message['subnet_spoke_ha'] = subnets[1]['CidrBlock']
                message['subnet_spoke_name'] = subnets[1]['Name']
            except:
                logger.warning('!!!your spoke vpc subnet is not setup correctly!!!')
                continue
            message['vpc_cidr_spoke'] = vpc_peering['CidrBlock']
            logger.info('Found VPC %s waiting to be peered. Sending SQS message to Queue %s' % (message['vpcid_spoke'],gatewayqueue))
            #Add New Gateway to SNS
            sns = boto3.client('sns')
            sns.publish(
                TopicArn=gatewaytopic,
                Subject='New Spoke Gateway',
                Message=json.dumps(message)
            )
            # only add one spoke at a time, return now
            return {
                'Status' : 'SUCCESS'
            }
        vpcs=ec2.describe_vpcs(Filters=[
            { 'Name': 'state', 'Values': [ 'available' ] },
            { 'Name': 'tag:'+spoketag, 'Values': [ 'false', 'False', 'FALSE' ] }
        ])
        for vpc_peering in vpcs['Vpcs']:
            message = {}
            message['action'] = 'deletegateway'
            message['subnet_spoke'] = vpc_peering['CidrBlock']
            message['vpcid_spoke'] = vpc_peering['VpcId']
            message['region_spoke'] = region_id
            message['gwsize_spoke'] = gwsize_spoke
            message['vpcid_hub'] = vpcid_hub
            logger.info('Found VPC %s waiting to be unpeered. Sending SQS message to Queue %s' % (message['vpcid_spoke'],gatewayqueue))
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
    #Find Spokes waiting to be peered or unpeered in OtherAccountRoleApp
    if OtherAccountRoleApp:
        if other_credentials:
            for region in regions['Regions']:
                region_id=region['RegionName']
                logger.info('[Other Account] Checking region: %s for VPC tagged %s' % (region_id,spoketag))
                ec2=boto3.client('ec2',
                                 region_name=region_id,
                                 aws_access_key_id=other_credentials['Credentials']['AccessKeyId'],
                                 aws_secret_access_key=other_credentials['Credentials']['SecretAccessKey'],
                                 aws_session_token=other_credentials['Credentials']['SessionToken'] )
                #Find VPCs with Tag:spoketag = true
                #Create Gateway for it and Peer, when done change the Tag:spoketag = peered
                vpcs=ec2.describe_vpcs(Filters=[
                    { 'Name': 'state', 'Values': [ 'available' ] },
                    { 'Name': 'tag:'+spoketag, 'Values': [ 'true', 'True', 'TRUE', 'test' ] }
                ])
                for vpc_peering in vpcs['Vpcs']:
                    message = {}
                    message['action'] = 'deploygateway'
                    message['vpcid_spoke'] = vpc_peering['VpcId']
                    message['region_spoke'] = region_id
                    message['gwsize_spoke'] = gwsize_spoke
                    message['vpcid_hub'] = vpcid_hub
                    message['otheraccount'] = True

                    #Finding the Public Subnet
                    try:
                        subnets=find_subnets(ec2,message['region_spoke'],message['vpcid_spoke'])
                        if subnets:
                            logger.warning('Subnets found: %s ' % (subnets))
                        message['subnet_spoke'] = subnets[0]['CidrBlock']
                        message['subnet_spoke_ha'] = subnets[1]['CidrBlock']
                        message['subnet_spoke_name'] = subnets[1]['Name']
                    except:
                        logger.warning('!!!your spoke vpc subnet is not setup correctly!!!')
                        continue
                    message['vpc_cidr_spoke'] = vpc_peering['CidrBlock']
                    logger.info('Found VPC %s waiting to be peered. Sending SQS message to Queue %s' % (message['vpcid_spoke'],gatewayqueue))
                    #Add New Gateway to SNS
                    sns = boto3.client('sns')
                    sns.publish(
                        TopicArn=gatewaytopic,
                        Subject='New Spoke Gateway',
                        Message=json.dumps(message)
                    )
                    # only add one spoke at a time, return now
                    return {
                        'Status' : 'SUCCESS'
                    }
                vpcs=ec2.describe_vpcs(Filters=[
                    { 'Name': 'state', 'Values': [ 'available' ] },
                    { 'Name': 'tag:'+spoketag, 'Values': [ 'false', 'False', 'FALSE' ] }
                ])
                for vpc_peering in vpcs['Vpcs']:
                    message = {}
                    message['action'] = 'deletegateway'
                    message['subnet_spoke'] = vpc_peering['CidrBlock']
                    message['vpcid_spoke'] = vpc_peering['VpcId']
                    message['region_spoke'] = region_id
                    message['gwsize_spoke'] = gwsize_spoke
                    message['vpcid_hub'] = vpcid_hub
                    message['otheraccount'] = True
                    logger.info('Found VPC %s waiting to be unpeered. Sending SQS message to Queue %s' % (message['vpcid_spoke'],gatewayqueue))
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
    return {
        'Status' : 'SUCCESS'
    }
