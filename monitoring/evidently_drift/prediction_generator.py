"""
monitoring/evidently_drift/prediction_generator.py
Generates synthetic customer records, sends them to the prediction
API, and verifies the records are stored in PostgreSQL.
Used to populate the predictions table before running monitor.py.

Usage:
    python prediction_generator.py --num-samples 100 --api-host localhost
"""

import argparse
import json
import random
import time

import pandas as pd
import requests
from sqlalchemy import create_engine

# ── Configuration ─────────────────────────────────────────────────────────────
API_ENDPOINT = "http://localhost:8000/predict"

DB_CONFIG = {
    "user":     "my_user",
    "password": "my_password",
    "host":     "localhost",
    "port":     "5432",
    "database": "my_db",
}


# ── Data Generation ───────────────────────────────────────────────────────────

def generate_customers(n: int = 10) -> list:
    """Generate n random customer feature dicts."""
    customers = []
    for _ in range(n):
        internet = random.choice(["DSL", "Fiber_optic", "No"])
        contract = random.choice(["Month_to_month", "One_year", "Two_year"])
        payment  = random.choice([
            "Bank_transfer_automatic", "Credit_card_automatic",
            "Electronic_check", "Mailed_check",
        ])
        tenure         = round(random.uniform(0, 72), 1)
        monthly        = round(random.uniform(20, 120), 2)
        total          = round(tenure * monthly * random.uniform(0.9, 1.1), 2)
        phone_service  = random.randint(0, 1)

        customers.append({
            "gender":           random.randint(0, 1),
            "SeniorCitizen":    random.randint(0, 1),
            "Partner":          random.randint(0, 1),
            "Dependents":       random.randint(0, 1),
            "tenure":           tenure,
            "PhoneService":     phone_service,
            "MultipleLines":    random.randint(0, 1) if phone_service else 0,
            "OnlineSecurity":   random.randint(0, 1),
            "OnlineBackup":     random.randint(0, 1),
            "DeviceProtection": random.randint(0, 1),
            "TechSupport":      random.randint(0, 1),
            "StreamingTV":      random.randint(0, 1),
            "StreamingMovies":  random.randint(0, 1),
            "PaperlessBilling": random.randint(0, 1),
            "MonthlyCharges":   monthly,
            "TotalCharges":     total,
            # Internet service (one-hot)
            "InternetService_DSL":         int(internet == "DSL"),
            "InternetService_Fiber_optic": int(internet == "Fiber_optic"),
            "InternetService_No":          int(internet == "No"),
            # Contract (one-hot)
            "Contract_Month_to_month": int(contract == "Month_to_month"),
            "Contract_One_year":       int(contract == "One_year"),
            "Contract_Two_year":       int(contract == "Two_year"),
            # Payment method (one-hot)
            "PaymentMethod_Bank_transfer_automatic": int(payment == "Bank_transfer_automatic"),
            "PaymentMethod_Credit_card_automatic":   int(payment == "Credit_card_automatic"),
            "PaymentMethod_Electronic_check":        int(payment == "Electronic_check"),
            "PaymentMethod_Mailed_check":            int(payment == "Mailed_check"),
        })
    return customers


# ── API ───────────────────────────────────────────────────────────────────────

def send_predictions(batch: list) -> int:
    """POST batch to the API, return number of successful predictions."""
    try:
        resp = requests.post(
            API_ENDPOINT,
            json=batch,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code == 200:
            preds = resp.json().get("predictions", [])
            return len(preds)
        else:
            print(f"  API error {resp.status_code}: {resp.text[:100]}")
            return 0
    except Exception as e:
        print(f"  Request failed: {e}")
        return 0


# ── Database Verification ─────────────────────────────────────────────────────

def verify_db(expected_min: int) -> int:
    """Return total row count in predictions table."""
    try:
        url    = (f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
                  f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
        engine = create_engine(url)
        result = pd.read_sql("SELECT COUNT(*) FROM predictions", engine)
        count  = int(result.iloc[0, 0])
        print(f"✓ DB verification: {count} total rows in predictions table")
        if count >= expected_min:
            print(f"  Expected at least {expected_min} → OK")
        else:
            print(f"  Expected at least {expected_min} → only {count} found")
        return count
    except Exception as e:
        print(f"DB verification failed: {e}")
        return -1


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate predictions for drift monitoring")
    parser.add_argument("--num-samples", type=int,  default=50,        help="Total customers to generate")
    parser.add_argument("--batch-size",  type=int,  default=10,        help="Records per API call")
    parser.add_argument("--api-host",    type=str,  default="localhost")
    parser.add_argument("--api-port",    type=int,  default=8000)
    parser.add_argument("--db-host",     type=str,  default="localhost")
    args = parser.parse_args()

    global API_ENDPOINT
    API_ENDPOINT          = f"http://{args.api_host}:{args.api_port}/predict"
    DB_CONFIG["host"]     = args.db_host

    print("=" * 60)
    print("  Churn Prediction Generator")
    print("=" * 60)
    print(f"  API endpoint : {API_ENDPOINT}")
    print(f"  DB host      : {DB_CONFIG['host']}")
    print(f"  Generating   : {args.num_samples} customers in batches of {args.batch_size}")
    print()

    starting_count  = verify_db(0)
    customers       = generate_customers(args.num_samples)
    total_predicted = 0

    for i in range(0, len(customers), args.batch_size):
        batch = customers[i : i + args.batch_size]
        print(f"  Batch {i // args.batch_size + 1}: {len(batch)} records ...", end=" ")
        n = send_predictions(batch)
        total_predicted += n
        print(f"→ {n} predictions returned")
        time.sleep(0.3)

    print()
    final_count = verify_db(starting_count + total_predicted)

    print()
    print("Summary")
    print(f"  Starting rows : {starting_count}")
    print(f"  Requested     : {args.num_samples}")
    print(f"  Predicted     : {total_predicted}")
    print(f"  Final rows    : {final_count}")


if __name__ == "__main__":
    main()