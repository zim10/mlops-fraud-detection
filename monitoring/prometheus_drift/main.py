"""
monitoring/prometheus_drift/main.py
FastAPI app that serves the churn prediction model,
logs predictions to PostgreSQL, tracks feature drift
via Prometheus gauges, and exposes a /metrics endpoint.
"""

import pickle
import boto3
import io
import time
import statistics
import logging
from datetime import datetime
from typing import List

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from sklearn.preprocessing import MinMaxScaler
from sqlalchemy.orm import Session
from prometheus_client import (
    Counter, Histogram, Gauge, make_asgi_app, generate_latest, CONTENT_TYPE_LATEST
)

from .models import SessionLocal, PredictionRecord, create_tables

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────
PREDICTION_COUNT    = Counter("churn_prediction_count",    "Total churn predictions",  ["result"])
PREDICTION_LATENCY  = Histogram("churn_prediction_latency_seconds", "Prediction latency",
                                buckets=[0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5])
INPUT_FEATURE_GAUGE = Gauge("churn_input_feature",  "Input feature mean values",    ["feature_name"])
FEATURE_DRIFT_GAUGE = Gauge("churn_feature_drift",  "Feature drift score vs baseline", ["feature_name"])
PREDICTION_DIST     = Histogram("churn_prediction_distribution", "Prediction probability distribution",
                                buckets=[i / 10 for i in range(11)])

# ── Baseline Statistics ───────────────────────────────────────────────────────
BASELINE_STATS = {
    "tenure":         {"mean": 32.4,   "std": 24.6},
    "MonthlyCharges": {"mean": 64.8,   "std": 30.1},
    "TotalCharges":   {"mean": 2283.3, "std": 2266.8},
}

_cumulative: dict = {
    f: {"values": [], "last_update": datetime.now()}
    for f in BASELINE_STATS
}

# ── S3 / Model Config ─────────────────────────────────────────────────────────
import os
S3_BUCKET = os.getenv("S3_BUCKET", "customer-churn-model-bucket")
MODEL_KEY  = os.getenv("MODEL_KEY", "model.pkl")
SCALE_COLS = ["tenure", "MonthlyCharges", "TotalCharges"]


class _MockModel:
    def predict_proba(self, X):
        n = X.shape[0]
        p = np.random.random((n, 2))
        return p / p.sum(axis=1, keepdims=True)


def _load_model():
    try:
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=S3_BUCKET, Key=MODEL_KEY)
        model = pickle.load(io.BytesIO(obj["Body"].read()))
        logger.info("✓ Model loaded from S3")
        return model
    except Exception as e:
        logger.warning(f"S3 model load failed ({e}) — using MockModel")
        return _MockModel()


model  = _load_model()
scaler = MinMaxScaler()

# ── Request Schema ────────────────────────────────────────────────────────────
class CustomerFeatures(BaseModel):
    gender: int; SeniorCitizen: int; Partner: int; Dependents: int
    tenure: float; PhoneService: int; MultipleLines: int
    OnlineSecurity: int; OnlineBackup: int; DeviceProtection: int
    TechSupport: int; StreamingTV: int; StreamingMovies: int
    PaperlessBilling: int; MonthlyCharges: float; TotalCharges: float
    InternetService_DSL: int; InternetService_Fiber_optic: int; InternetService_No: int
    Contract_Month_to_month: int; Contract_One_year: int; Contract_Two_year: int
    PaymentMethod_Bank_transfer_automatic: int; PaymentMethod_Credit_card_automatic: int
    PaymentMethod_Electronic_check: int; PaymentMethod_Mailed_check: int

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Churn Prediction API with Drift Monitoring", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    create_tables()
    logger.info("✓ DB tables ready")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _update_drift(feature: str, value: float):
    buf = _cumulative[feature]
    buf["values"].append(value)
    if len(buf["values"]) > 1000:
        buf["values"] = buf["values"][-1000:]

    now = datetime.now()
    if (now - buf["last_update"]).total_seconds() > 60 and len(buf["values"]) > 1:
        cur_mean = statistics.mean(buf["values"])
        cur_std  = statistics.stdev(buf["values"])
        baseline = BASELINE_STATS[feature]
        mean_d   = abs(cur_mean - baseline["mean"]) / (baseline["std"] + 1e-9)
        std_d    = abs(cur_std  - baseline["std"])  / (baseline["std"] + 1e-9)
        drift    = (mean_d + std_d) / 2
        FEATURE_DRIFT_GAUGE.labels(feature_name=feature).set(drift)
        buf["last_update"] = now


def _preprocess(data: List[CustomerFeatures]) -> np.ndarray:
    df = pd.DataFrame([d.dict() for d in data])
    for feature in BASELINE_STATS:
        if feature in df.columns:
            mean_val = df[feature].mean()
            INPUT_FEATURE_GAUGE.labels(feature_name=feature).set(mean_val)
            for v in df[feature].dropna():
                _update_drift(feature, float(v))
    df[SCALE_COLS] = scaler.fit_transform(df[SCALE_COLS])
    return df.values


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/sample")
def sample_data():
    return [{
        "gender": 0, "SeniorCitizen": 0, "Partner": 1, "Dependents": 0,
        "tenure": 72.0, "PhoneService": 1, "MultipleLines": 1,
        "OnlineSecurity": 1, "OnlineBackup": 1, "DeviceProtection": 1,
        "TechSupport": 1, "StreamingTV": 1, "StreamingMovies": 1,
        "PaperlessBilling": 1, "MonthlyCharges": 84.45, "TotalCharges": 6033.35,
        "InternetService_DSL": 1, "InternetService_Fiber_optic": 0, "InternetService_No": 0,
        "Contract_Month_to_month": 0, "Contract_One_year": 0, "Contract_Two_year": 1,
        "PaymentMethod_Bank_transfer_automatic": 0, "PaymentMethod_Credit_card_automatic": 1,
        "PaymentMethod_Electronic_check": 0, "PaymentMethod_Mailed_check": 0,
    }]

@app.post("/predict")
def predict(data: List[CustomerFeatures], db: Session = Depends(get_db)):
    start = time.time()
    try:
        X    = _preprocess(data)
        proba = model.predict_proba(X)[:, 1]
        preds = (proba >= 0.5).astype(int)

        for i, item in enumerate(data):
            db.add(PredictionRecord(**item.dict(), prediction=int(preds[i])))
        db.commit()

        for p in proba:
            PREDICTION_DIST.observe(p)

        churn = int(preds.sum())
        PREDICTION_COUNT.labels(result="churn").inc(churn)
        PREDICTION_COUNT.labels(result="non_churn").inc(len(preds) - churn)
        PREDICTION_LATENCY.observe(time.time() - start)

        return {"predictions": preds.tolist(), "probabilities": proba.tolist()}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/drift")
def get_drift():
    return {f: FEATURE_DRIFT_GAUGE.labels(feature_name=f)._value.get() for f in BASELINE_STATS}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)