"""
serving/app/models.py
SQLAlchemy ORM model for logging predictions to PostgreSQL.
Each row represents one fraud prediction request.
"""

from sqlalchemy import create_engine, Column, Integer, Float, DateTime, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://my_user:my_password@postgres:5432/my_db"
)

engine       = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


class PredictionRecord(Base):
    __tablename__ = "fraud_predictions"

    id             = Column(Integer, primary_key=True, index=True)
    TransactionAmt = Column(Float,   nullable=True)
    card1          = Column(Integer, nullable=True)
    card2          = Column(Float,   nullable=True)
    card3          = Column(Float,   nullable=True)
    card5          = Column(Float,   nullable=True)
    addr1          = Column(Float,   nullable=True)
    addr2          = Column(Float,   nullable=True)
    dist1          = Column(Float,   nullable=True)
    dist2          = Column(Float,   nullable=True)
    C1             = Column(Float,   nullable=True)
    C2             = Column(Float,   nullable=True)
    C3             = Column(Float,   nullable=True)
    C4             = Column(Float,   nullable=True)
    C5             = Column(Float,   nullable=True)
    C6             = Column(Float,   nullable=True)
    C7             = Column(Float,   nullable=True)
    C8             = Column(Float,   nullable=True)
    C9             = Column(Float,   nullable=True)
    C10            = Column(Float,   nullable=True)
    C11            = Column(Float,   nullable=True)
    C12            = Column(Float,   nullable=True)
    C13            = Column(Float,   nullable=True)
    C14            = Column(Float,   nullable=True)
    D1             = Column(Float,   nullable=True)
    D2             = Column(Float,   nullable=True)
    D3             = Column(Float,   nullable=True)
    D4             = Column(Float,   nullable=True)
    D5             = Column(Float,   nullable=True)
    prediction     = Column(Integer, nullable=False)
    probability    = Column(Float,   nullable=False)
    model_version  = Column(String,  default="1.0.0")
    created_at     = Column(DateTime, default=datetime.utcnow)


def create_tables():
    Base.metadata.create_all(bind=engine)