"""
infrastructure/mlflow/main.py
Pulumi IaC — Deploys MLflow tracking server on AWS EC2.
Artifacts are stored in S3. EC2 is granted S3 access via IAM role.
MLflow UI is accessible on port 5000 via SSH tunnel through the bastion.
"""

import pulumi
import pulumi_aws as aws

# ── VPC ───────────────────────────────────────────────────────────────────────
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
igw = aws.ec2.InternetGateway("internet-gateway", vpc_id=vpc.id, tags={"Name": "my-igw"})

# ── Public Route Table ────────────────────────────────────────────────────────
public_rt = aws.ec2.RouteTable("public-route-table", vpc_id=vpc.id, tags={"Name": "public-route-table"})
aws.ec2.Route("igw-route", route_table_id=public_rt.id, destination_cidr_block="0.0.0.0/0", gateway_id=igw.id)
aws.ec2.RouteTableAssociation("public-rta", subnet_id=public_subnet.id, route_table_id=public_rt.id)

# ── NAT Gateway ───────────────────────────────────────────────────────────────
eip = aws.ec2.Eip("nat-eip", domain="vpc", tags={"Name": "nat-eip"})
nat_gw = aws.ec2.NatGateway(
    "nat-gateway",
    subnet_id=public_subnet.id,
    allocation_id=eip.id,
    tags={"Name": "my-nat-gateway"},
    opts=pulumi.ResourceOptions(depends_on=[eip]),
)

# ── Private Route Table ───────────────────────────────────────────────────────
private_rt = aws.ec2.RouteTable("private-route-table", vpc_id=vpc.id, tags={"Name": "private-route-table"})
aws.ec2.Route("nat-route", route_table_id=private_rt.id, destination_cidr_block="0.0.0.0/0", nat_gateway_id=nat_gw.id)
aws.ec2.RouteTableAssociation("private-rta", subnet_id=private_subnet.id, route_table_id=private_rt.id)

# ── Security Groups ───────────────────────────────────────────────────────────
bastion_sg = aws.ec2.SecurityGroup(
    "bastion-secgrp",
    vpc_id=vpc.id,
    description="SSH + MLflow tunnel access for bastion",
    ingress=[
        {"protocol": "tcp", "from_port": 22,   "to_port": 22,   "cidr_blocks": ["0.0.0.0/0"]},
        {"protocol": "tcp", "from_port": 5000, "to_port": 5000, "cidr_blocks": ["0.0.0.0/0"]},
    ],
    egress=[{"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}],
    tags={"Name": "bastion-sg"},
)

mlflow_sg = aws.ec2.SecurityGroup(
    "mlflow-secgrp",
    vpc_id=vpc.id,
    description="SSH and MLflow access from bastion / private subnet",
    ingress=[
        {"protocol": "tcp", "from_port": 22,   "to_port": 22,   "cidr_blocks": ["10.0.1.0/24"]},
        {"protocol": "tcp", "from_port": 5000, "to_port": 5000, "cidr_blocks": ["10.0.1.0/24"]},
        {"protocol": "tcp", "from_port": 5432, "to_port": 5432, "cidr_blocks": ["10.0.2.0/24"]},
    ],
    egress=[{"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}],
    tags={"Name": "mlflow-sg"},
)

# ── S3 Bucket for MLflow Artifacts ───────────────────────────────────────────
mlflow_bucket = aws.s3.Bucket(
    "mlflow-artifacts-bucket",
    tags={"Name": "mlflow-artifacts", "Project": "fraud-detection"},
)

aws.s3.BucketPublicAccessBlock(
    "mlflow-bucket-pab",
    bucket=mlflow_bucket.id,
    block_public_acls=True,
    block_public_policy=True,
    ignore_public_acls=True,
    restrict_public_buckets=True,
)

# ── IAM Role & Policy for S3 Access ──────────────────────────────────────────
ec2_role = aws.iam.Role(
    "ec2-mlflow-role",
    assume_role_policy="""{
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"}
        }]
    }""",
)

s3_policy = aws.iam.Policy(
    "s3-access-policy",
    policy=mlflow_bucket.arn.apply(lambda arn: f"""{{
        "Version": "2012-10-17",
        "Statement": [{{
            "Effect": "Allow",
            "Action": ["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:ListBucket"],
            "Resource": ["{arn}", "{arn}/*"]
        }}]
    }}"""),
)

aws.iam.RolePolicyAttachment(
    "role-policy-attachment",
    role=ec2_role.name,
    policy_arn=s3_policy.arn,
)

instance_profile = aws.iam.InstanceProfile("ec2-instance-profile", role=ec2_role.name)

# ── AMI & User Data ───────────────────────────────────────────────────────────
AMI_ID = "ami-02c7683e4ca3ebf58"

def read_script(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        pulumi.log.warn(f"Script not found: {path}")
        return ""

mlflow_user_data = read_script("scripts/mlflow-install.sh")

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

mlflow_instance = aws.ec2.Instance(
    "mlflow-instance",
    instance_type="t3.medium",
    vpc_security_group_ids=[mlflow_sg.id],
    ami=AMI_ID,
    subnet_id=private_subnet.id,
    key_name="MyKeyPair",
    user_data=mlflow_user_data,
    iam_instance_profile=instance_profile.name,
    root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
        volume_size=20,
        volume_type="gp3",
    ),
    tags={"Name": "mlflow-server"},
)

# ── Outputs ───────────────────────────────────────────────────────────────────
pulumi.export("vpc_id",             vpc.id)
pulumi.export("bastion_public_ip",  bastion.public_ip)
pulumi.export("mlflow_private_ip",  mlflow_instance.private_ip)
pulumi.export("mlflow_bucket_name", mlflow_bucket.bucket)
pulumi.export("mlflow_web_ui_url",
    pulumi.Output.concat("http://", mlflow_instance.private_ip, ":5000"))
pulumi.export("mlflow_tunnel_command",
    pulumi.Output.concat(
        "ssh -i MyKeyPair.pem -L 5000:",
        mlflow_instance.private_ip,
        ":5000 ubuntu@",
        bastion.public_ip,
    ))
pulumi.export("mlflow_tracking_uri",
    pulumi.Output.concat("http://", mlflow_instance.private_ip, ":5000"))