# serving/app/model_loader.py
"""
Model Loader - Load models from S3 or MLflow Registry
"""
import joblib
import boto3
import mlflow
from datetime import datetime
from typing import Dict, Any
import os

class ModelLoader:
    """Load and manage fraud detection models"""
    
    def __init__(self):
        self.models: Dict[str, Dict[str, Any]] = {}
        self.last_updated: datetime = None
        self.s3_bucket = os.getenv('MODEL_BUCKET', 'mlops-fraud-detection-models')
        self.mlflow_tracking_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
    
    def load_models(self):
        """Load all models from S3 or MLflow"""
        mlflow.set_tracking_uri(self.mlflow_tracking_uri)
        
        # Load XGBoost model
        self._load_xgboost()
        
        # Load LightGBM model
        self._load_lightgbm()
        
        # Load Isolation Forest model
        self._load_isolation_forest()
        
        self.last_updated = datetime.utcnow()
    
    def _load_xgboost(self):
        """Load XGBoost model"""
        try:
            # Try MLflow first
            model_uri = "models:/fraud-xgboost/production"
            model = mlflow.xgboost.load_model(model_uri)
            self.models['xgboost'] = {
                'model': model,
                'source': 'mlflow',
                'type': 'xgboost'
            }
        except Exception as e:
            print(f"MLflow load failed for XGBoost: {e}")
            # Fallback to local file
            try:
                self.models['xgboost'] = {
                    'model': joblib.load('/models/xgboost_fraud_model.json'),
                    'source': 'local',
                    'type': 'xgboost'
                }
            except Exception as e2:
                print(f"Local load also failed: {e2}")
                # Fallback to S3
                self._load_from_s3('xgboost', 'xgboost_fraud_model.json')
    
    def _load_lightgbm(self):
        """Load LightGBM model"""
        try:
            model_uri = "models:/fraud-lightgbm/production"
            model = mlflow.lightgbm.load_model(model_uri)
            self.models['lightgbm'] = {
                'model': model,
                'source': 'mlflow',
                'type': 'lightgbm'
            }
        except Exception as e:
            print(f"MLflow load failed for LightGBM: {e}")
            try:
                import lightgbm as lgb
                self.models['lightgbm'] = {
                    'model': lgb.Booster(model_file='/models/lightgbm_fraud_model.txt'),
                    'source': 'local',
                    'type': 'lightgbm'
                }
            except Exception as e2:
                print(f"Local load also failed: {e2}")
                self._load_from_s3('lightgbm', 'lightgbm_fraud_model.txt')
    
    def _load_isolation_forest(self):
        """Load Isolation Forest model"""
        try:
            model_uri = "models:/fraud-isolation-forest/production"
            model = mlflow.sklearn.load_model(model_uri)
            self.models['isolation_forest'] = {
                'model': model,
                'source': 'mlflow',
                'type': 'isolation_forest'
            }
        except Exception as e:
            print(f"MLflow load failed for Isolation Forest: {e}")
            try:
                self.models['isolation_forest'] = {
                    'model': joblib.load('/models/isolation_forest_model.pkl'),
                    'source': 'local',
                    'type': 'isolation_forest'
                }
            except Exception as e2:
                print(f"Local load also failed: {e2}")
                self._load_from_s3('isolation_forest', 'isolation_forest_model.pkl')
    
    def _load_from_s3(self, model_name: str, file_name: str):
        """Load model from S3"""
        s3_client = boto3.client('s3')
        
        try:
            local_path = f'/tmp/{file_name}'
            s3_client.download_file(
                self.s3_bucket,
                f'models/{file_name}',
                local_path
            )
            
            if file_name.endswith('.pkl'):
                model = joblib.load(local_path)
            else:
                model = joblib.load(local_path)
            
            self.models[model_name] = {
                'model': model,
                'source': 's3',
                'type': model_name
            }
        except Exception as e:
            print(f"S3 load failed for {model_name}: {e}")
    
    def model_info(self) -> Dict[str, Any]:
        """Get information about loaded models"""
        return {
            name: {
                'source': info['source'],
                'type': info['type'],
                'loaded': True
            }
            for name, info in self.models.items()
        }
    
    def reload_models(self):
        """Reload all models"""
        self.models = {}
        self.load_models()