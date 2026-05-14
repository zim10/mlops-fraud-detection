"""
infrastructure/mongodb/main.py
Pulumi IaC — Deploys MongoDB on AWS EC2 inside a VPC with
a bastion host for secure SSH access.
"""

import pulumi
import pulumi_aws as aws

# ── VPC ──────────────────────────────────────────────────────────────────────
vpc = aws.ec2.Vpc(
    "my-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={"Name": "my-vpc"},
)

# ── Subnets ───────────────────────────────────────────────────────────────────
public_subnet = aws.ec2.Subnet(
    "public-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    availability_zone="ap-southeast-1a",
    map_public_ip_on_launch=True,
    tags={"Name": "public-subnet"},
)

private_subnet = aws.ec2.Subnet(
    "private-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.2.0/24",
    availability_zone="ap-southeast-1a",
    tags={"Name": "private-subnet"},
)

# ── Internet Gateway ──────────────────────────────────────────────────────────
igw = aws.ec2.InternetGateway(
    "internet-gateway",
    vpc_id=vpc.id,
    tags={"Name": "my-igw"},
)

# ── Public Route Table ────────────────────────────────────────────────────────
public_route_table = aws.ec2.RouteTable(
    "public-route-table",
    vpc_id=vpc.id,
    tags={"Name": "public-route-table"},
)

aws.ec2.Route(
    "igw-route",
    route_table_id=public_route_table.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=igw.id,
)

aws.ec2.RouteTableAssociation(
    "public-route-table-association",
    subnet_id=public_subnet.id,
    route_table_id=public_route_table.id,
)

# ── NAT Gateway (for private subnet outbound traffic) ────────────────────────
eip = aws.ec2.Eip("nat-eip", domain="vpc", tags={"Name": "nat-eip"})

nat_gateway = aws.ec2.NatGateway(
    "nat-gateway",
    subnet_id=public_subnet.id,
    allocation_id=eip.id,
    tags={"Name": "my-nat-gateway"},
    opts=pulumi.ResourceOptions(depends_on=[eip]),
)

# ── Private Route Table ───────────────────────────────────────────────────────
private_route_table = aws.ec2.RouteTable(
    "private-route-table",
    vpc_id=vpc.id,
    tags={"Name": "private-route-table"},
)

aws.ec2.Route(
    "nat-route",
    route_table_id=private_route_table.id,
    destination_cidr_block="0.0.0.0/0",
    nat_gateway_id=nat_gateway.id,
)

aws.ec2.RouteTableAssociation(
    "private-route-table-association",
    subnet_id=private_subnet.id,
    route_table_id=private_route_table.id,
)

# ── Security Groups ───────────────────────────────────────────────────────────
bastion_sg = aws.ec2.SecurityGroup(
    "bastion-secgrp",
    vpc_id=vpc.id,
    description="Enable SSH access for bastion host",
    ingress=[
        {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
    ],
    egress=[
        {"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]},
    ],
    tags={"Name": "bastion-sg"},
)

mongodb_sg = aws.ec2.SecurityGroup(
    "mongodb-secgrp",
    vpc_id=vpc.id,
    description="Enable SSH and MongoDB access from private subnet",
    ingress=[
        # SSH only from bastion (public subnet)
        {"protocol": "tcp", "from_port": 22,    "to_port": 22,    "cidr_blocks": ["10.0.1.0/24"]},
        # MongoDB only from within private subnet
        {"protocol": "tcp", "from_port": 27017, "to_port": 27017, "cidr_blocks": ["10.0.2.0/24"]},
    ],
    egress=[
        {"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]},
    ],
    tags={"Name": "mongodb-sg"},
)

# ── AMI & User Data ───────────────────────────────────────────────────────────
AMI_ID = "ami-02c7683e4ca3ebf58"  # Ubuntu 24.04 LTS — ap-southeast-1

def read_script(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        pulumi.log.warn(f"Script not found: {path}")
        return ""

mongodb_user_data = read_script("scripts/mongodb-install.sh")

# ── EC2 Instances ─────────────────────────────────────────────────────────────
bastion = aws.ec2.Instance(
    "bastion-host",
    instance_type="t2.micro",
    vpc_security_group_ids=[bastion_sg.id],
    ami=AMI_ID,
    subnet_id=public_subnet.id,
    key_name="MyKeyPair",
    associate_public_ip_address=True,
    tags={"Name": "bastion-host"},
)

mongodb_instance = aws.ec2.Instance(
    "mongodb-instance",
    instance_type="t2.micro",
    vpc_security_group_ids=[mongodb_sg.id],
    ami=AMI_ID,
    subnet_id=private_subnet.id,
    key_name="MyKeyPair",
    user_data=mongodb_user_data,
    root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
        volume_size=30,
        volume_type="gp3",
    ),
    tags={"Name": "mongodb-server"},
)

# ── Outputs ───────────────────────────────────────────────────────────────────
pulumi.export("vpc_id",                vpc.id)
pulumi.export("bastion_public_ip",     bastion.public_ip)
pulumi.export("bastion_private_ip",    bastion.private_ip)
pulumi.export("mongodb_private_ip",    mongodb_instance.private_ip)
pulumi.export("ssh_bastion_command",
    pulumi.Output.concat("ssh -i MyKeyPair.pem ubuntu@", bastion.public_ip))
pulumi.export("ssh_mongodb_command",
    pulumi.Output.concat("ssh -i MyKeyPair.pem ubuntu@", mongodb_instance.private_ip))
pulumi.export("mongodb_connection_string",
    pulumi.Output.concat("mongodb://", mongodb_instance.private_ip, ":27017/fraud_detection"))