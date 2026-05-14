"""
monitoring/evidently_drift/monitor.py
Fetches reference data from S3 and current predictions from PostgreSQL,
generates Evidently AI drift reports (full + per-feature), and uploads
all HTML reports back to S3 for audit trail.
"""

import os
import io
import boto3
import pandas as pd
import psycopg2
from sqlalchemy import create_engine
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, DataQualityPreset
from evidently.metrics import ColumnDriftMetric, ColumnSummaryMetric
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
S3_BUCKET         = os.getenv("S3_BUCKET",   "churn-model-poridhi5678")
S3_DATASET_KEY    = os.getenv("S3_DATASET_KEY", "my_dataset.csv")
REPORT_OUTPUT_DIR = "reports"

DB_USER     = os.getenv("DB_USER",     "my_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "my_password")
DB_NAME     = os.getenv("DB_NAME",     "my_db")
DB_HOST     = os.getenv("DB_HOST",     "postgres")
DB_PORT     = os.getenv("DB_PORT",     "5432")

# Features to monitor individually
IMPORTANT_FEATURES = [
    "tenure",
    "MonthlyCharges",
    "TotalCharges",
    "Contract_Month_to_month",
    "InternetService_Fiber_optic",
]


# ── Database ──────────────────────────────────────────────────────────────────

def get_db_engine():
    url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)


def fetch_current_predictions(engine) -> pd.DataFrame:
    """Load all prediction records from PostgreSQL."""
    try:
        df = pd.read_sql("SELECT * FROM predictions", engine)
        print(f"✓ Loaded {len(df)} prediction records from PostgreSQL")
        return df
    except Exception as e:
        print(f"Error fetching from PostgreSQL: {e}")
        raise


# ── S3 ────────────────────────────────────────────────────────────────────────

def fetch_reference_data() -> pd.DataFrame:
    """Download reference (training) dataset from S3."""
    try:
        s3  = boto3.client("s3")
        obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_DATASET_KEY)
        df  = pd.read_csv(io.BytesIO(obj["Body"].read()))
        print(f"✓ Loaded reference dataset from S3: {df.shape}")
        return df
    except Exception as e:
        print(f"Error fetching reference data from S3: {e}")
        raise


def upload_report(local_path: str, s3_key: str = None):
    """Upload an HTML report to S3."""
    try:
        s3 = boto3.client("s3")
        key = s3_key or f"reports/{os.path.basename(local_path)}"
        s3.upload_file(local_path, S3_BUCKET, key)
        print(f"✓ Uploaded {local_path} → s3://{S3_BUCKET}/{key}")
    except Exception as e:
        print(f"Upload failed ({local_path}): {e}")


# ── Data Alignment ────────────────────────────────────────────────────────────

def align_datasets(current: pd.DataFrame, reference: pd.DataFrame):
    """Keep only columns that exist in both datasets, drop id/prediction."""
    drop_cols   = {"id", "prediction"}
    common_cols = list(
        (set(current.columns) & set(reference.columns)) - drop_cols
    )
    print(f"✓ Comparing {len(common_cols)} common columns")
    return current[common_cols], reference[common_cols]


# ── Report Generation ─────────────────────────────────────────────────────────

def generate_full_drift_report(current: pd.DataFrame, reference: pd.DataFrame) -> str:
    """Run DataDriftPreset + DataQualityPreset and save HTML."""
    os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(REPORT_OUTPUT_DIR, f"drift_report_{timestamp}.html")

    cur_aligned, ref_aligned = align_datasets(current, reference)

    report = Report(metrics=[
        DataDriftPreset(),
        DataQualityPreset(),
    ])
    report.run(reference_data=ref_aligned, current_data=cur_aligned)
    report.save_html(report_path)

    print(f"✓ Full drift report saved → {report_path}")
    return report_path


def generate_feature_drift_reports(current: pd.DataFrame, reference: pd.DataFrame):
    """Generate one HTML report per important feature and upload to S3."""
    feature_dir = os.path.join(REPORT_OUTPUT_DIR, "features")
    os.makedirs(feature_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    cur_aligned, ref_aligned = align_datasets(current, reference)

    for feature in IMPORTANT_FEATURES:
        if feature not in cur_aligned.columns or feature not in ref_aligned.columns:
            print(f"  Skipping {feature} — not in both datasets")
            continue

        try:
            report = Report(metrics=[
                ColumnDriftMetric(column_name=feature),
                ColumnSummaryMetric(column_name=feature),
            ])
            report.run(reference_data=ref_aligned, current_data=cur_aligned)

            path = os.path.join(feature_dir, f"{feature}_drift_{timestamp}.html")
            report.save_html(path)
            print(f"  ✓ Feature report: {feature} → {path}")

            upload_report(path, f"reports/features/{feature}_drift_{timestamp}.html")

        except Exception as e:
            print(f"  Error generating report for {feature}: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Evidently AI Drift Monitoring")
    print("=" * 60)

    engine    = get_db_engine()
    current   = fetch_current_predictions(engine)
    reference = fetch_reference_data()

    # Full report
    full_report_path = generate_full_drift_report(current, reference)
    upload_report(full_report_path)

    # Per-feature reports
    generate_feature_drift_reports(current, reference)

    print("\n✓ Monitoring run complete")
    print(f"  Reports available at: s3://{S3_BUCKET}/reports/")


if __name__ == "__main__":
    main()