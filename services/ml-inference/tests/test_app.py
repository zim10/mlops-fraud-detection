"""
services/ml-inference/tests/test_app.py
Unit tests for the ML inference Flask service.
Runs without starting a real server — uses Flask test client.
"""

import sys
import os
import json
import unittest

# Make sure the parent directory is on the path so `app` can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app


class TestMLInference(unittest.TestCase):

    def setUp(self):
        self.client         = app.test_client()
        app.config["TESTING"] = True

    # ── /health ──────────────────────────────────────────────────────────────

    def test_health_returns_200(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_health_body(self):
        resp = self.client.get("/health")
        data = json.loads(resp.data)
        self.assertEqual(data["status"],  "healthy")
        self.assertEqual(data["service"], "ml-inference")

    # ── /predict ─────────────────────────────────────────────────────────────

    def test_predict_valid_input(self):
        payload = {"features": [1.0, 2.0, 3.0, 4.0]}
        resp    = self.client.post(
            "/predict",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_predict_response_structure(self):
        payload = {"features": [0.5, -0.2, 1.3, 0.7]}
        resp    = self.client.post(
            "/predict",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = json.loads(resp.data)
        self.assertIn("prediction",    data)
        self.assertIn("model_version", data)
        self.assertIn("timestamp",     data)

    def test_predict_value_range(self):
        payload = {"features": [1.0, 2.0, 3.0]}
        resp    = self.client.post(
            "/predict",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = json.loads(resp.data)
        self.assertGreaterEqual(data["prediction"], 0.0)
        self.assertLessEqual(   data["prediction"], 1.0)

    def test_predict_missing_features_key(self):
        resp = self.client.post(
            "/predict",
            data=json.dumps({"wrong_key": [1, 2, 3]}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_predict_empty_body(self):
        resp = self.client.post(
            "/predict",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_predict_no_body(self):
        resp = self.client.post("/predict")
        self.assertEqual(resp.status_code, 400)

    # ── /metrics ─────────────────────────────────────────────────────────────

    def test_metrics_returns_200(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)

    def test_metrics_contains_prediction_counter(self):
        # Make a prediction first so the counter is non-zero
        self.client.post(
            "/predict",
            data=json.dumps({"features": [1.0, 2.0]}),
            content_type="application/json",
        )
        resp = self.client.get("/metrics")
        self.assertIn(b"ml_predictions_total", resp.data)

    def test_metrics_contains_duration_histogram(self):
        resp = self.client.get("/metrics")
        self.assertIn(b"ml_prediction_duration_seconds", resp.data)


if __name__ == "__main__":
    unittest.main()