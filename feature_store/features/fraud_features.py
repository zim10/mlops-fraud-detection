# feature_store/features/fraud_features.py
"""
Feast Feature Definitions for Fraud Detection
"""
from feast import Entity, Feature, FeatureView, FileSource
from feast.types import Float64, Int64
from datetime import timedelta

# Entity definition
transaction = Entity(
    name="transaction",
    join_keys=["transaction_id"],
    description="Transaction entity"
)

# File sources
transactions_source = FileSource(
    path="s3://mlops-fraud-detection/feast/parquet/transactions.parquet",
    timestamp_field="timestamp"
)

# Feature views
transaction_features = FeatureView(
    name="transaction_features",
    entities=["transaction"],
    ttl=timedelta(hours=1),
    schema={
        "amount_stats_1h": Float64,
        "velocity_24h": Float64,
        "user_risk_score": Float64,
    },
    source=transactions_source
)

merchant_features = FeatureView(
    name="merchant_features",
    entities=["transaction"],
    ttl=timedelta(days=7),
    schema={
        "fraud_rate": Float64,
        "total_transactions": Int64,
        "avg_transaction_amount": Float64,
    },
    source=transactions_source
)

user_features = FeatureView(
    name="user_features",
    entities=["transaction"],
    ttl=timedelta(days=30),
    schema={
        "account_age_days": Int64,
        "total_transactions": Int64,
        "chargeback_rate": Float64,
    },
    source=transactions_source
)