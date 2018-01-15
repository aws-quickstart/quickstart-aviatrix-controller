import unittest
from  aviatrix_poller import *

class Aviatrix_Poller_Test(unittest.TestCase):
  def test_find_subnets(self):
    region_id='us-east-1'
    vpc_id='vpc-afdee5d7'
    ec2=boto3.client('ec2',region_name=region_id)
    result=find_subnets(ec2,region_id,vpc_id)
    self.assertIs(type(result), list)
    for subnet in result:
        self.assertEquals(subnet['SubnetId'][:6],'subnet')
        self.assertEquals(subnet['Name'][:8],'Unittest')
    #Fail tests
    region_id='us-east-2'
    vpc_id='vpc-afdee5d7'
    ec2=boto3.client('ec2',region_name=region_id)
    with self.assertRaises(IndexError):
        result=find_subnets(ec2,region_id,vpc_id)

if __name__ == '__main__':
  unittest.main()
