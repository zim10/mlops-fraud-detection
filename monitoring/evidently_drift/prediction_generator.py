# monitoring/evidently_drift/prediction_generator.py
"""
Generate Synthetic Predictions for Testing
"""
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import random
import numpy as np
from typing import List

class PredictionGenerator:
    """Generate synthetic prediction records for testing"""
    
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
    
    def generate_transaction(self, transaction_id: str, timestamp: datetime) -> dict:
        """Generate a single synthetic transaction"""
        # Simulate realistic fraud patterns
        is_fraud = random.random() < 0.03  # 3% fraud rate
        
        amount = np.random.lognormal(mean=4.5, sigma=1.2)
        if is_fraud:
            amount *= random.uniform(2, 5)  # Fraudulent transactions often larger
        
        return {
            'transaction_id': transaction_id,
            'amount': round(amount, 2),
            'is_fraud': is_fraud,
            'fraud_probability': round(min(1.0, random.uniform(0.0, 0.3) + (0.5 if is_fraud else 0)), 4),
            'time_since_last_transaction': random.uniform(10, 7200),
            'user_risk_score': random.uniform(0, 1) if not is_fraud else random.uniform(0.5, 1),
            'account_age_days': random.randint(1, 3650) if not is_fraud else random.randint(1, 180),
            'merchant_fraud_rate': random.uniform(0, 0.1) if not is_fraud else random.uniform(0.1, 0.4),
            'created_at': timestamp
        }
    
    def generate_batch(self, count: int, start_date: datetime = None) -> List[dict]:
        """Generate a batch of transactions"""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=7)
        
        transactions = []
        current_time = start_date
        
        for i in range(count):
            transaction_id = f"generated_txn_{start_date.strftime('%Y%m%d')}_{i:06d}"
            
            transaction = self.generate_transaction(
                transaction_id,
                current_time
            )
            transactions.append(transaction)
            
            # Time between transactions (1-30 seconds)
            current_time += timedelta(seconds=random.randint(1, 30))
        
        return transactions
    
    def save_to_database(self, transactions: List[dict]):
        """Save transactions to database"""
        df = pd.DataFrame(transactions)
        df.to_sql(
            'prediction_records',
            self.engine,
            if_exists='append',
            index=False,
            method='multi',
            chunksize=1000
        )
        
        print(f"Saved {len(transactions)} prediction records to database")
    
    def generate_for_days(self, days: int, transactions_per_day: int = 10000):
        """Generate data for multiple days"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        for day in range(days):
            current_date = start_date + timedelta(days=day)
            transactions = self.generate_batch(
                transactions_per_day,
                start_date=current_date.replace(hour=0, minute=0, second=0)
            )
            self.save_to_database(transactions)
        
        print(f"Generated {days * transactions_per_day} records")

if __name__ == "__main__":
    db_url = "postgresql://fraud:password@localhost:5432/fraud_detection"
    generator = PredictionGenerator(db_url)
    
    # Generate 7 days of data
    generator.generate_for_days(days=7, transactions_per_day=1000)