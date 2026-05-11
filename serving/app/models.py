# serving/app/models.py
"""
SQLAlchemy Database Models
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class PredictionRecord(Base):
    """Store prediction records for monitoring"""
    __tablename__ = 'prediction_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(50), unique=True, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    is_fraud = Column(Boolean, nullable=False)
    fraud_probability = Column(Float, nullable=False)
    xgboost_prob = Column(Float)
    lightgbm_prob = Column(Float)
    isolation_forest_score = Column(Float)
    model_version = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<PredictionRecord(transaction_id={self.transaction_id}, is_fraud={self.is_fraud})>"

class FeatureDriftRecord(Base):
    """Store feature drift metrics"""
    __tablename__ = 'feature_drift_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    feature_name = Column(String(100), nullable=False, index=True)
    drift_score = Column(Float, nullable=False)
    p_value = Column(Float)
    psi_value = Column(Float)
    is_drifted = Column(Boolean, default=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)

def get_engine():
    """Create database engine"""
    db_url = os.getenv('DATABASE_URL', 'postgresql://user:pass@localhost:5432/fraud_detection')
    return create_engine(db_url)

def init_db():
    """Initialize database tables"""
    engine = get_engine()
    Base.metadata.create_all(engine)
    
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()