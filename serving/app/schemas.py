# serving/app/schemas.py
"""
Pydantic Request/Response Schemas
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime

class TransactionFeatures(BaseModel):
    """Input features for a single transaction"""
    transaction_id: str = Field(..., description="Unique transaction identifier")
    amount: float = Field(..., gt=0, description="Transaction amount")
    time_since_last_transaction: float = Field(..., ge=0, description="Time since last transaction in seconds")
    transaction_velocity: float = Field(..., ge=0, description="Transaction velocity metric")
    user_risk_score: float = Field(..., ge=0, le=1, description="User risk score (0-1)")
    account_age_days: int = Field(..., ge=0, description="Account age in days")
    merchant_fraud_rate: float = Field(..., ge=0, le=1, description="Merchant historical fraud rate")

class PredictionRequest(TransactionFeatures):
    """Single prediction request"""
    pass

class TransactionFeaturesBatch(TransactionFeatures):
    """Transaction with additional batch features"""
    hour_of_day: Optional[int] = Field(None, ge=0, le=23)
    is_weekend: Optional[bool] = False
    country_risk_score: Optional[float] = Field(None, ge=0, le=1)

class BatchPredictionRequest(BaseModel):
    """Batch prediction request"""
    transactions: List[TransactionFeatures] = Field(..., description="List of transactions to predict")
    model_name: Optional[str] = Field(None, description="Specific model to use (optional)")

class PredictionResponse(BaseModel):
    """Prediction response"""
    transaction_id: str
    is_fraud: int = Field(..., description="0 = legitimate, 1 = fraudulent")
    fraud_probability: float = Field(..., ge=0, le=1, description="Ensemble fraud probability")
    individual_predictions: Dict[str, int] = Field(..., description="Predictions from each model")
    individual_probabilities: Dict[str, float] = Field(..., description="Probabilities from each model")
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)

class ModelInfo(BaseModel):
    """Model information"""
    name: str
    version: str
    type: str  # 'xgboost', 'lightgbm', 'isolation_forest'
    last_trained: Optional[datetime]

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: datetime
    models_loaded: List[str]