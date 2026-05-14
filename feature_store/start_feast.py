"""
feature_store/start_feast.py
Flask server that wraps the Feast feature store.
Exposes /health, /status, /store-data, and /drift endpoints
so the training and monitoring pipelines can push/pull features.
"""

import os
import sys
import logging
import statistics
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
FEAST_REPO_PATH  = "/home/ubuntu/fraud_detection_pipeline/fraud_detection_features"
DATA_SOURCE_PATH = os.path.join(FEAST_REPO_PATH, "data", "data_source.parquet")

# Baseline statistics calculated during model training
BASELINE_STATS = {
    "TransactionAmt": {"mean": 134.5,  "std": 215.0},
    "C1":             {"mean": 1.0,    "std": 1.5},
    "C2":             {"mean": 1.2,    "std": 1.8},
    "D1":             {"mean": 200.0,  "std": 150.0},
    "amt_per_card":   {"mean": 134.5,  "std": 215.0},
}

# Rolling window for drift calculation
_feature_buffers: dict = {f: {"values": [], "last_update": datetime.now()}
                           for f in BASELINE_STATS}
_drift_scores: dict = {f: 0.0 for f in BASELINE_STATS}

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)


def _update_drift(feature: str, value: float):
    """Update rolling drift score for a single feature value."""
    buf = _feature_buffers[feature]
    buf["values"].append(value)
    if len(buf["values"]) > 1000:
        buf["values"] = buf["values"][-1000:]

    now = datetime.now()
    if (now - buf["last_update"]).total_seconds() > 60 and len(buf["values"]) > 1:
        current_mean = statistics.mean(buf["values"])
        current_std  = statistics.stdev(buf["values"])
        baseline     = BASELINE_STATS[feature]

        mean_drift = abs(current_mean - baseline["mean"]) / (baseline["std"] + 1e-9)
        std_drift  = abs(current_std  - baseline["std"])  / (baseline["std"] + 1e-9)
        _drift_scores[feature] = round((mean_drift + std_drift) / 2, 4)

        buf["last_update"] = now
        logger.info(f"Drift updated — {feature}: {_drift_scores[feature]:.4f}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "feast-feature-store"}), 200


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status": "success",
        "repo_path": FEAST_REPO_PATH,
        "data_source_exists": os.path.exists(DATA_SOURCE_PATH),
        "drift_scores": _drift_scores,
    }), 200


@app.route("/store-data", methods=["POST"])
def store_data():
    """Receive feature records and persist as parquet for offline/online store."""
    data = request.get_json()
    if not data or "data" not in data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    records = data["data"]
    if not records:
        return jsonify({"status": "error", "message": "Empty data list"}), 400

    df = pd.DataFrame(records)

    # Update drift scores for monitored features
    for feature in BASELINE_STATS:
        if feature in df.columns:
            for val in df[feature].dropna():
                _update_drift(feature, float(val))

    # Add event timestamp if missing (required by Feast offline store)
    if "event_timestamp" not in df.columns:
        df["event_timestamp"] = pd.Timestamp.now()

    os.makedirs(os.path.dirname(DATA_SOURCE_PATH), exist_ok=True)

    # Append to existing parquet or create new
    if os.path.exists(DATA_SOURCE_PATH):
        existing = pd.read_parquet(DATA_SOURCE_PATH)
        df = pd.concat([existing, df], ignore_index=True)

    df.to_parquet(DATA_SOURCE_PATH, index=False)
    logger.info(f"Stored {len(records)} records → {DATA_SOURCE_PATH}")

    return jsonify({
        "status": "success",
        "records_count": len(records),
        "total_records": len(df),
    }), 200


@app.route("/get-features", methods=["POST"])
def get_features():
    """Return features for a list of TransactionIDs (simple lookup)."""
    data = request.get_json()
    if not data or "transaction_ids" not in data:
        return jsonify({"status": "error", "message": "transaction_ids required"}), 400

    if not os.path.exists(DATA_SOURCE_PATH):
        return jsonify({"status": "error", "message": "No feature data available"}), 404

    df = pd.read_parquet(DATA_SOURCE_PATH)
    ids = data["transaction_ids"]

    if "TransactionID" in df.columns:
        result = df[df["TransactionID"].isin(ids)]
    else:
        result = df.head(len(ids))

    return jsonify({
        "status": "success",
        "features": result.fillna(0).to_dict("records"),
        "count": len(result),
    }), 200


@app.route("/drift", methods=["GET"])
def get_drift():
    """Return current drift scores for all monitored features."""
    return jsonify(_drift_scores), 200


# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    # Verify Feast environment
    conda_env = os.environ.get("CONDA_DEFAULT_ENV", "None")
    logger.info(f"Python: {sys.executable}")
    logger.info(f"Conda env: {conda_env}")

    if os.path.exists(FEAST_REPO_PATH):
        os.chdir(FEAST_REPO_PATH)
        logger.info(f"Working directory: {FEAST_REPO_PATH}")
    else:
        logger.warning(f"Feast repo not found at {FEAST_REPO_PATH}")

    try:
        from feast import FeatureStore
        store = FeatureStore(repo_path=".")
        entities    = store.list_entities()
        views       = store.list_feature_views()
        logger.info(f"Feast store loaded — {len(entities)} entities, {len(views)} feature views")
    except Exception as e:
        logger.warning(f"Feast store init failed (running in standalone mode): {e}")

    logger.info("Starting Feast feature server on port 6566 ...")
    app.run(host="0.0.0.0", port=6566, debug=False)


if __name__ == "__main__":
    main()
