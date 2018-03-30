# quickstart-aviatrix-nextgentransithub
## Aviatrix Global Transit Hub on the AWS Cloud


This Quick Start builds a highly available, secure global transit network on the Amazon Web Services (AWS) Cloud in about 10 minutes. It deploys Aviatrix Controller and Aviatrix Gateways in a central virtual private cloud (VPC) on AWS to manage routing between remote networks (spoke VPCs) in a hub-and-spoke model. 

You can add spoke VPCs to the network by tagging them in AWS. Aviatrix Global Transit Hub automatically establishes VPN connections between the spoke VPCs and the hub VPC by using AWS CloudFormation templates and AWS Lambda functions. The transit network supports multiple AWS accounts and can be extended to include shared services with direct peering, or to connect your cloud network to on-premises networks.

The Quick Start offers two deployment options:

- Deploying Aviatrix Global Transit Hub into a new VPC on AWS
- Deploying Aviatrix Global Transit Hub into an existing VPC on AWS

You can also use the AWS CloudFormation templates as a starting point for your own implementation.

![Quick Start architecture for Aviatrix Global Transit Hub on AWS](https://d0.awsstatic.com/partner-network/QuickStart/datasheets/aviatrix-global-transit-hub-architecture-on-aws.jpg)

For architectural details, best practices, step-by-step instructions, and customization options, see the 
[deployment guide](https://fwd.aws/WENBA).

To post feedback, submit feature ideas, or report bugs, use the **Issues** section of this GitHub repo.
If you'd like to submit code for this Quick Start, please review the [AWS Quick Start Contributor's Kit](https://aws-quickstart.github.io/). 

