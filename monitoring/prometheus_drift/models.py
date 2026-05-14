"""
monitoring/prometheus_drift/models.py
SQLAlchemy ORM for logging churn predictions to PostgreSQL.
"""

from sqlalchemy import create_engine, Column, Integer, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://my_user:my_password@postgres/my_db")

engine       = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


class PredictionRecord(Base):
    __tablename__ = "predictions"

    id                                    = Column(Integer, primary_key=True, index=True)
    gender                                = Column(Integer)
    SeniorCitizen                         = Column(Integer)
    Partner                               = Column(Integer)
    Dependents                            = Column(Integer)
    tenure                                = Column(Float)
    PhoneService                          = Column(Integer)
    MultipleLines                         = Column(Integer)
    OnlineSecurity                        = Column(Integer)
    OnlineBackup                          = Column(Integer)
    DeviceProtection                      = Column(Integer)
    TechSupport                           = Column(Integer)
    StreamingTV                           = Column(Integer)
    StreamingMovies                       = Column(Integer)
    PaperlessBilling                      = Column(Integer)
    MonthlyCharges                        = Column(Float)
    TotalCharges                          = Column(Float)
    InternetService_DSL                   = Column(Integer)
    InternetService_Fiber_optic           = Column(Integer)
    InternetService_No                    = Column(Integer)
    Contract_Month_to_month               = Column(Integer)
    Contract_One_year                     = Column(Integer)
    Contract_Two_year                     = Column(Integer)
    PaymentMethod_Bank_transfer_automatic = Column(Integer)
    PaymentMethod_Credit_card_automatic   = Column(Integer)
    PaymentMethod_Electronic_check        = Column(Integer)
    PaymentMethod_Mailed_check            = Column(Integer)
    prediction                            = Column(Integer)


def create_tables():
    Base.metadata.create_all(bind=engine)