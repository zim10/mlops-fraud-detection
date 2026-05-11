# infrastructure/airflow/scripts/airflow-install.sh
#!/bin/bash
set -e

# Install Python and pip
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv

# Create virtual environment
python3 -m venv /opt/airflow/venv
source /opt/airflow/venv/bin/activate

# Install Airflow
pip install apache-airflow==2.7.0

# Install additional providers
pip install apache-airflow-providers-amazon apache-airflow-providers-postgres

# Initialize Airflow database
airflow db init

# Create admin user
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com

# Start Airflow webserver and scheduler
export AIRFLOW_HOME=/opt/airflow
/opt/airflow/venv/bin/airflow webserver -p 8080 &
/opt/airflow/venv/bin/airflow scheduler &

echo "Airflow installation complete!"