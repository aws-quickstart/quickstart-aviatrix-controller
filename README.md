# quickstart-aviatrix-nextgentransithub
## Aviatrix Next-Gen Global Transit Hub on the AWS Cloud


This Quick Start builds a highly available, secure global transit network on the Amazon Web Services (AWS) Cloud in about 5 minutes. It deploys Aviatrix Controller and Aviatrix Gateways in a central virtual private cloud (VPC) on AWS to manage routing between remote networks (spoke VPCs) in a hub-and-spoke model. 

After you deploy the Aviatrix Controller using this Quick Start, you can use the Aviatrix Global Transit Network Wizard in the Aviatrix Controller to deploy the Hub Gateway instances into a VPC that will be designated as the Next-Gen Global Transit Hub. The wizard allows you to launch and configure two Aviatrix Gateways in the transit hub VPC and the designated spoke VPCs. The gateway instances allow for IPsec VPN termination, routing, and security policies, and provide ongoing monitoring.

Once you have established your transit VPC, you can extend beyond the AWS Cloud and automatically configure VPN connections to an on-premises infrastructure or other network providers with the Aviatrix Controller. Aviatrix also enables you to expand your global transit architecture to include a Shared Services layer with AWS Direct Peering. This helps support teams that require a shared or management VPC for common services in the cloud.

The Quick Start offers two deployment options:

- Deploying Aviatrix Next-Gen Global Transit Hub into a new VPC on AWS
- Deploying Aviatrix Next-Gen Global Transit Hub into an existing VPC on AWS

You can also use the AWS CloudFormation templates as a starting point for your own implementation.

![Quick Start architecture for Aviatrix Next-Gen Global Transit Hub on AWS](https://d1.awsstatic.com/partner-network/QuickStart/datasheets/aviatrix-next-gen-on-aws-architecture.ce5fc19c138ec20817c3bf747034b5dac63b3f47.png)

For architectural details, best practices, step-by-step instructions, and customization options, see the 
[deployment guide](https://fwd.aws/WENBA).

To post feedback, submit feature ideas, or report bugs, use the **Issues** section of this GitHub repo.
If you'd like to submit code for this Quick Start, please review the [AWS Quick Start Contributor's Kit](https://aws-quickstart.github.io/). 

