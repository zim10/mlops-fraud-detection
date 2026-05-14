"""
serving/app/schemas.py
Pydantic request / response schemas for the fraud detection API.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class FraudInput(BaseModel):
    """Single transaction feature payload."""
    TransactionAmt: float = Field(..., description="Transaction amount in USD")
    card1:          Optional[int]   = None
    card2:          Optional[float] = None
    card3:          Optional[float] = None
    card5:          Optional[float] = None
    addr1:          Optional[float] = None
    addr2:          Optional[float] = None
    dist1:          Optional[float] = None
    dist2:          Optional[float] = None
    C1:             Optional[float] = None
    C2:             Optional[float] = None
    C3:             Optional[float] = None
    C4:             Optional[float] = None
    C5:             Optional[float] = None
    C6:             Optional[float] = None
    C7:             Optional[float] = None
    C8:             Optional[float] = None
    C9:             Optional[float] = None
    C10:            Optional[float] = None
    C11:            Optional[float] = None
    C12:            Optional[float] = None
    C13:            Optional[float] = None
    C14:            Optional[float] = None
    D1:             Optional[float] = None
    D2:             Optional[float] = None
    D3:             Optional[float] = None
    D4:             Optional[float] = None
    D5:             Optional[float] = None
    M1:             Optional[int]   = None
    M2:             Optional[int]   = None
    M3:             Optional[int]   = None
    M4:             Optional[int]   = None
    M5:             Optional[int]   = None
    M6:             Optional[int]   = None
    M7:             Optional[int]   = None
    M8:             Optional[int]   = None
    M9:             Optional[int]   = None
    amt_per_card:   Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "TransactionAmt": 49.0,
                "card1": 2755,
                "C1": 1.0,
                "C2": 1.0,
                "D1": 14.0,
            }
        }


class FraudPrediction(BaseModel):
    """Prediction response for a single transaction."""
    prediction:    int   = Field(..., description="0 = not fraud, 1 = fraud")
    probability:   float = Field(..., description="Probability of fraud (0.0 – 1.0)")
    model_version: str   = Field(default="1.0.0")


class BatchFraudInput(BaseModel):
    """Batch prediction request — list of transactions."""
    transactions: List[FraudInput]


class BatchFraudPrediction(BaseModel):
    """Batch prediction response."""
    predictions: List[FraudPrediction]
    count:       int
