"""
pipelines/retraining_pipeline.py
Airflow DAG — Drift-triggered retraining pipeline.
Checks Evidently drift scores, and if drift is detected above
threshold, re-runs the full preprocessing + training pipeline.
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.utils.state import State
from datetime import datetime, timedelta
import requests
import json
import os

# ── Configuration ─────────────────────────────────────────────────────────────
FEAST_SERVER_URL    = "http://10.0.2.40:6566"
MLFLOW_TRACKING_URI = "http://localhost:5000"
DRIFT_THRESHOLD     = 0.3          # Trigger retraining if any feature drift > 0.3
TMP_DIR             = "/opt/airflow/fraud_detection_pipeline/tmp"

# ── Task functions ────────────────────────────────────────────────────────────

def check_drift_scores(**context):
    """
    Read latest drift scores from the Feast /drift endpoint.
    Pushes 'retrain_needed' flag to XCom.
    """
    print("Checking drift scores...")
    retrain_needed = False

    try:
        r = requests.get(f"{FEAST_SERVER_URL}/drift", timeout=10)
        if r.status_code == 200:
            drift_scores = r.json()
            print(f"Drift scores: {drift_scores}")

            for feature, score in drift_scores.items():
                if score is not None and score > DRIFT_THRESHOLD:
                    print(f"⚠️  DRIFT DETECTED — {feature}: {score:.4f} > threshold {DRIFT_THRESHOLD}")
                    retrain_needed = True
        else:
            print(f"Drift endpoint returned {r.status_code} — assuming no drift")
    except Exception as e:
        print(f"Could not reach drift endpoint: {e} — assuming no drift")

    context["ti"].xcom_push(key="retrain_needed", value=retrain_needed)
    print(f"Retrain needed: {retrain_needed}")
    return retrain_needed


def evaluate_model_performance(**context):
    """
    Pull latest model metrics from MLflow and check if performance
    has degraded below acceptable thresholds.
    """
    print("Evaluating model performance...")
    retrain_needed = context["ti"].xcom_pull(key="retrain_needed", task_ids="check_drift_scores")

    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.tracking.MlflowClient()

        # Check best model experiment
        experiment = client.get_experiment_by_name("fraud_detection_model_selection")
        if experiment:
            runs = client.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["start_time DESC"],
                max_results=1,
            )
            if runs:
                latest_run = runs[0]
                f1    = latest_run.data.metrics.get("best_f1_score", 1.0)
                auc   = latest_run.data.metrics.get("best_auc", 1.0)
                print(f"Latest model — F1: {f1:.4f} | AUC: {auc:.4f}")

                F1_THRESHOLD  = 0.7
                AUC_THRESHOLD = 0.75

                if f1 < F1_THRESHOLD or auc < AUC_THRESHOLD:
                    print(f"⚠️  PERFORMANCE DEGRADATION — F1={f1:.4f} AUC={auc:.4f}")
                    retrain_needed = True
    except Exception as e:
        print(f"Could not evaluate MLflow metrics: {e}")

    context["ti"].xcom_push(key="retrain_needed", value=retrain_needed)
    print(f"Final retrain decision: {retrain_needed}")
    return retrain_needed


def decide_retraining(**context):
    """
    Branch logic — raise an exception to skip downstream tasks if
    retraining is not needed (Airflow short-circuit pattern).
    """
    retrain_needed = context["ti"].xcom_pull(key="retrain_needed", task_ids="evaluate_model_performance")

    if not retrain_needed:
        print("✓ No retraining needed — model performance is acceptable")
        raise Exception("SKIP: No retraining needed")   # causes downstream to be skipped
    else:
        print("⚠️  Retraining triggered!")


def notify_retraining_start(**context):
    """Log retraining event to a file (extend to Slack/email in production)."""
    os.makedirs(TMP_DIR, exist_ok=True)
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "reason": "drift_or_performance_degradation",
        "dag_run_id": context["run_id"],
    }
    path = os.path.join(TMP_DIR, "retraining_events.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps(event) + "\n")
    print(f"✓ Retraining event logged: {event}")


# ── DAG Definition ────────────────────────────────────────────────────────────
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "email_on_failure": False,
    "retries": 0,
}

with DAG(
    "retraining_pipeline",
    default_args=default_args,
    description="Drift-triggered retraining — checks drift then triggers training DAG",
    schedule_interval="@daily",     # Run drift check daily
    catchup=False,
    tags=["fraud_detection", "retraining", "drift"],
) as dag:

    t_drift    = PythonOperator(
        task_id="check_drift_scores",
        python_callable=check_drift_scores,
        provide_context=True,
    )

    t_perf     = PythonOperator(
        task_id="evaluate_model_performance",
        python_callable=evaluate_model_performance,
        provide_context=True,
    )

    t_decide   = PythonOperator(
        task_id="decide_retraining",
        python_callable=decide_retraining,
        provide_context=True,
    )

    t_notify   = PythonOperator(
        task_id="notify_retraining_start",
        python_callable=notify_retraining_start,
        provide_context=True,
    )

    # Trigger the preprocessing DAG first, then training
    t_preprocess = TriggerDagRunOperator(
        task_id="trigger_preprocessing_pipeline",
        trigger_dag_id="preprocessing_pipeline",
        wait_for_completion=True,
    )

    t_train    = TriggerDagRunOperator(
        task_id="trigger_training_pipeline",
        trigger_dag_id="training_pipeline",
        wait_for_completion=True,
    )

    t_drift >> t_perf >> t_decide >> t_notify >> t_preprocess >> t_train