"""
serving/app/model_loader.py
Loads the best fraud detection model.
Priority order:
  1. MLflow Model Registry (Production stage)
  2. Local model files (xgboost → lightgbm → isolation forest)
  3. Dummy model (for testing / cold start)
"""

import os
import pickle
import logging
import numpy as np

logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MODEL_DIR           = os.getenv("MODEL_DIR", "/opt/airflow/fraud_detection_pipeline/models")


class _DummyModel:
    """Fallback model — returns random probabilities. Replace in production."""
    def predict_proba(self, X):
        n = X.shape[0]
        probs = np.random.dirichlet(np.ones(2), size=n)
        return probs

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def _load_from_mlflow():
    """Attempt to load the Production model from MLflow registry."""
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.tracking.MlflowClient()

        # Try each experiment in preference order
        for experiment_name in [
            "fraud_detection_xgboost",
            "fraud_detection_lightgbm",
            "fraud_detection_isolation_forest",
        ]:
            exp = client.get_experiment_by_name(experiment_name)
            if not exp:
                continue

            runs = client.search_runs(
                experiment_ids=[exp.experiment_id],
                order_by=["metrics.f1_score DESC"],
                max_results=1,
            )
            if not runs:
                continue

            best_run = runs[0]
            model_uri = f"runs:/{best_run.info.run_id}/model"
            model = mlflow.pyfunc.load_model(model_uri)
            logger.info(f"✓ Model loaded from MLflow — experiment: {experiment_name}")
            return model

    except Exception as e:
        logger.warning(f"MLflow model load failed: {e}")
    return None


def _load_from_local():
    """Attempt to load a model from local files."""
    candidates = [
        ("xgboost",          os.path.join(MODEL_DIR, "xgboost_fraud_model.json")),
        ("lightgbm",         os.path.join(MODEL_DIR, "lightgbm_fraud_model.txt")),
        ("isolation_forest", os.path.join(MODEL_DIR, "isolation_forest_model.pkl")),
    ]

    for name, path in candidates:
        if not os.path.exists(path):
            continue
        try:
            if name == "xgboost":
                import xgboost as xgb
                model = xgb.XGBClassifier()
                model.load_model(path)
                logger.info(f"✓ XGBoost model loaded from {path}")
                return model

            elif name == "lightgbm":
                import lightgbm as lgb
                model = lgb.Booster(model_file=path)
                # Wrap booster so it has predict_proba
                class _LGBWrapper:
                    def __init__(self, booster):
                        self._b = booster
                    def predict_proba(self, X):
                        p = self._b.predict(X)
                        return np.column_stack([1 - p, p])
                    def predict(self, X):
                        return (self._b.predict(X) >= 0.5).astype(int)
                logger.info(f"✓ LightGBM model loaded from {path}")
                return _LGBWrapper(model)

            elif name == "isolation_forest":
                with open(path, "rb") as f:
                    model = pickle.load(f)
                logger.info(f"✓ IsolationForest model loaded from {path}")
                return model

        except Exception as e:
            logger.warning(f"Failed to load {name} from {path}: {e}")

    return None


def load_model():
    """Load model with fallback chain: MLflow → local files → dummy."""
    model = _load_from_mlflow()
    if model:
        return model

    model = _load_from_local()
    if model:
        return model

    logger.warning("⚠️  Using DummyModel — no trained model found!")
    return _DummyModel()
