"""
monitoring/prometheus_drift/drift_simulator.py
Simulates four phases of data drift against the live prediction API
so you can watch drift scores change in real time on Grafana.

Phase 1 — No drift     (baseline, 50 batches)
Phase 2 — Feature drift (MonthlyCharges ↑, tenure ↓, 100 batches)
Phase 3 — Concept drift (behavior pattern change, 50 batches)
Phase 4 — Return normal (50 batches)
"""

import requests
import pandas as pd
import numpy as np
import time
import random
from tqdm import tqdm

API_URL  = "http://localhost:8000/predict"
DATA_URL = "https://raw.githubusercontent.com/minhaz00/MLOps-Project-Customer-Churn-Prediction/main/Data/Telco-Customer-Churn.csv"

# ── Data Loading ──────────────────────────────────────────────────────────────

def load_dataset() -> pd.DataFrame:
    try:
        df = pd.read_csv(DATA_URL)
        print(f"✓ Loaded dataset: {df.shape}")
        return df
    except Exception as e:
        print(f"Dataset download failed ({e}) — generating synthetic data")
        return _synthetic_df(500)


def _synthetic_df(n: int) -> pd.DataFrame:
    return pd.DataFrame({
        "gender":         np.random.choice(["Male", "Female"], n),
        "SeniorCitizen":  np.random.randint(0, 2, n),
        "Partner":        np.random.choice(["Yes", "No"], n),
        "Dependents":     np.random.choice(["Yes", "No"], n),
        "tenure":         np.random.uniform(0, 72, n),
        "PhoneService":   np.random.choice(["Yes", "No"], n),
        "MultipleLines":  np.random.choice(["Yes", "No", "No phone service"], n),
        "OnlineSecurity": np.random.choice(["Yes", "No", "No internet service"], n),
        "OnlineBackup":   np.random.choice(["Yes", "No", "No internet service"], n),
        "DeviceProtection":np.random.choice(["Yes", "No", "No internet service"], n),
        "TechSupport":    np.random.choice(["Yes", "No", "No internet service"], n),
        "StreamingTV":    np.random.choice(["Yes", "No", "No internet service"], n),
        "StreamingMovies":np.random.choice(["Yes", "No", "No internet service"], n),
        "InternetService":np.random.choice(["DSL", "Fiber optic", "No"], n),
        "Contract":       np.random.choice(["Month-to-month", "One year", "Two year"], n),
        "PaperlessBilling":np.random.choice(["Yes", "No"], n),
        "PaymentMethod":  np.random.choice([
            "Electronic check", "Mailed check",
            "Bank transfer (automatic)", "Credit card (automatic)"
        ], n),
        "MonthlyCharges": np.random.uniform(18, 120, n),
        "TotalCharges":   [str(round(random.uniform(20, 8000), 2)) for _ in range(n)],
    })


# ── Preprocessing ─────────────────────────────────────────────────────────────

_MAPS = {
    "gender":         {"Female": 0, "Male": 1},
    "Partner":        {"Yes": 1, "No": 0},
    "Dependents":     {"Yes": 1, "No": 0},
    "PhoneService":   {"Yes": 1, "No": 0},
    "MultipleLines":  {"No": 0, "Yes": 1, "No phone service": 2},
    "OnlineSecurity": {"No": 0, "Yes": 1, "No internet service": 2},
    "OnlineBackup":   {"No": 0, "Yes": 1, "No internet service": 2},
    "DeviceProtection":{"No": 0, "Yes": 1, "No internet service": 2},
    "TechSupport":    {"No": 0, "Yes": 1, "No internet service": 2},
    "StreamingTV":    {"No": 0, "Yes": 1, "No internet service": 2},
    "StreamingMovies":{"No": 0, "Yes": 1, "No internet service": 2},
    "PaperlessBilling":{"Yes": 1, "No": 0},
}


