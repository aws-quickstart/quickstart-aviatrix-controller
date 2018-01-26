import os, sys
import boto3
import json
import logging
from urllib.request import urlopen, URLError
from urllib.parse import urlencode
#Needed to load Aviatrix Python API.
from aviatrix3 import Aviatrix
#Needed for Lambda Custom call
import cfnresponse
import time

#logging configuration
logger = logging.getLogger()
logger.setLevel(logging.INFO)

USAGE_URL = "http://127.0.0.1:5001"
USAGE_DATA = { 'launchtime': time.time()
               # 'accountid':  boto3.client('sts').get_caller_identity().get('Account')
               }

#Read environment Variables
controller_ip = os.environ.get("Controller_IP")
username = os.environ.get("Username")
private_ip = os.environ.get("Private_IP")
admin_email = os.environ.get("Admin_Email")
password = os.environ.get("Password")
account = os.environ.get("Account")
aviatrixroleapp = os.environ.get("AviatrixRoleApp")
aviatrixroleec2 = os.environ.get("AviatrixRoleEC2")
vpcid_hub = os.environ.get("VPC")
subnet_hub = os.environ.get("Subnet")
subnet_hubHA = os.environ.get("SubnetHA")
region_hub = os.environ.get("Region")
gwsize_hub = os.environ.get("HubGWSize")
gateway_queue = os.environ.get("GatewayQueue")
gatewaytopic = os.environ.get("GatewayTopic")
licensemodel = os.environ.get("LicenseModel")
license = os.environ.get("License")
otheraccount = os.environ.get("OtherAccount")
otheraccountroleapp = os.environ.get("OtherAccountRoleApp")
otheraccountroleec2 = os.environ.get("OtherAccountRoleEC2")

def send_usage_info(url,data):
    # sending POST request
    try:
        parameters = urlencode(data)
        response = urlopen(url, data=parameters)
        return "Usage Data sent"
    except URLError:
        return "Couldn't send out Usage Data"

def controller_login_first_time(controller_ip,username,private_ip,counter=1):
    logger.info('aviatrix-controller.py - Login in for First time. Attempt#:%s' % counter)
    try:
        if counter <=2:
            controller = Aviatrix(controller_ip)
            controller.login(username,private_ip)
            logger.info('aviatrix-controller.py - Login in for First time. SUCCESS')
            return {
                'Status' : 'SUCCESS',
                'Controller' : controller
            }
        else:
            logger.info('aviatrix-controller.py - Login in for First time. FAILURE')
            responseData = {
                "PhysicalResourceId": "arn:aws:fake:myID",
                "Cause" : controller.results
            }
            cfnresponse.send(event, context, cfnresponse.FAILURE, responseData)
            raise Exception('Failure to connect to controller after %s attempts' % counter)
    except URLError:
        if counter <= 2:
            logger.info('aviatrix-controller.py - FTL - Failed request - Retrying in 30s')
            time.sleep(30)
            counter += 1
            controller_login_first_time(controller_ip,username,private_ip,counter)

def controller_initialize(controller_ip,username,private_ip,password,admin_email,upgrade=False):
    logger.info('aviatrix-controller.py - Controller initialization Begins')
    #Start the Controller Initialization process
    response = controller_login_first_time(controller_ip,username,private_ip)
    controller = response['Controller']
    try:
        controller.admin_email(admin_email)
        controller.change_password(username,username,private_ip,password)
        controller.login(username,password)
        if upgrade:
            controller.initial_setup("run")
        logger.info('aviatrix-controller.py - Done with Initial Controller Setup')
        return {
            'Status' : 'SUCCESS',
            'Controller' : controller
        }
    except URLError:
        logger.info('aviatrix-controller.py - Failed request. Error: %s', controller.results)
        responseData = {
            "PhysicalResourceId": "arn:aws:fake:myID",
            "Cause" : controller.results
        }
        cfnresponse.send(event, context, cfnresponse.FAILURE, responseData)
        raise Exception('Failure initializing Controller')

def controller_account_setup(controller,admin_email,account,aviatrixroleapp,aviatrixroleec2,other=False):
    #Account Setup
    try:
        if other:
            account_name="AWSOtherAccount"
        else:
            account_name="AWSAccount"
        controller.setup_account_profile(account_name,
                                         password,
                                         admin_email,
                                         "1",
                                         account,
                                         aviatrixroleapp,
                                         aviatrixroleec2)
        logger.info('aviatrix-controller.py - Done with Setting up %s' % account_name)
        return {
            'Status' : 'SUCCESS'
        }
    except URLError:
        logger.info('aviatrix-controller.py - Failed request. Error: %s', controller.results)
        responseData = {
            "PhysicalResourceId": "arn:aws:fake:myID",
            "Cause" : controller.results
        }
        cfnresponse.send(event, context, cfnresponse.FAILURE, responseData)
        raise Exception('Failure setting up accounts on Controller')

