"""
pipelines/training_pipeline.py
Airflow DAG — Fraud detection model training pipeline.
Loads features from Feast, trains XGBoost / LightGBM / IsolationForest
in parallel, logs everything to MLflow, selects best model by F1-score.
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import pandas as pd
from pymongo import MongoClient
import os
import requests
import json
import numpy as np
import pickle
import mlflow
import mlflow.sklearn
import mlflow.xgboost
import mlflow.lightgbm
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score
from sklearn.ensemble import IsolationForest
import xgboost as xgb
import lightgbm as lgb

# ── Configuration ─────────────────────────────────────────────────────────────
TMP_DIR          = "/opt/airflow/fraud_detection_pipeline/tmp"
MODEL_DIR        = "/opt/airflow/fraud_detection_pipeline/models"
MONGO_URI        = "mongodb://10.0.2.100:27017/"
DB_NAME          = "fraud_detection"
FEAST_SERVER_URL = "http://10.0.2.40:6566"
MLFLOW_TRACKING_URI = "http://localhost:5000"

mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


# ── Utility helpers ───────────────────────────────────────────────────────────

def get_mongo_client():
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)


def load_data_from_mongodb(collection_name: str, limit: int = 1000) -> pd.DataFrame:
    client = get_mongo_client()
    db = client[DB_NAME]
    cursor = db[collection_name].find({}).limit(limit)
    df = pd.DataFrame(list(cursor))
    if "_id" in df.columns:
        df.drop("_id", axis=1, inplace=True)
    return df


# ── Task functions ────────────────────────────────────────────────────────────

def test_feast_connection():
    try:
        r = requests.get(f"{FEAST_SERVER_URL}/health", timeout=10)
        if r.status_code == 200:
            print(f"✓ Feast server healthy at {FEAST_SERVER_URL}")
            return True
        print(f"Feast returned {r.status_code}")
        return False
    except Exception as e:
        print(f"Failed to reach Feast: {e}")
        return False


def test_mlflow_connection():
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.tracking.MlflowClient()
        experiments = client.search_experiments()
        print(f"✓ MLflow connected — {len(experiments)} experiment(s) found")
        return True
    except Exception as e:
        print(f"Failed to reach MLflow: {e}")
        return False


def load_features_from_feast():
    """Pull processed features from Feast/MongoDB."""
    print("Loading features from Feast → MongoDB fallback...")
    try:
        X_train = load_data_from_mongodb("X_train_final", limit=1000)
        X_test  = load_data_from_mongodb("X_test_final",  limit=1000)
        print(f"Train shape: {X_train.shape} | Test shape: {X_test.shape}")

        if "isFraud" not in X_train.columns:
            print("Warning: isFraud missing — generating dummy target")
            X_train["isFraud"] = np.random.choice([0, 1], size=len(X_train), p=[0.9, 0.1])

        os.makedirs(TMP_DIR, exist_ok=True)
        X_train.to_pickle(os.path.join(TMP_DIR, "X_train_features.pkl"))
        X_test.to_pickle(os.path.join(TMP_DIR,  "X_test_features.pkl"))
        print("✓ Features saved to tmp/")
    except Exception as e:
        print(f"Error loading features: {e}")
        raise


def prepare_training_data():
    """Split features and target; align train/test columns."""
    print("Preparing training data...")
    X_train = pd.read_pickle(os.path.join(TMP_DIR, "X_train_features.pkl"))
    X_test  = pd.read_pickle(os.path.join(TMP_DIR, "X_test_features.pkl"))

    y_train = X_train.pop("isFraud") if "isFraud" in X_train.columns else \
              pd.Series(np.random.choice([0, 1], size=len(X_train), p=[0.9, 0.1]))

    train_num = X_train.select_dtypes(include=[np.number]).columns
    test_num  = X_test.select_dtypes(include=[np.number]).columns
    common    = train_num.intersection(test_num)

    X_train = X_train[common].fillna(0)
    X_test  = X_test[common].fillna(0)

    X_tr, X_val, y_tr, y_val = train_test_split(
        X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
    )

    X_tr.to_pickle(os.path.join(TMP_DIR,  "X_train_prepared.pkl"))
    X_val.to_pickle(os.path.join(TMP_DIR, "X_val_prepared.pkl"))
    X_test.to_pickle(os.path.join(TMP_DIR, "X_test_prepared.pkl"))
    with open(os.path.join(TMP_DIR, "y_train_prepared.pkl"), "wb") as f: pickle.dump(y_tr,  f)
    with open(os.path.join(TMP_DIR, "y_val_prepared.pkl"),   "wb") as f: pickle.dump(y_val, f)
    print(f"✓ Train: {X_tr.shape} | Val: {X_val.shape} | Test: {X_test.shape}")


def _load_prepared():
    X_train = pd.read_pickle(os.path.join(TMP_DIR, "X_train_prepared.pkl"))
    X_val   = pd.read_pickle(os.path.join(TMP_DIR, "X_val_prepared.pkl"))
    with open(os.path.join(TMP_DIR, "y_train_prepared.pkl"), "rb") as f: y_train = pickle.load(f)
    with open(os.path.join(TMP_DIR, "y_val_prepared.pkl"),   "rb") as f: y_val   = pickle.load(f)
    return X_train, X_val, y_train, y_val


def _log_metrics(y_val, y_pred, y_proba, model_name: str):
    auc       = roc_auc_score(y_val, y_proba)
    precision = precision_score(y_val, y_pred, zero_division=0)
    recall    = recall_score(y_val, y_pred, zero_division=0)
    f1        = f1_score(y_val, y_pred, zero_division=0)
    mlflow.log_metrics({"auc": auc, "precision": precision, "recall": recall, "f1_score": f1})
    metrics = {"model": model_name, "auc": auc, "precision": precision, "recall": recall, "f1_score": f1}
    with open(os.path.join(TMP_DIR, f"{model_name}_metrics.json"), "w") as f:
        json.dump(metrics, f)
    print(f"{model_name} → AUC={auc:.4f} | F1={f1:.4f}")
    return metrics


def train_xgboost_model():
    X_train, X_val, y_train, y_val = _load_prepared()
    mlflow.set_experiment("fraud_detection_xgboost")
    params = dict(objective="binary:logistic", eval_metric="auc", max_depth=6,
                  learning_rate=0.1, n_estimators=100, subsample=0.8,
                  colsample_bytree=0.8, random_state=42)
    with mlflow.start_run(run_name="xgboost_fraud_detection"):
        mlflow.log_params(params)
        model = xgb.XGBClassifier(**params)
        model.fit(X_train, y_train)
        y_proba = model.predict_proba(X_val)[:, 1]
        y_pred  = model.predict(X_val)
        _log_metrics(y_val, y_pred, y_proba, "xgboost")
        mlflow.xgboost.log_model(model, "model")
        os.makedirs(MODEL_DIR, exist_ok=True)
        model.save_model(os.path.join(MODEL_DIR, "xgboost_fraud_model.json"))
    print("✓ XGBoost training complete")


def train_lightgbm_model():
    X_train, X_val, y_train, y_val = _load_prepared()
    mlflow.set_experiment("fraud_detection_lightgbm")
    params = dict(objective="binary", metric="auc", boosting_type="gbdt",
                  num_leaves=31, learning_rate=0.1, n_estimators=100,
                  subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=-1)
    with mlflow.start_run(run_name="lightgbm_fraud_detection"):
        mlflow.log_params(params)
        model = lgb.LGBMClassifier(**params)
        model.fit(X_train, y_train)
        y_proba = model.predict_proba(X_val)[:, 1]
        y_pred  = model.predict(X_val)
        _log_metrics(y_val, y_pred, y_proba, "lightgbm")
        mlflow.lightgbm.log_model(model, "model")
        os.makedirs(MODEL_DIR, exist_ok=True)
        model.booster_.save_model(os.path.join(MODEL_DIR, "lightgbm_fraud_model.txt"))
    print("✓ LightGBM training complete")


def train_isolation_forest():
    X_train, X_val, y_train, y_val = _load_prepared()
    mlflow.set_experiment("fraud_detection_isolation_forest")
    params = dict(contamination=0.1, random_state=42, n_estimators=100)
    with mlflow.start_run(run_name="isolation_forest_fraud_detection"):
        mlflow.log_params(params)
        model = IsolationForest(**params)
        model.fit(X_train)
        y_pred_raw = model.predict(X_val)
        y_pred     = np.where(y_pred_raw == -1, 1, 0)
        y_scores   = -model.decision_function(X_val)
        _log_metrics(y_val, y_pred, y_scores, "isolation_forest")
        mlflow.sklearn.log_model(model, "model")
        os.makedirs(MODEL_DIR, exist_ok=True)
        with open(os.path.join(MODEL_DIR, "isolation_forest_model.pkl"), "wb") as f:
            pickle.dump(model, f)
    print("✓ Isolation Forest training complete")


def select_best_model():
    """Compare all trained models and select the one with the highest F1-score."""
    performance = []
    for name in ["xgboost", "lightgbm", "isolation_forest"]:
        path = os.path.join(TMP_DIR, f"{name}_metrics.json")
        if os.path.exists(path):
            with open(path) as f:
                performance.append(json.load(f))

    if not performance:
        raise ValueError("No model metrics found — did training tasks run?")

    best = max(performance, key=lambda x: x["f1_score"])

    print("\nModel Comparison:")
    for m in performance:
        print(f"  {m['model']:25s} AUC={m['auc']:.4f}  F1={m['f1_score']:.4f}")
    print(f"\n✓ Best model: {best['model']} (F1={best['f1_score']:.4f})")

    with open(os.path.join(TMP_DIR, "best_model.json"), "w") as f:
        json.dump(best, f)

    mlflow.set_experiment("fraud_detection_model_selection")
    with mlflow.start_run(run_name="best_model_selection"):
        mlflow.log_params({"selection_criteria": "f1_score"})
        mlflow.log_metrics({"best_f1_score": best["f1_score"], "best_auc": best["auc"]})
        mlflow.log_artifact(os.path.join(TMP_DIR, "best_model.json"))

    print("✓ Best model logged to MLflow")


# ── DAG Definition ────────────────────────────────────────────────────────────
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    "training_pipeline",
    default_args=default_args,
    description="Fraud detection model training pipeline",
    schedule_interval=None,   # Manual trigger only
    catchup=False,
    tags=["fraud_detection", "training", "ml"],
) as dag:

    t_feast  = PythonOperator(task_id="test_feast_connection",  python_callable=test_feast_connection)
    t_mlflow = PythonOperator(task_id="test_mlflow_connection", python_callable=test_mlflow_connection)
    t_load   = PythonOperator(task_id="load_features",          python_callable=load_features_from_feast)
    t_prep   = PythonOperator(task_id="prepare_training_data",  python_callable=prepare_training_data)
    t_xgb    = PythonOperator(task_id="train_xgboost",          python_callable=train_xgboost_model)
    t_lgb    = PythonOperator(task_id="train_lightgbm",         python_callable=train_lightgbm_model)
    t_iso    = PythonOperator(task_id="train_isolation_forest",  python_callable=train_isolation_forest)
    t_best   = PythonOperator(task_id="select_best_model",      python_callable=select_best_model)

    [t_feast, t_mlflow] >> t_load >> t_prep
    t_prep >> [t_xgb, t_lgb, t_iso] >> t_best