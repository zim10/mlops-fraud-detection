# infrastructure/mongodb/main.py
import pulumi
import pulumi_aws as aws

# VPC for MongoDB infrastructure
vpc = aws.ec2.Vpc("mongodb-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    tags={"Name": "mongodb-vpc"}
)

# Subnet
subnet = aws.ec2.Subnet("mongodb-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    availability_zone="us-east-1a",
    tags={"Name": "mongodb-subnet"}
)

# Security Group
sg = aws.ec2.SecurityGroup("mongodb-sg",
    description="Security group for MongoDB",
    vpc_id=vpc.id,
    ingress=[
        {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
        {"protocol": "tcp", "from_port": 27017, "to_port": 27017, "cidr_blocks": ["10.0.0.0/16"]},
    ],
    egress=[{"protocol": "all", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}],
    tags={"Name": "mongodb-sg"}
)

# EC2 Instance for MongoDB
instance = aws.ec2.Instance("mongodb-instance",
    ami="ami-0c55b159cbfafe1f0",  # Amazon Linux 2
    instance_type="t3.medium",
    subnet_id=subnet.id,
    vpc_security_group_ids=[sg.id],
    tags={"Name": "mongodb-server"}
)

pulumi.export("vpc_id", vpc.id)
pulumi.export("instance_id", instance.id)
pulumi.export("instance_ip", instance.public_ip)