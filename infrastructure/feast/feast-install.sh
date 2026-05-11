# infrastructure/feast/scripts/feast-install.sh
#!/bin/bash
set -e

# Install Redis
sudo apt-get update
sudo apt-get install -y redis-server

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Install Python dependencies
pip install feast redis pyarrow pandas

echo "Feast and Redis installation complete!"