from urllib2 import Request, urlopen, URLError
from time import sleep
import urllib, ssl, json, logging
import os

class Aviatrix:
    logging.basicConfig(filename="./aviatrix.log",level="INFO")
    def __init__(self,controller_ip):
        self.controller_ip = controller_ip
        self.CID = ""
        #Required for SSL Certificate no-verify
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
    def avx_api_call(self,method,action,parameters):
        url = "https://%s/v1/api?action=%s" % (self.controller_ip,action)
        for key,value in parameters.iteritems():
            value = urllib.quote(value, safe='')
            url = url + "&%s=%s" % (key,value)
        self.url = url
        logging.info("Executing API call:%s" % self.url)
        try:
            if method == "POST":
                data = urllib.urlencode(parameters)
                response = urlopen(self.url, data=data, context=self.ctx)
            else:
                response = urlopen(self.url, context=self.ctx)
            json_response = response.read()
            logging.info("HTTP Response: %s" % json_response)
            self.result = json.loads(json_response)
            if self.result['return'] == False:
                self.results = self.result['reason']
            else:
                self.results = self.result['results']
        except URLError, e:
            logging.info('Failed request. URLError: %s', str(e.reason))

    def login(self,username,password):
        self.avx_api_call("GET","login",{ "username": username,
                                          "password": password })
        try:
            if self.result['return'] == True:
                self.CID = self.result['CID']
        except AttributeError,e:
            logging.info('Login Request Failed. AttributeError: %s', str(e))

    def admin_email(self,email):
        self.avx_api_call("GET","add_admin_email_addr", { "CID": self.CID,
                                                          "admin_email": email })

    def change_password(self,account,username,old_password,password):
        self.avx_api_call("GET","change_password", { "CID": self.CID,
                                                     "account_name": account,
                                                     "user_name": username,
                                                     "old_password": old_password,
                                                     "password": password })

    def initial_setup(self,subaction):
        self.avx_api_call("POST","initial_setup", { "subaction": subaction, "CID": self.CID })
        if self.result['return'] == True:
            sleep(self.result['results'])

    def setup_account_profile(self,account,password,email,cloud_type,aws_account_number,aws_role_arn,aws_role_ec2):
        self.avx_api_call("POST","setup_account_profile", { "CID": self.CID,
                                                            "account_name": account,
                                                            "account_password": password,
                                                            "account_email": email,
                                                            "cloud_type": cloud_type,
                                                            "aws_iam": "true",
                                                            "aws_account_number": aws_account_number,
                                                            "aws_role_arn": aws_role_arn,
                                                            "aws_role_ec2": aws_role_ec2 })

    def setup_customer_id(self,customer_id):
        self.avx_api_call("GET","setup_customer_id", { "CID": self.CID,
                                                       "customer_id": customer_id })

    def create_gateway(self,account,cloud_type,gw_name,vpc_id,vpc_region,vpc_size,vpc_net):
        self.avx_api_call("POST","connect_container", { "CID": self.CID,
                                                        "account_name": account,
                                                        "cloud_type": cloud_type,
                                                        "gw_name": gw_name,
                                                        "vpc_id": vpc_id,
                                                        "vpc_reg": vpc_region,
                                                        "vpc_size": vpc_size,
                                                        "vpc_net": vpc_net })
    def delete_gateway(self,cloud_type,gw_name):
        self.avx_api_call("GET","delete_container", { "CID": self.CID,
                                                        "cloud_type": cloud_type,
                                                        "gw_name": gw_name })
    def peering(self,vpc_name1,vpc_name2):
        self.avx_api_call("GET","peer_vpc_pair", { "CID": self.CID,
                                                   "vpc_name1": vpc_name1,
                                                   "vpc_name2": vpc_name2 })
    def unpeering(self,vpc_name1,vpc_name2):
        self.avx_api_call("GET","unpeer_vpc_pair", { "CID": self.CID,
                                                   "vpc_name1": vpc_name1,
                                                   "vpc_name2": vpc_name2 })

    def enable_vpc_ha(self,vpc_name,specific_subnet):
        self.avx_api_call("POST","enable_vpc_ha", { "CID": self.CID,
                                                    "vpc_name": vpc_name,
                                                    "specific_subnet": specific_subnet })

    def disable_vpc_ha(self,vpc_name,specific_subnet):
        self.avx_api_call("POST","disable_vpc_ha", { "CID": self.CID,
                                                    "vpc_name": vpc_name,
                                                    "specific_subnet": specific_subnet })

    def add_extended_vpc_peer(self,source,nexthop,reachable_cidr):
        self.avx_api_call("POST", "add_extended_vpc_peer", { "CID": self.CID,
                                                        "source": source,
                                                        "nexthop": nexthop,
                                                        "reachable_cidr": reachable_cidr })
    def delete_extended_vpc_peer(self,source,nexthop,reachable_cidr):
        self.avx_api_call("POST", "delete_extended_vpc_peer", { "CID": self.CID,
                                                                "source": source,
                                                                "nexthop": nexthop,
                                                                "reachable_cidr": reachable_cidr })
    def list_extended_vpc_peer(self):
        self.avx_api_call("POST", "list_extended_vpc_peer", { "CID": self.CID })
    def list_peers_vpc_pairs(self):
        self.avx_api_call("GET", "list_peer_vpc_pairs", { "CID": self.CID })

    def list_vpcs_summary(self,account_name):
        self.avx_api_call("GET", "list_vpcs_summary", { "CID": self.CID,
                                                        "account_name": account_name })

    def add_vpn_user(self,vpc_id,username,user_email,profile_name):
        self.avx_api_call("GET", "add_vpn_user", {  "CID": self.CID,
                                                    "vpc_id": vpc_id,
                                                    "username": username,
                                                    "user_email": user_email,
                                                    "profile_name": profile_name })
