# monitoring/prometheus_drift/main.py
"""
FastAPI with Prometheus Drift Metrics
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from starlette.responses import Response
from sqlalchemy.orm import Session
import numpy as np
from datetime import datetime
import random

from .models import get_db, init_db
from .drift_simulator import DriftSimulator

app = FastAPI(title="Fraud Detection with Drift Monitoring")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus Drift Metrics
FEATURE_DRIFT_GAUGE = Gauge(
    'feature_drift_score',
    'Feature drift score (PSI-based)',
    ['feature_name']
)

CONCEPT_DRIFT_GAUGE = Gauge(
    'concept_drift_score',
    'Concept drift score',
    ['model_name']
)

PREDICTION_DRIFT_COUNTER = Counter(
    'prediction_drift_detected_total',
    'Total number of drift detections',
    ['drift_type', 'severity']
)

PREDICTION_LATENCY = Histogram(
    'prediction_latency_seconds',
    'Prediction latency'
)

# Initialize drift simulator
drift_simulator = DriftSimulator()

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "drift_phase": drift_simulator.current_phase
    }

@app.post("/predict")
async def predict(transaction_data: dict):
    """Prediction endpoint with drift tracking"""
    # Simulate prediction with current drift conditions
    base_probability = transaction_data.get('amount', 100) / 1000
    
    # Apply drift adjustments
    if drift_simulator.current_phase > 1:
        # Feature drift effect
        drift_factor = drift_simulator.get_feature_drift_factor()
        base_probability *= drift_factor
    
    if drift_simulator.current_phase == 3:
        # Concept drift effect
        base_probability = min(1.0, base_probability * 1.5)
    
    # Add some randomness
    probability = min(1.0, max(0.0, base_probability + random.uniform(-0.1, 0.1)))
    is_fraud = int(probability > 0.5)
    
    return {
        "transaction_id": transaction_data.get('transaction_id'),
        "is_fraud": is_fraud,
        "probability": round(probability, 4),
        "drift_phase": drift_simulator.current_phase
    }

@app.get("/drift-status")
async def drift_status():
    """Get current drift status"""
    return {
        "current_phase": drift_simulator.current_phase,
        "phase_description": drift_simulator.get_phase_description(),
        "feature_drift_scores": drift_simulator.get_feature_drift_scores(),
        "concept_drift_score": drift_simulator.get_concept_drift_score()
    }

@app.post("/drift-trigger-phase")
async def trigger_phase(phase: int):
    """Manually trigger a drift phase (1-4)"""
    if phase < 1 or phase > 4:
        raise HTTPException(status_code=400, detail="Phase must be 1-4")
    
    drift_simulator.set_phase(phase)
    return {"status": "success", "new_phase": phase}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    # Update drift metrics
    for feature, score in drift_simulator.get_feature_drift_scores().items():
        FEATURE_DRIFT_GAUGE.labels(feature_name=feature).set(score)
    
    CONCEPT_DRIFT_GAUGE.labels(model_name='ensemble').set(
        drift_simulator.get_concept_drift_score()
    )
    
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )

@app.get("/drift-history")
async def drift_history(db: Session = Depends(get_db)):
    """Get drift history from database"""
    from .models import FeatureDriftRecord
    
    records = db.query(FeatureDriftRecord).order_by(
        FeatureDriftRecord.recorded_at.desc()
    ).limit(100).all()
    
    return [
        {
            "feature_name": r.feature_name,
            "drift_score": r.drift_score,
            "is_drifted": r.is_drifted,
            "recorded_at": r.recorded_at.isoformat()
        }
        for r in records
    ]
