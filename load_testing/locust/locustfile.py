# load_testing/locust/locustfile.py
"""
Locust Load Testing for Fraud Detection API
"""
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner
import random
import numpy as np

class MLModelUser(HttpUser):
    """Standard user making occasional predictions"""
    wait_time = between(1, 3)
    
    @task(3)
    def predict_normal(self):
        """Normal transaction prediction"""
        payload = {
            "transaction_id": f"txn_{random.randint(1000000, 9999999)}",
            "amount": random.uniform(10, 500),
            "time_since_last_transaction": random.uniform(60, 3600),
            "transaction_velocity": random.uniform(0.1, 2.0),
            "user_risk_score": random.uniform(0, 0.3),
            "account_age_days": random.randint(30, 3650),
            "merchant_fraud_rate": random.uniform(0, 0.05)
        }
        self.client.post("/predict", json=payload)
    
    @task(1)
    def health_check(self):
        """Check API health"""
        self.client.get("/health")

class HeavyUser(HttpUser):
    """User making many predictions for batch processing"""
    wait_time = between(0.5, 1)
    
    @task
    def batch_predict(self):
        """Batch prediction of 100 transactions"""
        transactions = [
            {
                "transaction_id": f"txn_{random.randint(1000000, 9999999)}",
                "amount": random.uniform(10, 500),
                "time_since_last_transaction": random.uniform(60, 3600),
                "transaction_velocity": random.uniform(0.1, 2.0),
                "user_risk_score": random.uniform(0, 0.3),
                "account_age_days": random.randint(30, 3650),
                "merchant_fraud_rate": random.uniform(0, 0.05)
            }
            for _ in range(100)
        ]
        self.client.post("/batch-predict", json={"transactions": transactions})

class LightUser(HttpUser):
    """Light user with sporadic usage"""
    wait_time = between(10, 30)
    
    @task
    def occasional_prediction(self):
        """Occasional prediction"""
        payload = {
            "transaction_id": f"txn_{random.randint(1000000, 9999999)}",
            "amount": random.uniform(50, 200),
            "time_since_last_transaction": random.uniform(300, 1800),
            "transaction_velocity": random.uniform(0.5, 1.5),
            "user_risk_score": random.uniform(0.1, 0.4),
            "account_age_days": random.randint(100, 1000),
            "merchant_fraud_rate": random.uniform(0.01, 0.1)
        }
        self.client.post("/predict", json=payload)

class BurstUser(HttpUser):
    """User generating burst traffic"""
    wait_time = between(0.1, 0.5)
    
    @task
    def burst_prediction(self):
        """Burst of predictions"""
        payload = {
            "transaction_id": f"txn_{random.randint(1000000, 9999999)}",
            "amount": random.uniform(100, 1000),
            "time_since_last_transaction": random.uniform(10, 300),
            "transaction_velocity": random.uniform(1.0, 5.0),
            "user_risk_score": random.uniform(0.2, 0.6),
            "account_age_days": random.randint(1, 365),
            "merchant_fraud_rate": random.uniform(0.05, 0.2)
        }
        self.client.post("/predict", json=payload)

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts"""
    print("Load test starting...")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops"""
    print("Load test completed!")

# Configure for distributed testing
class FraudDetectionUser(HttpUser):
    """Default user combining various behaviors"""
    wait_time = between(1, 5)
    
    def on_start(self):
        """Called when user starts"""
        self.user_id = random.randint(1, 10000)
    
    @task(10)
    def predict_transaction(self):
        """Standard prediction"""
        amount = np.random.lognormal(mean=4.5, sigma=1.0)
        
        payload = {
            "transaction_id": f"user_{self.user_id}_txn_{random.randint(1, 10000)}",
            "amount": round(amount, 2),
            "time_since_last_transaction": random.uniform(30, 7200),
            "transaction_velocity": random.uniform(0.1, 3.0),
            "user_risk_score": random.uniform(0, 1),
            "account_age_days": random.randint(1, 3650),
            "merchant_fraud_rate": random.uniform(0, 0.3)
        }
        
        with self.client.post("/predict", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")
    
    @task(2)
    def batch_predict_small(self):
        """Small batch prediction"""
        transactions = [
            {
                "transaction_id": f"user_{self.user_id}_txn_{i}",
                "amount": round(random.uniform(10, 500), 2),
                "time_since_last_transaction": random.uniform(60, 3600),
                "transaction_velocity": random.uniform(0.1, 2.0),
                "user_risk_score": random.uniform(0, 1),
                "account_age_days": random.randint(30, 3650),
                "merchant_fraud_rate": random.uniform(0, 0.3)
            }
            for i in range(10)
        ]
        
        self.client.post("/batch-predict", json={"transactions": transactions})
    
    @task(1)
    def check_metrics(self):
        """Check Prometheus metrics"""
        self.client.get("/metrics")
    
    @task(1)
    def get_model_info(self):
        """Get model information"""
        self.client.get("/model-info")