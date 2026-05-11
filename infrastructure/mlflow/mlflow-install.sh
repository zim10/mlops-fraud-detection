# infrastructure/mlflow/scripts/mlflow-install.sh
#!/bin/bash
set -e

# Install Python dependencies
pip install mlflow boto3 sqlalchemy psycopg2-binary

# Configure MLflow
export MLFLOW_TRACKING_URI=http://localhost:5000
export AWS_DEFAULT_REGION=us-east-1

# Create MLflow service
cat > /etc/systemd/system/mlflow.service << 'EOF'
[Unit]
Description=MLflow Tracking Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/mlflow
ExecStart=/usr/local/bin/mlflow server --backend-store-uri postgresql://user:pass@localhost:5432/mlflow --default-artifact-root s3://mlops-fraud-detection-mlflow/
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl start mlflow
sudo systemctl enable mlflow

echo "MLflow installation complete!"