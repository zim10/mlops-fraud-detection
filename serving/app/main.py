"""
serving/app/main.py
FastAPI inference service for the fraud detection model.
Loads the best model from MLflow registry (or local fallback),
validates input with Pydantic, logs predictions to PostgreSQL,
and exposes Prometheus metrics + drift scores.
"""

import os
import time
import json
import logging
import statistics
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
)

from .schemas import FraudInput, FraudPrediction, BatchFraudInput, BatchFraudPrediction
from .models import SessionLocal, PredictionRecord, create_tables
from .model_loader import load_model

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────
PREDICTION_COUNT    = Counter("fraud_predictions_total",         "Total predictions",         ["result"])
PREDICTION_LATENCY  = Histogram("fraud_prediction_latency_seconds", "Prediction latency",
                                buckets=[0.05, 0.1, 0.2, 0.5, 1, 2, 5])
BATCH_SIZE_HIST     = Histogram("fraud_batch_size",              "Batch prediction size")
FEATURE_DRIFT_GAUGE = Gauge("fraud_feature_drift",               "Feature drift score", ["feature_name"])
ACTIVE_REQUESTS     = Gauge("fraud_active_requests",             "In-flight requests")
ERROR_COUNTER       = Counter("fraud_prediction_errors_total",   "Prediction errors",   ["error_type"])

# Baseline stats (from training data distribution)
BASELINE_STATS = {
    "TransactionAmt": {"mean": 134.5,  "std": 215.0},
    "C1":             {"mean": 1.0,    "std": 1.5},
    "D1":             {"mean": 200.0,  "std": 150.0},
}
_feature_buffers = {f: {"values": [], "last_update": datetime.now()} for f in BASELINE_STATS}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Fraud Detection API",
    description="Real-time fraud prediction service with drift monitoring",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ── Model (loaded at startup) ─────────────────────────────────────────────────
model = None


@app.on_event("startup")
def startup_event():
    global model
    logger.info("Loading model...")
    model = load_model()
    logger.info("Creating DB tables...")
    create_tables()
    logger.info("✓ Startup complete")


# ── DB dependency ─────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Drift helpers ─────────────────────────────────────────────────────────────
def _update_drift(feature: str, value: float):
    buf = _feature_buffers[feature]
    buf["values"].append(value)
    if len(buf["values"]) > 500:
        buf["values"] = buf["values"][-500:]

    now = datetime.now()
    if (now - buf["last_update"]).total_seconds() > 60 and len(buf["values"]) > 1:
        cur_mean = statistics.mean(buf["values"])
        cur_std  = statistics.stdev(buf["values"])
        baseline = BASELINE_STATS[feature]
        drift    = (abs(cur_mean - baseline["mean"]) / (baseline["std"] + 1e-9) +
                    abs(cur_std  - baseline["std"])  / (baseline["std"] + 1e-9)) / 2
        FEATURE_DRIFT_GAUGE.labels(feature_name=feature).set(round(drift, 4))
        buf["last_update"] = now


def _track_features(df: pd.DataFrame):
    for feature in BASELINE_STATS:
        if feature in df.columns:
            for val in df[feature].dropna():
                _update_drift(feature, float(val))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Fraud Detection API", "docs": "/docs", "metrics": "/metrics"}


@app.get("/health")
def health():
    return {"status": "healthy", "service": "fraud-detection-api", "model_loaded": model is not None}


@app.post("/predict", response_model=FraudPrediction)
def predict(payload: FraudInput, db: Session = Depends(get_db)):
    """Single transaction fraud prediction."""
    ACTIVE_REQUESTS.inc()
    start = time.time()
    try:
        df = pd.DataFrame([payload.dict()])
        _track_features(df)

        features = df.select_dtypes(include=[np.number]).fillna(0).values
        prob     = float(model.predict_proba(features)[0][1])
        label    = int(prob >= 0.5)

        PREDICTION_COUNT.labels(result="fraud" if label else "non_fraud").inc()
        PREDICTION_LATENCY.observe(time.time() - start)

        # Persist to PostgreSQL
        record = PredictionRecord(**payload.dict(), prediction=label, probability=prob)
        db.add(record)
        db.commit()

        return FraudPrediction(prediction=label, probability=prob, model_version="1.0.0")

    except Exception as e:
        ERROR_COUNTER.labels(error_type=type(e).__name__).inc()
        db.rollback()
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ACTIVE_REQUESTS.dec()


@app.post("/batch-predict", response_model=BatchFraudPrediction)
def batch_predict(payload: BatchFraudInput, db: Session = Depends(get_db)):
    """Batch fraud predictions."""
    ACTIVE_REQUESTS.inc()
    start = time.time()
    try:
        df = pd.DataFrame([r.dict() for r in payload.transactions])
        _track_features(df)
        BATCH_SIZE_HIST.observe(len(df))

        features = df.select_dtypes(include=[np.number]).fillna(0).values
        probs    = model.predict_proba(features)[:, 1]
        labels   = (probs >= 0.5).astype(int)

        results = []
        for i, (label, prob) in enumerate(zip(labels, probs)):
            results.append(FraudPrediction(prediction=int(label), probability=float(prob), model_version="1.0.0"))
            record = PredictionRecord(**payload.transactions[i].dict(), prediction=int(label), probability=float(prob))
            db.add(record)

        db.commit()
        PREDICTION_LATENCY.observe(time.time() - start)

        return BatchFraudPrediction(predictions=results, count=len(results))

    except Exception as e:
        ERROR_COUNTER.labels(error_type=type(e).__name__).inc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ACTIVE_REQUESTS.dec()


@app.get("/drift")
def get_drift():
    """Return current feature drift scores."""
    scores = {}
    for feature in BASELINE_STATS:
        try:
            scores[feature] = FEATURE_DRIFT_GAUGE.labels(feature_name=feature)._value.get()
        except Exception:
            scores[feature] = 0.0
    return scores


@app.get("/model-info")
def model_info():
    return {
        "model_version": "1.0.0",
        "model_type": "XGBoost / LightGBM / IsolationForest (best by F1)",
        "features_expected": "numeric fraud detection features",
        "endpoints": ["/predict", "/batch-predict", "/drift", "/health", "/metrics"],
    }


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)