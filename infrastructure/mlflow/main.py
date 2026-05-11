# infrastructure/mlflow/main.py
import pulumi
import pulumi_aws as aws

# VPC for MLflow infrastructure
vpc = aws.ec2.Vpc("mlflow-vpc",
    cidr_block="10.2.0.0/16",
    enable_dns_hostnames=True,
    tags={"Name": "mlflow-vpc"}
)

# Subnet
subnet = aws.ec2.Subnet("mlflow-subnet",
    vpc_id=vpc.id,
    cidr_block="10.2.1.0/24",
    availability_zone="us-east-1a",
    tags={"Name": "mlflow-subnet"}
)

# Security Group
sg = aws.ec2.SecurityGroup("mlflow-sg",
    description="Security group for MLflow",
    vpc_id=vpc.id,
    ingress=[
        {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
        {"protocol": "tcp", "from_port": 5000, "to_port": 5000, "cidr_blocks": ["0.0.0.0/0"]},
    ],
    egress=[{"protocol": "all", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}],
    tags={"Name": "mlflow-sg"}
)

# S3 Bucket for MLflow artifacts
bucket = aws.s3.Bucket("mlflow-artifacts",
    bucket="mlops-fraud-detection-mlflow",
    tags={"Name": "mlflow-artifacts"}
)

# IAM Role for EC2 to access S3
role = aws.iam.Role("mlflow-role",
    name="mlflow-ec2-role",
    assume_role_policy="""{
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"}
        }]
    }"""
)

role_policy = aws.iam.RolePolicy("mlflow-policy",
    role=role.id,
    policy=pulumi.Output.all(bucket.arn).apply(lambda args: f"""{{
        "Version": "2012-10-17",
        "Statement": [
            {{
                "Effect": "Allow",
                "Action": ["s3:*"],
                "Resource": ["{args[0]}/*"]
            }}
        ]
    }}""")
)

instance_profile = aws.iam.InstanceProfile("mlflow-profile", role=role.name)

# EC2 Instance for MLflow
instance = aws.ec2.Instance("mlflow-instance",
    ami="ami-0c55b159cbfafe1f0",
    instance_type="t3.large",
    subnet_id=subnet.id,
    vpc_security_group_ids=[sg.id],
    iam_instance_profile=instance_profile.name,
    tags={"Name": "mlflow-server"}
)

pulumi.export("bucket_name", bucket.bucket)
pulumi.export("instance_id", instance.id)