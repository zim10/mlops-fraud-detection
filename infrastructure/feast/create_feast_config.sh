# infrastructure/feast/scripts/create_feast_config.sh
#!/bin/bash

cat > feature_store.yaml << 'EOF'
project: fraud_detection
registry: s3://mlops-fraud-detection/feast/registry.db
provider: aws
online_store:
  redis:
    host: localhost
    port: 6379
offline_store:
  parquet:
    uri: s3://mlops-fraud-detection/feast/parquet/
entity_key_datasource:
  postgres:
    host: ${POSTGRES_HOST}
    port: 5432
    database: fraud_detection
    schema: public
EOF

echo "Feast configuration created!"