def preprocess_row(row) -> dict:
    d = {}
    for col, mapping in _MAPS.items():
        d[col] = mapping.get(row.get(col, "No"), 0)

    d["SeniorCitizen"]  = int(row.get("SeniorCitizen", 0))
    d["tenure"]         = float(row.get("tenure", 0))
    d["MonthlyCharges"] = float(row.get("MonthlyCharges", 0))
    try:
        d["TotalCharges"] = float(str(row.get("TotalCharges", "0")).strip() or 0)
    except ValueError:
        d["TotalCharges"] = 0.0

    internet = row.get("InternetService", "No")
    d["InternetService_DSL"]          = int(internet == "DSL")
    d["InternetService_Fiber_optic"]  = int(internet == "Fiber optic")
    d["InternetService_No"]           = int(internet == "No")

    contract = row.get("Contract", "Month-to-month")
    d["Contract_Month_to_month"] = int(contract == "Month-to-month")
    d["Contract_One_year"]       = int(contract == "One year")
    d["Contract_Two_year"]       = int(contract == "Two year")

    payment = row.get("PaymentMethod", "Electronic check")
    d["PaymentMethod_Bank_transfer_automatic"] = int(payment == "Bank transfer (automatic)")
    d["PaymentMethod_Credit_card_automatic"]   = int(payment == "Credit card (automatic)")
    d["PaymentMethod_Electronic_check"]        = int(payment == "Electronic check")
    d["PaymentMethod_Mailed_check"]            = int(payment == "Mailed check")

    return d


def apply_drift(record: dict, drift_type: str, intensity: float = 0.2) -> dict:
    d = record.copy()
    if drift_type == "feature_drift":
        d["MonthlyCharges"] *= (1 + intensity)
        d["tenure"]          = d["tenure"] * (1 - intensity / 2)
        d["TotalCharges"]   *= (1 + intensity / 3)
    elif drift_type == "concept_drift":
        if random.random() < intensity:
            d["StreamingTV"]    = 1
            d["StreamingMovies"] = 1
            d["Contract_Month_to_month"] = 1
            d["Contract_One_year"]       = 0
            d["Contract_Two_year"]       = 0
    elif drift_type == "seasonal_drift":
        if random.random() < intensity:
            d["Contract_Month_to_month"] = 1
            d["Contract_One_year"]       = 0
            d["Contract_Two_year"]       = 0
    return d


def send_batch(records: list, drift_type: str = "none", intensity: float = 0.0):
    processed = [preprocess_row(r) for r in records]
    if drift_type != "none":
        processed = [apply_drift(r, drift_type, intensity) for r in processed]
    try:
        resp = requests.post(API_URL, json=processed, timeout=15)
        if resp.status_code != 200:
            print(f"  API error {resp.status_code}: {resp.text[:80]}")
    except Exception as e:
        print(f"  Request failed: {e}")


# ── Simulation Phases ─────────────────────────────────────────────────────────

def simulate():
    df = load_dataset()
    rows = df.to_dict("records")

    print("\n── Phase 1: No drift (baseline) ──────────────────")
    for _ in tqdm(range(50)):
        batch = random.choices(rows, k=10)
        send_batch(batch)
        time.sleep(1)

    print("\n── Phase 2: Gradual feature drift ────────────────")
    for i in tqdm(range(100)):
        intensity = min(0.5, i * 0.005)
        batch = random.choices(rows, k=10)
        send_batch(batch, "feature_drift", intensity)
        time.sleep(1)

    print("\n── Phase 3: Concept drift ────────────────────────")
    for _ in tqdm(range(50)):
        batch = random.choices(rows, k=10)
        send_batch(batch, "concept_drift", 0.3)
        time.sleep(1)

    print("\n── Phase 4: Return to normal ─────────────────────")
    for _ in tqdm(range(50)):
        batch = random.choices(rows, k=10)
        send_batch(batch)
        time.sleep(1)

    print("\n✓ Drift simulation completed!")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        API_URL = sys.argv[1]
    print(f"Sending drift simulation to {API_URL}")
    simulate()