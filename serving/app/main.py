# serving/app/main.py
"""
FastAPI Model Serving Application
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
from typing import List
import joblib
import boto3
from datetime import datetime

from .schemas import PredictionRequest, BatchPredictionRequest, PredictionResponse
from .model_loader import ModelLoader
from .models import PredictionRecord
from sqlalchemy.orm import Session

app = FastAPI(title="Fraud Detection API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
REQUEST_COUNT = Counter(
    'fraud_prediction_requests_total',
    'Total number of fraud prediction requests',
    ['model', 'status']
)

REQUEST_LATENCY = Histogram(
    'fraud_prediction_latency_seconds',
    'Prediction latency in seconds',
    ['model']
)

# Initialize model loader
model_loader = ModelLoader()

@app.on_event("startup")
async def startup_event():
    """Load models on startup"""
    model_loader.load_models()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "models_loaded": list(model_loader.models.keys())
    }

@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """Single transaction prediction"""
    start_time = datetime.utcnow()
    
    try:
        # Prepare features
        features = np.array([[
            request.amount,
            request.time_since_last_transaction,
            request.transaction_velocity,
            request.user_risk_score,
            request.account_age_days,
            request.merchant_fraud_rate
        ]])
        
        # Get predictions from all models
        predictions = {}
        probabilities = {}
        
        for model_name, model_info in model_loader.models.items():
            model = model_info['model']
            
            if model_name == 'xgboost':
                prob = model.predict_proba(features)[0][1]
            elif model_name == 'lightgbm':
                prob = model.predict(features)[0]
            elif model_name == 'isolation_forest':
                # Anomaly score: lower = more anomalous
                score = model.decision_function(features)[0]
                prob = 1 / (1 + np.exp(score))  # Convert to probability-like
            else:
                prob = 0.5
            
            predictions[model_name] = int(prob > 0.5)
            probabilities[model_name] = float(prob)
        
        # Ensemble prediction (weighted average)
        ensemble_prob = (
            0.4 * probabilities.get('xgboost', 0.5) +
            0.4 * probabilities.get('lightgbm', 0.5) +
            0.2 * probabilities.get('isolation_forest', 0.5)
        )
        ensemble_prediction = int(ensemble_prob > 0.5)
        
        # Record metrics
        latency = (datetime.utcnow() - start_time).total_seconds()
        REQUEST_LATENCY.labels(model='ensemble').observe(latency)
        REQUEST_COUNT.labels(model='ensemble', status='success').inc()
        
        return PredictionResponse(
            transaction_id=request.transaction_id,
            is_fraud=ensemble_prediction,
            fraud_probability=ensemble_prob,
            individual_predictions=predictions,
            individual_probabilities=probabilities
        )
    
    except Exception as e:
        REQUEST_COUNT.labels(model='ensemble', status='error').inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/batch-predict")
async def batch_predict(request: BatchPredictionRequest):
    """Batch transaction prediction"""
    start_time = datetime.utcnow()
    
    try:
        results = []
        
        for transaction in request.transactions:
            # Create prediction request for each transaction
            pred_request = PredictionRequest(
                transaction_id=transaction.transaction_id,
                amount=transaction.amount,
                time_since_last_transaction=transaction.time_since_last_transaction,
                transaction_velocity=transaction.transaction_velocity,
                user_risk_score=transaction.user_risk_score,
                account_age_days=transaction.account_age_days,
                merchant_fraud_rate=transaction.merchant_fraud_rate
            )
            
            # Single prediction
            pred_response = await predict(pred_request)
            results.append(pred_response)
        
        latency = (datetime.utcnow() - start_time).total_seconds()
        REQUEST_LATENCY.labels(model='batch').observe(latency)
        
        return {
            "predictions": results,
            "count": len(results),
            "processing_time_seconds": latency
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )

@app.get("/model-info")
async def model_info():
    """Get information about loaded models"""
    return {
        "models": model_loader.model_info(),
        "last_updated": model_loader.last_updated.isoformat() if model_loader.last_updated else None
    }