def controller_setup_license(controller,licensemodel,license):
    #License Setup
    if licensemodel == "BYOL":
        logger.info('aviatrix-controller.py - Setting up License ')
        try:
            controller.setup_customer_id(license)
            logger.info('aviatrix-controller.py - Done with License Setup')
            return {
                'Status' : 'SUCCESS'
            }
        except URLError:
            logger.info('aviatrix-controller.py - Failed request. Error: %s', controller.results)
            return {
                'Status' : 'FAILURE',
                'Error' : controller.results
            }

def controller_login(controller_ip,username,password):
    try:
        controller = Aviatrix(controller_ip)
        controller.login(username,password)
        return controller
    except URLError:
        logger.info('aviatrix-controller.py - Failed request. Error: %s', controller.results)
        return {
            'Status' : 'FAILURE',
            'Error' : controller.results
        }

def create_handler(event,context):
    #Initialize the Aviatrix Controller
    response=controller_initialize(controller_ip,username,private_ip,password,admin_email,True)
    #Relogin to controller
    controller = controller_login(controller_ip,username,password)
    #Setup License
    response = controller_setup_license(controller,licensemodel,license)
    #Setup Accounts
    controller = controller_login(controller_ip,username,password)
    response = controller_account_setup(controller,admin_email,account,aviatrixroleapp,aviatrixroleec2,False)
    if otheraccount != "":
        other_response=controller_account_setup(controller,admin_email,otheraccount,otheraccountroleapp,otheraccountroleec2,True)
    logger.info('aviatrix-controller.py - Done with Controller Setup')

    #Gather necessary info to deploy Hub GW
    message = {}
    message['action'] = 'deployhub'
    message['vpcid_hub'] = vpcid_hub
    message['region_hub'] = region_hub
    message['gwsize_hub'] = gwsize_hub
    message['subnet_hub'] = subnet_hub
    message['subnet_hubHA'] = subnet_hubHA
    message['original_event'] = str(event)
    message['original_context'] = context.log_stream_name
    logger.info('aviatrix-controller.py - Creating Hub VPC %s. Sending SQS message', message['vpcid_hub'])
    logger.info('aviatrix-controller.py - Message sent: %s: ' % json.dumps(message))

    sns = boto3.client('sns')
    sns.publish(
        TopicArn=gatewaytopic,
        Subject='Create Hub Gateway',
        Message=json.dumps(message)
    )

    #Run this only once to report who is utilizing this script back to Aviatrix
    # usage_response = send_usage_info(USAGE_URL,USAGE_DATA)
    # logger.info('Usage Data Response: %s' % (usage_response))


def delete_handler(event, context):
    #Delete all tunnels and gateways
    try:
        logger.info('aviatrix-controller.py - Starting with decomission of Controller')
        controller = Aviatrix(controller_ip)
        controller.login(username,password)
        controller.list_peers_vpc_pairs()
        tunnels=controller.results
        if tunnels:
            logger.info('aviatrix-controller.py - Deleting existing tunnels')
            #To be done
            #for tunnel in tunnels delete each one.
        controller.list_vpcs_summary("admin")
        gateways=controller.results
        if gateways:
            for gateway in gateways:
                logger.info('aviatrix-controller.py - Deleting gateway %s', gateway['vpc_name'])
                controller.delete_gateway('1',gateway['vpc_name'])
        responseData = {
            "PhysicalResourceId": "arn:aws:fake:myID"
        }
        cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
    except URLError:
        logger.info('aviatrix-controller.py - Failed request. Error: %s', controller.results)
        return {
            'Status' : 'FAILURE',
            'Error' : controller.results
        }

def handler(event, context):
# Main function handler
    print(event)
    action = event["RequestType"]
    if action == "Create":
        create_handler(event, context)
    if action == "Delete":
        delete_handler(event, context)



# Create Event Example
# {
#   "StackId": "arn:aws:cloudformation:us-east-1:910395570553:stack/AviatrixLambda/0833bfb0-d9fa-11e7-8433-5044334e0ab3",
#   "ResponseURL": "https://cloudformation-custom-resource-response-useast1.s3.amazonaws.com/arn%3Aaws%3Acloudformation%3Aus-east-1%3A910395570553%3Astack/AviatrixLambda/0833bfb0-d9fa-11e7-8433-5044334e0ab3%7CAviatrixControllerLambdaTrigger%7C67dc9dbf-c18d-4f92-b802-7af92f11be69?AWSAccessKeyId=AKIAJNXHFR7P7YGKLDPQ&Expires=1512512668&Signature=AS3m%2FjJQdVCl%2FFbhS5oDNS4TVl0%3D",
#   "ResourceProperties": {
#     "ServiceToken": "arn:aws:lambda:us-east-1:910395570553:function:AviatrixLambda-AviatrixControllerLambda-1AG07492W8K3M"
#   },
#   "RequestType": "Create",
#   "ServiceToken": "arn:aws:lambda:us-east-1:910395570553:function:AviatrixLambda-AviatrixControllerLambda-1AG07492W8K3M",
#   "ResourceType": "Custom::ControllerLamdbdaTrigger",
#   "RequestId": "67dc9dbf-c18d-4f92-b802-7af92f11be69",
#   "LogicalResourceId": "AviatrixControllerLambdaTrigger"
# }
