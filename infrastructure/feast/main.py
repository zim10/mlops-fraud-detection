# infrastructure/feast/main.py
import pulumi
import pulumi_aws as aws

# VPC for Feast + Redis infrastructure
vpc = aws.ec2.Vpc("feast-vpc",
    cidr_block="10.1.0.0/16",
    enable_dns_hostnames=True,
    tags={"Name": "feast-vpc"}
)

# Subnets
subnet_a = aws.ec2.Subnet("feast-subnet-a",
    vpc_id=vpc.id,
    cidr_block="10.1.1.0/24",
    availability_zone="us-east-1a",
    tags={"Name": "feast-subnet-a"}
)

subnet_b = aws.ec2.Subnet("feast-subnet-b",
    vpc_id=vpc.id,
    cidr_block="10.1.2.0/24",
    availability_zone="us-east-1b",
    tags={"Name": "feast-subnet-b"}
)

# Security Group
sg = aws.ec2.SecurityGroup("feast-sg",
    description="Security group for Feast",
    vpc_id=vpc.id,
    ingress=[
        {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
        {"protocol": "tcp", "from_port": 6379, "to_port": 6379, "cidr_blocks": ["10.1.0.0/16"]},
        {"protocol": "tcp", "from_port": 8888, "to_port": 8888, "cidr_blocks": ["0.0.0.0/0"]},
    ],
    egress=[{"protocol": "all", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}],
    tags={"Name": "feast-sg"}
)

# EC2 Instance for Feast + Redis
instance = aws.ec2.Instance("feast-instance",
    ami="ami-0c55b159cbfafe1f0",
    instance_type="t3.large",
    subnet_id=subnet_a.id,
    vpc_security_group_ids=[sg.id],
    tags={"Name": "feast-server"}
)

pulumi.export("vpc_id", vpc.id)
pulumi.export("instance_id", instance.id)