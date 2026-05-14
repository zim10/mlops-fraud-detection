"""
cicd-infrastructure/__main__.py
Pulumi IaC — Provisions the complete CI/CD deployment stack:
  VPC + public subnet + IGW + route table
  Security group (ports 22, 8001, 8002, 9090, 3000)
  Two ECR repositories (ml-inference, data-ingestion)
  EC2 t2.micro + Elastic IP
  SSH key pair from environment variable SSH_PUBLIC_KEY

Destroy-and-recreate strategy: every CI/CD run calls
  pulumi destroy --yes  then  pulumi up --yes
ensuring a clean environment on every deployment.
"""

import os
import pulumi
import pulumi_aws as aws

# ── Stack identifier ──────────────────────────────────────────────────────────
UNIQUE_SUFFIX = "main"
STACK         = pulumi.get_stack()
REGION        = "ap-southeast-1"
AMI_ID        = "ami-0df7a207adb9748c7"   # Ubuntu 22.04 LTS — ap-southeast-1

# ── SSH Key Pair ──────────────────────────────────────────────────────────────
key_pair = aws.ec2.KeyPair(
    "mlops-key",
    key_name=f"mlops-key-{UNIQUE_SUFFIX}",
    public_key=os.environ.get("SSH_PUBLIC_KEY", ""),
    tags={"Project": f"mlops-pipeline-{STACK}"},
)

# ── VPC ───────────────────────────────────────────────────────────────────────
vpc = aws.ec2.Vpc(
    "mlops-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={"Name": f"mlops-vpc-{STACK}", "Project": f"mlops-pipeline-{STACK}"},
)

igw = aws.ec2.InternetGateway(
    "mlops-igw",
    vpc_id=vpc.id,
    tags={"Name": f"mlops-igw-{STACK}"},
)

subnet = aws.ec2.Subnet(
    "mlops-public-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    availability_zone=f"{REGION}a",
    map_public_ip_on_launch=True,
    tags={"Name": f"mlops-public-subnet-{STACK}"},
)

route_table = aws.ec2.RouteTable(
    "mlops-route-table",
    vpc_id=vpc.id,
    routes=[aws.ec2.RouteTableRouteArgs(
        cidr_block="0.0.0.0/0",
        gateway_id=igw.id,
    )],
    tags={"Name": f"mlops-route-table-{STACK}"},
)

aws.ec2.RouteTableAssociation(
    "mlops-rta",
    subnet_id=subnet.id,
    route_table_id=route_table.id,
)

# ── Security Group ────────────────────────────────────────────────────────────
sg = aws.ec2.SecurityGroup(
    "mlops-sg",
    name=f"mlops-sg-{UNIQUE_SUFFIX}",
    vpc_id=vpc.id,
    description="MLOps CI/CD services security group",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=22,   to_port=22,   cidr_blocks=["0.0.0.0/0"], description="SSH"),
        aws.ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=8001, to_port=8001, cidr_blocks=["0.0.0.0/0"], description="ML Inference"),
        aws.ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=8002, to_port=8002, cidr_blocks=["0.0.0.0/0"], description="Data Ingestion"),
        aws.ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=9090, to_port=9090, cidr_blocks=["0.0.0.0/0"], description="Prometheus"),
        aws.ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=3000, to_port=3000, cidr_blocks=["0.0.0.0/0"], description="Grafana"),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"]),
    ],
    tags={"Name": f"mlops-sg-{STACK}"},
)

# ── ECR Repositories ──────────────────────────────────────────────────────────
ml_repo = aws.ecr.Repository(
    "ml-inference-repo",
    name=f"mlops/ml-inference-{UNIQUE_SUFFIX}",
    image_tag_mutability="MUTABLE",
    force_delete=True,
    image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=True,
    ),
    tags={"Name": f"ml-inference-repo-{STACK}"},
)

data_repo = aws.ecr.Repository(
    "data-ingestion-repo",
    name=f"mlops/data-ingestion-{UNIQUE_SUFFIX}",
    image_tag_mutability="MUTABLE",
    force_delete=True,
    image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=True,
    ),
    tags={"Name": f"data-ingestion-repo-{STACK}"},
)

# ── EC2 User-Data ─────────────────────────────────────────────────────────────
USER_DATA = """#!/bin/bash
apt-get update -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker ubuntu
systemctl enable docker
systemctl start docker

# Docker log rotation (important for t2.micro)
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
EOF
systemctl restart docker

# Docker Compose v2
curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" \
     -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# AWS CLI v2
apt-get install -y unzip curl
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip -q awscliv2.zip
./aws/install
rm -rf aws awscliv2.zip get-docker.sh

# Wait for Docker
timeout=120
while ! docker info > /dev/null 2>&1 && [ $timeout -gt 0 ]; do
  sleep 5; timeout=$((timeout-5))
done

echo "Setup complete at $(date)" > /home/ubuntu/setup-info.txt
chown ubuntu:ubuntu /home/ubuntu/setup-info.txt
"""

# ── EC2 Instance ──────────────────────────────────────────────────────────────
instance = aws.ec2.Instance(
    "mlops-instance",
    key_name=key_pair.key_name,
    instance_type="t2.micro",
    ami=AMI_ID,
    subnet_id=subnet.id,
    vpc_security_group_ids=[sg.id],
    user_data=USER_DATA,
    root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
        volume_type="gp2",
        volume_size=20,
        delete_on_termination=True,
    ),
    tags={"Name": f"mlops-instance-{STACK}"},
)

# ── Elastic IP ────────────────────────────────────────────────────────────────
eip = aws.ec2.Eip(
    "mlops-eip",
    instance=instance.id,
    domain="vpc",
    tags={"Name": f"mlops-eip-{STACK}"},
)

# ── Outputs ───────────────────────────────────────────────────────────────────
pulumi.export("vpc_id",                vpc.id)
pulumi.export("instance_id",           instance.id)
pulumi.export("instance_public_ip",    eip.public_ip)
pulumi.export("ml_inference_repo_url", ml_repo.repository_url)
pulumi.export("data_ingestion_repo_url", data_repo.repository_url)
pulumi.export("unique_suffix",         UNIQUE_SUFFIX)
pulumi.export("grafana_url",    pulumi.Output.concat("http://", eip.public_ip, ":3000"))
pulumi.export("prometheus_url", pulumi.Output.concat("http://", eip.public_ip, ":9090"))
pulumi.export("ml_service_url", pulumi.Output.concat("http://", eip.public_ip, ":8001"))
pulumi.export("data_service_url", pulumi.Output.concat("http://", eip.public_ip, ":8002"))