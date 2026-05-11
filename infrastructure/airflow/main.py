# infrastructure/airflow/main.py
import pulumi
import pulumi_aws as aws

# VPC for Airflow infrastructure
vpc = aws.ec2.Vpc("airflow-vpc",
    cidr_block="10.3.0.0/16",
    enable_dns_hostnames=True,
    tags={"Name": "airflow-vpc"}
)

# Subnet
subnet = aws.ec2.Subnet("airflow-subnet",
    vpc_id=vpc.id,
    cidr_block="10.3.1.0/24",
    availability_zone="us-east-1a",
    tags={"Name": "airflow-subnet"}
)

# Security Group
sg = aws.ec2.SecurityGroup("airflow-sg",
    description="Security group for Airflow",
    vpc_id=vpc.id,
    ingress=[
        {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
        {"protocol": "tcp", "from_port": 8080, "to_port": 8080, "cidr_blocks": ["0.0.0.0/0"]},
    ],
    egress=[{"protocol": "all", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}],
    tags={"Name": "airflow-sg"}
)

# EC2 Instance for Airflow
instance = aws.ec2.Instance("airflow-instance",
    ami="ami-0c55b159cbfafe1f0",
    instance_type="t3.xlarge",
    subnet_id=subnet.id,
    vpc_security_group_ids=[sg.id],
    tags={"Name": "airflow-server"}
)

pulumi.export("vpc_id", vpc.id)
pulumi.export("instance_id", instance.id)