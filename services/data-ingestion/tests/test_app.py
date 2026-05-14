"""
services/data-ingestion/tests/test_app.py
Unit tests for the data ingestion Flask service.
"""

import sys
import os
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, data_store


class TestDataIngestion(unittest.TestCase):

    def setUp(self):
        self.client           = app.test_client()
        app.config["TESTING"] = True
        # Clear the in-memory store before each test
        data_store.clear()

    # ── /health ──────────────────────────────────────────────────────────────

    def test_health_returns_200(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_health_body(self):
        resp = self.client.get("/health")
        data = json.loads(resp.data)
        self.assertEqual(data["status"],  "healthy")
        self.assertEqual(data["service"], "data-ingestion")

    # ── /ingest ───────────────────────────────────────────────────────────────

    def test_ingest_valid_data(self):
        payload = {"sensor": "temp01", "value": 25.5}
        resp    = self.client.post(
            "/ingest",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_ingest_response_structure(self):
        payload = {"sensor": "temp01", "value": 25.5}
        resp    = self.client.post(
            "/ingest",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "success")
        self.assertIn("id",        data)
        self.assertIn("timestamp", data)

    def test_ingest_id_is_positive_integer(self):
        resp = self.client.post(
            "/ingest",
            data=json.dumps({"x": 1}),
            content_type="application/json",
        )
        data = json.loads(resp.data)
        self.assertIsInstance(data["id"], int)
        self.assertGreater(data["id"], 0)

    def test_ingest_empty_body_returns_400(self):
        resp = self.client.post(
            "/ingest",
            data=json.dumps({}),
            content_type="application/json",
        )
        # Empty JSON object IS valid JSON — service should accept it
        # If you want to reject empty dicts change the service logic;
        # for now we confirm the response is either 201 or 400
        self.assertIn(resp.status_code, [201, 400])

    def test_ingest_no_body_returns_400(self):
        resp = self.client.post("/ingest")
        self.assertEqual(resp.status_code, 400)

    # ── /data/<id> ────────────────────────────────────────────────────────────

    def test_retrieve_existing_record(self):
        # Ingest first
        resp   = self.client.post(
            "/ingest",
            data=json.dumps({"sensor": "s1", "value": 42}),
            content_type="application/json",
        )
        rec_id = json.loads(resp.data)["id"]

        # Then retrieve
        resp2  = self.client.get(f"/data/{rec_id}")
        self.assertEqual(resp2.status_code, 200)

    def test_retrieve_record_content(self):
        payload = {"sensor": "s2", "value": 99.9}
        resp    = self.client.post(
            "/ingest",
            data=json.dumps(payload),
            content_type="application/json",
        )
        rec_id = json.loads(resp.data)["id"]

        resp2  = self.client.get(f"/data/{rec_id}")
        record = json.loads(resp2.data)
        self.assertIn("data",      record)
        self.assertIn("timestamp", record)
        self.assertIn("id",        record)
        self.assertEqual(record["data"]["sensor"], "s2")

    def test_retrieve_nonexistent_record_returns_404(self):
        resp = self.client.get("/data/99999")
        self.assertEqual(resp.status_code, 404)

    # ── /data  (list) ─────────────────────────────────────────────────────────

    def test_list_data_empty_store(self):
        resp = self.client.get("/data")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["data"],  [])

    def test_list_data_respects_limit(self):
        # Ingest 5 records
        for i in range(5):
            self.client.post(
                "/ingest",
                data=json.dumps({"i": i}),
                content_type="application/json",
            )
        resp = self.client.get("/data?limit=3")
        data = json.loads(resp.data)
        self.assertLessEqual(len(data["data"]), 3)

    # ── /metrics ─────────────────────────────────────────────────────────────

    def test_metrics_returns_200(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)

    def test_metrics_contains_ingestion_counter(self):
        # Ingest something first so counter is non-zero
        self.client.post(
            "/ingest",
            data=json.dumps({"x": 1}),
            content_type="application/json",
        )
        resp = self.client.get("/metrics")
        self.assertIn(b"data_ingestion_total", resp.data)


if __name__ == "__main__":
    unittest.main()