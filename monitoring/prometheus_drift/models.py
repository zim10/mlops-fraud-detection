# monitoring/prometheus_drift/models.py
"""
SQLAlchemy Models for Drift Monitoring
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class PredictionRecord(Base):
    """Store prediction records"""
    __tablename__ = 'prediction_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(50), unique=True, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    is_fraud = Column(Boolean, nullable=False)
    fraud_probability = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

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
    db_url = os.getenv('DATABASE_URL', 'postgresql://fraud:password@postgres:5432/fraud_detection')
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