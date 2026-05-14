"""
services/ml-inference/app.py
Flask microservice — ML inference service for the CI/CD pipeline.
Exposes /health, /predict, and /metrics (Prometheus) on port 8001.
Uses a simple DummyModel; swap in your real model for production.
"""

import time
import logging
import numpy as np
from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────
prediction_counter  = Counter(
    "ml_predictions_total",
    "Total number of predictions made",
)
prediction_duration = Histogram(
    "ml_prediction_duration_seconds",
    "Time spent processing a prediction request",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# ── Model ─────────────────────────────────────────────────────────────────────

class DummyModel:
    """
    Placeholder model that returns a random probability.
    Replace with:
        import pickle
        with open("model.pkl", "rb") as f:
            model = pickle.load(f)
    """
    def predict(self, features: list) -> float:
        time.sleep(0.05)                    # Simulate inference latency
        return float(np.random.random())    # Random probability [0, 1]


model = DummyModel()

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    """Liveness / readiness probe."""
    return jsonify({"status": "healthy", "service": "ml-inference"}), 200


@app.route("/predict", methods=["POST"])
def predict():
    """
    Accepts JSON body: {"features": [f1, f2, ...]}
    Returns:           {"prediction": float, "model_version": str, "timestamp": float}
    """
    start_time = time.time()

    data = request.get_json(silent=True)
    if not data or "features" not in data:
        return jsonify({"error": "No features provided"}), 400

    features = data["features"]
    logger.info(f"Prediction request — {len(features)} feature(s)")

    try:
        prediction = model.predict(features)

        prediction_counter.inc()
        prediction_duration.observe(time.time() - start_time)

        return jsonify({
            "prediction":    prediction,
            "model_version": "1.0.0",
            "timestamp":     time.time(),
        }), 200

    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/metrics", methods=["GET"])
def metrics():
    """Prometheus scrape endpoint."""
    try:
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        return "Metrics unavailable", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)