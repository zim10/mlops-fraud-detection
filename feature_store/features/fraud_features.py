"""
feature_store/features/fraud_features.py
Feast feature definitions for the fraud detection pipeline.
Defines entities, data sources, and feature views for both
offline (parquet) and online (Redis) stores.
"""

from feast import Entity, FeatureView, Field, FileSource
from feast.types import Float64, Int64, String
from datetime import timedelta

# ── Entity ────────────────────────────────────────────────────────────────────
# The primary key that joins features across views
transaction = Entity(
    name="transaction_id",
    join_keys=["TransactionID"],
    description="Unique fraud detection transaction identifier",
)

# ── Offline Data Source ───────────────────────────────────────────────────────
# Parquet file produced by the preprocessing pipeline
transaction_source = FileSource(
    path="/home/ubuntu/fraud_detection_pipeline/fraud_detection_features/data/data_source.parquet",
    timestamp_field="event_timestamp",
    description="Processed fraud transaction features",
)

# ── Feature Views ─────────────────────────────────────────────────────────────

transaction_features = FeatureView(
    name="transaction_features",
    entities=[transaction],
    ttl=timedelta(days=7),
    schema=[
        Field(name="TransactionAmt",      dtype=Float64),
        Field(name="card1",               dtype=Int64),
        Field(name="card2",               dtype=Float64),
        Field(name="card3",               dtype=Float64),
        Field(name="card5",               dtype=Float64),
        Field(name="addr1",               dtype=Float64),
        Field(name="addr2",               dtype=Float64),
        Field(name="dist1",               dtype=Float64),
        Field(name="dist2",               dtype=Float64),
        Field(name="P_emaildomain",       dtype=String),
        Field(name="R_emaildomain",       dtype=String),
        Field(name="C1",                  dtype=Float64),
        Field(name="C2",                  dtype=Float64),
        Field(name="C3",                  dtype=Float64),
        Field(name="C4",                  dtype=Float64),
        Field(name="C5",                  dtype=Float64),
        Field(name="C6",                  dtype=Float64),
        Field(name="C7",                  dtype=Float64),
        Field(name="C8",                  dtype=Float64),
        Field(name="C9",                  dtype=Float64),
        Field(name="C10",                 dtype=Float64),
        Field(name="C11",                 dtype=Float64),
        Field(name="C12",                 dtype=Float64),
        Field(name="C13",                 dtype=Float64),
        Field(name="C14",                 dtype=Float64),
        Field(name="D1",                  dtype=Float64),
        Field(name="D2",                  dtype=Float64),
        Field(name="D3",                  dtype=Float64),
        Field(name="D4",                  dtype=Float64),
        Field(name="D5",                  dtype=Float64),
        Field(name="M1",                  dtype=String),
        Field(name="M2",                  dtype=String),
        Field(name="M3",                  dtype=String),
        Field(name="M4",                  dtype=String),
        Field(name="M5",                  dtype=String),
        Field(name="M6",                  dtype=String),
        Field(name="M7",                  dtype=String),
        Field(name="M8",                  dtype=String),
        Field(name="M9",                  dtype=String),
        Field(name="amt_per_card",        dtype=Float64),
    ],
    source=transaction_source,
    online=True,      # Materialise to Redis for real-time serving
    description="Core transaction features for fraud detection",
    tags={"team": "mlops", "project": "fraud-detection"},
)

identity_features = FeatureView(
    name="identity_features",
    entities=[transaction],
    ttl=timedelta(days=7),
    schema=[
        Field(name="DeviceType",      dtype=String),
        Field(name="DeviceInfo",      dtype=String),
        Field(name="id_01",           dtype=Float64),
        Field(name="id_02",           dtype=Float64),
        Field(name="id_03",           dtype=Float64),
        Field(name="id_04",           dtype=Float64),
        Field(name="id_05",           dtype=Float64),
        Field(name="id_06",           dtype=Float64),
        Field(name="id_09",           dtype=Float64),
        Field(name="id_10",           dtype=Float64),
        Field(name="id_11",           dtype=Float64),
        Field(name="id_12",           dtype=String),
        Field(name="id_13",           dtype=Float64),
        Field(name="id_14",           dtype=Float64),
        Field(name="id_15",           dtype=String),
        Field(name="id_16",           dtype=String),
        Field(name="id_17",           dtype=Float64),
        Field(name="id_18",           dtype=Float64),
        Field(name="id_19",           dtype=Float64),
        Field(name="id_20",           dtype=Float64),
        Field(name="id_28",           dtype=String),
        Field(name="id_29",           dtype=String),
        Field(name="id_31",           dtype=String),
        Field(name="id_33",           dtype=String),
        Field(name="id_36",           dtype=String),
        Field(name="id_37",           dtype=String),
        Field(name="id_38",           dtype=String),
    ],
    source=transaction_source,
    online=True,
    description="Device and identity features for fraud detection",
    tags={"team": "mlops", "project": "fraud-detection"},
)
