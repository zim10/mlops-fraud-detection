"""
services/data-ingestion/app.py
Flask microservice — Data ingestion service for the CI/CD pipeline.
Receives, stores, and retrieves data records.
Exposes /health, /ingest, /data/<id>, /data (list), and /metrics on port 8002.
"""

import time
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────
ingestion_counter  = Counter(
    "data_ingestion_total",
    "Total number of data records ingested",
)
ingestion_duration = Histogram(
    "data_ingestion_duration_seconds",
    "Time spent processing an ingestion request",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)
data_size_hist = Histogram(
    "data_size_bytes",
    "Size of each ingested payload in bytes",
    buckets=[64, 256, 1024, 4096, 16384, 65536, 262144],
)
store_size_gauge = Gauge(
    "data_store_total_records",
    "Total records currently in the in-memory store",
)

# ── In-memory Store ───────────────────────────────────────────────────────────
# In production replace with a database (PostgreSQL, DynamoDB, etc.)
data_store: list = []

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    """Liveness / readiness probe."""
    return jsonify({"status": "healthy", "service": "data-ingestion"}), 200


@app.route("/ingest", methods=["POST"])
def ingest():
    """
    Accept any JSON payload, attach metadata, and store it.
    Returns 201 with the new record ID and timestamp.
    """
    start_time = time.time()

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    record = {
        "id":        len(data_store) + 1,
        "data":      data,
        "timestamp": datetime.utcnow().isoformat(),
        "source_ip": request.remote_addr,
    }

    # Simulate processing delay
    time.sleep(0.05)

    data_store.append(record)
    store_size_gauge.set(len(data_store))

    # Update Prometheus metrics
    ingestion_counter.inc()
    ingestion_duration.observe(time.time() - start_time)
    data_size_hist.observe(len(json.dumps(data)))

    logger.info(f"Ingested record ID={record['id']} from {record['source_ip']}")

    return jsonify({
        "status":    "success",
        "id":        record["id"],
        "timestamp": record["timestamp"],
    }), 201


@app.route("/data/<int:data_id>", methods=["GET"])
def get_data(data_id: int):
    """Retrieve a single record by its numeric ID."""
    for record in data_store:
        if record["id"] == data_id:
            return jsonify(record), 200
    return jsonify({"error": f"Data not found: id={data_id}"}), 404


@app.route("/data", methods=["GET"])
def list_data():
    """
    Return the most recent records.
    Optional query param: ?limit=N  (default 10, max 100)
    """
    limit  = min(request.args.get("limit", 10, type=int), 100)
    recent = data_store[-limit:] if data_store else []
    return jsonify({
        "total":  len(data_store),
        "limit":  limit,
        "data":   recent,
    }), 200


@app.route("/metrics", methods=["GET"])
def metrics():
    """Prometheus scrape endpoint."""
    try:
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        return "Metrics unavailable", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002, debug=False)