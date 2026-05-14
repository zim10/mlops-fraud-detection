"""
pipelines/preprocessing_pipeline.py
Airflow DAG — Feature engineering pipeline.
Reads raw data from MongoDB, engineers features, and pushes
processed data to the Feast feature store.
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pymongo import MongoClient
import requests
import json
import os

# ── Configuration ─────────────────────────────────────────────────────────────
MONGO_URI        = "mongodb://10.0.2.100:27017/"
DB_NAME          = "fraud_detection"
FEAST_SERVER_URL = "http://10.0.2.40:6566"
TMP_DIR          = "/opt/airflow/fraud_detection_pipeline/tmp"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_mongo_client():
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)


def load_collection(name: str, limit: int = 5000) -> pd.DataFrame:
    client = get_mongo_client()
    cursor = client[DB_NAME][name].find({}).limit(limit)
    df = pd.DataFrame(list(cursor))
    if "_id" in df.columns:
        df.drop("_id", axis=1, inplace=True)
    return df


# ── Task functions ────────────────────────────────────────────────────────────

def extract_raw_data():
    """Load train/test transaction + identity data from MongoDB."""
    print("Extracting raw data from MongoDB...")
    os.makedirs(TMP_DIR, exist_ok=True)

    train_txn = load_collection("train_transaction", limit=5000)
    test_txn  = load_collection("test_transaction",  limit=5000)
    train_id  = load_collection("train_identity",    limit=5000)
    test_id   = load_collection("test_identity",     limit=5000)

    train_txn.to_pickle(os.path.join(TMP_DIR, "train_transaction.pkl"))
    test_txn.to_pickle(os.path.join(TMP_DIR,  "test_transaction.pkl"))
    train_id.to_pickle(os.path.join(TMP_DIR,  "train_identity.pkl"))
    test_id.to_pickle(os.path.join(TMP_DIR,   "test_identity.pkl"))

    print(f"✓ train_transaction: {train_txn.shape}")
    print(f"✓ test_transaction:  {test_txn.shape}")
    print(f"✓ train_identity:    {train_id.shape}")
    print(f"✓ test_identity:     {test_id.shape}")


def merge_datasets():
    """Merge transaction and identity tables on TransactionID."""
    print("Merging transaction and identity data...")

    train_txn = pd.read_pickle(os.path.join(TMP_DIR, "train_transaction.pkl"))
    test_txn  = pd.read_pickle(os.path.join(TMP_DIR, "test_transaction.pkl"))
    train_id  = pd.read_pickle(os.path.join(TMP_DIR, "train_identity.pkl"))
    test_id   = pd.read_pickle(os.path.join(TMP_DIR, "test_identity.pkl"))

    train = train_txn.merge(train_id, on="TransactionID", how="left")
    test  = test_txn.merge(test_id,   on="TransactionID", how="left")

    train.to_pickle(os.path.join(TMP_DIR, "train_merged.pkl"))
    test.to_pickle(os.path.join(TMP_DIR,  "test_merged.pkl"))
    print(f"✓ Merged train: {train.shape} | test: {test.shape}")


def engineer_features():
    """
    Feature engineering:
    - Drop high-cardinality / leakage columns
    - Fill missing values
    - Encode categoricals
    - Add simple aggregate features
    """
    print("Engineering features...")

    train = pd.read_pickle(os.path.join(TMP_DIR, "train_merged.pkl"))
    test  = pd.read_pickle(os.path.join(TMP_DIR, "test_merged.pkl"))

    # Separate target
    y_train = train["isFraud"] if "isFraud" in train.columns else None

    drop_cols = ["isFraud", "TransactionID", "TransactionDT"]
    train.drop(columns=[c for c in drop_cols if c in train.columns], inplace=True)
    test.drop(columns=[c for c in drop_cols if c in test.columns],   inplace=True)

    # Align columns
    common = [c for c in train.columns if c in test.columns]
    train, test = train[common], test[common]

    # Fill missing values
    for col in train.select_dtypes(include=["object"]).columns:
        train[col].fillna("Unknown", inplace=True)
        test[col].fillna("Unknown",  inplace=True)

    for col in train.select_dtypes(include=[np.number]).columns:
        median = train[col].median()
        train[col].fillna(median, inplace=True)
        test[col].fillna(median,  inplace=True)

    # Label-encode categoricals
    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    for col in train.select_dtypes(include=["object"]).columns:
        train[col] = le.fit_transform(train[col].astype(str))
        test[col]  = le.transform(
            test[col].astype(str).apply(
                lambda x: x if x in le.classes_ else le.classes_[0]
            )
        )

    # Simple aggregate feature: transaction amount per card
    if "TransactionAmt" in train.columns and "card1" in train.columns:
        train["amt_per_card"] = train.groupby("card1")["TransactionAmt"].transform("mean")
        test["amt_per_card"]  = test.groupby("card1")["TransactionAmt"].transform("mean")

    # Re-attach target
    if y_train is not None:
        train["isFraud"] = y_train.values

    train.to_pickle(os.path.join(TMP_DIR, "X_train_engineered.pkl"))
    test.to_pickle(os.path.join(TMP_DIR,  "X_test_engineered.pkl"))
    print(f"✓ Engineered train: {train.shape} | test: {test.shape}")


def push_to_mongodb():
    """Persist final processed features back to MongoDB for the training DAG."""
    print("Pushing engineered features to MongoDB...")

    train = pd.read_pickle(os.path.join(TMP_DIR, "X_train_engineered.pkl"))
    test  = pd.read_pickle(os.path.join(TMP_DIR, "X_test_engineered.pkl"))

    client = get_mongo_client()
    db = client[DB_NAME]

    db["X_train_final"].drop()
    db["X_test_final"].drop()

    db["X_train_final"].insert_many(train.to_dict("records"))
    db["X_test_final"].insert_many(test.to_dict("records"))

    print(f"✓ Inserted {len(train)} train records and {len(test)} test records into MongoDB")


def push_to_feast():
    """Push engineered features to the Feast feature server."""
    print("Pushing features to Feast...")

    train = pd.read_pickle(os.path.join(TMP_DIR, "X_train_engineered.pkl"))

    # Keep only numeric columns for Feast
    numeric_cols = train.select_dtypes(include=[np.number]).columns.tolist()
    feast_data = train[numeric_cols].head(1000).to_dict("records")

    try:
        r = requests.post(
            f"{FEAST_SERVER_URL}/store-data",
            json={"data": feast_data},
            timeout=60,
        )
        if r.status_code == 200:
            print(f"✓ Pushed {len(feast_data)} records to Feast")
        else:
            print(f"Feast push returned {r.status_code}: {r.text}")
    except Exception as e:
        print(f"Could not reach Feast (non-fatal): {e}")


def validate_features():
    """Basic data quality checks on engineered features."""
    print("Validating features...")

    train = pd.read_pickle(os.path.join(TMP_DIR, "X_train_engineered.pkl"))
    test  = pd.read_pickle(os.path.join(TMP_DIR, "X_test_engineered.pkl"))

    assert len(train) > 0, "Train dataset is empty!"
    assert len(test)  > 0, "Test dataset is empty!"

    null_pct_train = train.isnull().mean().max()
    null_pct_test  = test.isnull().mean().max()

    print(f"Max null % — train: {null_pct_train:.2%} | test: {null_pct_test:.2%}")
    assert null_pct_train < 0.5, "Too many nulls in training data"

    print(f"✓ Validation passed — train: {train.shape} | test: {test.shape}")


# ── DAG Definition ────────────────────────────────────────────────────────────
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    "preprocessing_pipeline",
    default_args=default_args,
    description="Feature engineering pipeline — MongoDB → Feast",
    schedule_interval="@daily",
    catchup=False,
    tags=["fraud_detection", "preprocessing", "feature_engineering"],
) as dag:

    t_extract  = PythonOperator(task_id="extract_raw_data",    python_callable=extract_raw_data)
    t_merge    = PythonOperator(task_id="merge_datasets",      python_callable=merge_datasets)
    t_engineer = PythonOperator(task_id="engineer_features",   python_callable=engineer_features)
    t_validate = PythonOperator(task_id="validate_features",   python_callable=validate_features)
    t_mongo    = PythonOperator(task_id="push_to_mongodb",     python_callable=push_to_mongodb)
    t_feast    = PythonOperator(task_id="push_to_feast",       python_callable=push_to_feast)

    t_extract >> t_merge >> t_engineer >> t_validate >> [t_mongo, t_feast]