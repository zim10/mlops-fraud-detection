# 🚀 MLOps Fraud Detection Pipeline

An end-to-end MLOps pipeline for fraud detection using the IEEE-CIS Fraud Detection dataset, deployed on AWS EC2 with infrastructure-as-code via Pulumi and fully automated CI/CD via GitHub Actions.

> **Status:** Training ✅ | Serving ✅ | Load Testing ✅ | Drift Monitoring ✅ | CI/CD ✅

---

## 📋 Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Pipeline Components](#pipeline-components)
- [CI/CD Workflow](#cicd-workflow)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)

---

## Project Overview

This project builds a **production-style end-to-end MLOps pipeline** covering the full ML lifecycle — from raw data ingestion, feature engineering, model training and tracking, containerized model serving, load testing, comprehensive drift monitoring, and fully automated CI/CD deployment on AWS.

**Every phase is complete (✅):**
- Stores raw fraud detection data in **MongoDB** on AWS EC2
- Engineers and serves features via **Feast** with Redis online store
- Tracks experiments and registers models with **MLflow** backed by S3
- Orchestrates model training workflows with **Apache Airflow**
- Trains and compares **XGBoost**, **LightGBM**, and **Isolation Forest** models
- Selects the best model automatically based on F1-score
- Serves the model as a REST API via **FastAPI** inside a **Docker** container
- Logs all predictions to **PostgreSQL** for drift comparison
- Load tests the API with **Locust** across four user behavior profiles
- Scrapes real-time metrics with **Prometheus** and visualizes on **Grafana**
- Detects statistical feature drift using custom Prometheus drift gauges
- Generates full HTML drift reports using **Evidently AI** stored in S3
- Automates the full build-test-deploy lifecycle with **GitHub Actions + Pulumi**
- Pushes Docker images to **AWS ECR** and deploys to EC2 automatically

---

## Architecture

### Overall System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           AWS VPC (10.0.0.0/16)                          │
│                                                                           │
│  ┌───────────────────┐         ┌─────────────────────────────────────┐   │
│  │   Public Subnet   │         │          Private Subnet             │   │
│  │   (10.0.1.0/24)   │  SSH /  │          (10.0.2.0/24)              │   │
│  │                   │  Tunnel │                                     │   │
│  │  ┌─────────────┐  │◄───────►│  ┌──────────┐    ┌─────────────┐   │   │
│  │  │   Bastion   │  │         │  │ MongoDB  │    │    Feast    │   │   │
│  │  │    Host     │  │         │  │ (27017)  │    │  + Redis    │   │   │
│  │  └─────────────┘  │         │  └──────────┘    │   (6566)    │   │   │
│  └───────────────────┘         │                  └─────────────┘   │   │
│           │                    │  ┌──────────┐    ┌─────────────┐   │   │
│    Internet Gateway            │  │  MLflow  │    │   Airflow   │   │   │
│                                │  │  (5000)  │    │   (8080)    │   │   │
│                                │  └──────────┘    └─────────────┘   │   │
│                                │                                     │   │
│                                │  ┌──────────┐    ┌─────────────┐   │   │
│                                │  │ FastAPI  │    │  PostgreSQL │   │   │
│                                │  │ +Docker  │    │  (5432)     │   │   │
│                                │  │(8001/8002│    └─────────────┘   │   │
│                                │  └──────────┘                      │   │
│                                │  ┌──────────┐    ┌─────────────┐   │   │
│                                │  │  Locust  │    │ Prometheus  │   │   │
│                                │  │  (8089)  │    │ + Grafana   │   │   │
│                                │  └──────────┘    └─────────────┘   │   │
│                                └─────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
         │                              │                    │
┌────────▼───────────┐  ┌──────────────▼──────────┐  ┌─────▼──────────────┐
│     S3 Bucket      │  │       S3 Bucket          │  │    AWS ECR         │
│ (MLflow Artifacts) │  │  (Evidently Drift Reports│  │  (Docker Images)   │
└────────────────────┘  │   + Reference Dataset)   │  └────────────────────┘
                        └──────────────────────────┘
```

### CI/CD Pipeline Flow ✅

```
  Developer pushes to main
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │              GitHub Actions Workflow                  │
  │                                                       │
  │  ┌─────────────┐    ┌─────────────┐                  │
  │  │  Test Job 1 │    │  Test Job 2 │  (parallel)      │
  │  │ ml-inference│    │data-ingestion                  │
  │  └──────┬──────┘    └──────┬──────┘                  │
  │         └────────┬─────────┘                         │
  │                  ▼                                    │
  │  ┌───────────────────────────┐                        │
  │  │  deploy-infrastructure    │                        │
  │  │  Pulumi destroy + recreate│                        │
  │  │  VPC + EC2 + ECR + EIP    │                        │
  │  └───────────────┬───────────┘                        │
  │                  ▼                                    │
  │  ┌─────────────┐    ┌─────────────┐                  │
  │  │ Build+Push  │    │ Build+Push  │  (parallel)      │
  │  │ ml-inference│    │data-ingestion                  │
  │  │   → ECR     │    │   → ECR     │                  │
  │  └──────┬──────┘    └──────┬──────┘                  │
  │         └────────┬─────────┘                         │
  │                  ▼                                    │
  │  ┌───────────────────────────┐                        │
  │  │     deploy-services       │                        │
  │  │  SSH to EC2               │                        │
  │  │  docker-compose up        │                        │
  │  │  Health check validation  │                        │
  │  └───────────────────────────┘                        │
  └─────────────────────────────────────────────────────┘
```

### Training Pipeline DAG (Airflow) ✅

```
[test_feast_connection] ──┐
                          ├──► [load_features] ──► [prepare_data]
[test_mlflow_connection]──┘                              │
                                           ┌─────────────┼─────────────┐
                                           ▼             ▼             ▼
                                     [xgboost]    [lightgbm]  [isolation_forest]
                                           └─────────────┼─────────────┘
                                                         ▼
                                                [select_best_model]
```

### Drift Monitoring Flow ✅

```
  Live Traffic                  Monitoring Stack
──────────────                  ────────────────

  User Request              ┌──────────────────────────────────────┐
      │                     │          Docker Compose               │
      ▼                     │                                      │
  ┌────────┐  predictions ┌─▼────────┐                            │
  │FastAPI │─────────────►│PostgreSQL│                            │
  │  API   │              │(current) │                            │
  └───┬────┘              └───┬──────┘                            │
      │ /metrics              │                                   │
      ▼                       ▼                                   │
  ┌──────────┐       ┌───────────────┐   ┌─────────────────┐     │
  │Prometheus│       │ Evidently AI  │◄──│   S3 Bucket     │     │
  │  (drift  │       │  monitor.py   │   │ (reference data)│     │
  │  gauges) │       └───────┬───────┘   └─────────────────┘     │
  └────┬─────┘               │ drift reports → S3               │
       ▼                     ▼                                   │
  ┌──────────┐       ┌───────────────┐                           │
  │  Grafana │       │drift_simulator│                           │
  │Dashboard │       │ 4 drift phases│                           │
  └──────────┘       └───────────────┘                           │
                                                                 │
  └───────────────────────────────────────────────────────────--─┘
```

### Full MLOps Lifecycle

```
                    ┌─────────────────────────────────────┐
                    │     CI/CD (GitHub Actions) ✅         │
                    │  push → test → infra → build → deploy│
                    └───────────────┬─────────────────────┘
                                    │
    ┌──────────┐    ┌─────────┐    ┌▼────────┐    ┌──────────┐
    │  Ingest  │───►│ Feature │───►│  Train  │───►│  Serve   │
    │ MongoDB  │    │  Feast  │    │ Airflow │    │ FastAPI  │
    │    ✅    │    │   ✅    │    │   ✅    │    │ +Docker  │
    └──────────┘    └─────────┘    └────┬────┘    │   ✅    │
                                        │         └────┬─────┘
                                   ┌────▼──────────────▼─────┐
                                   │    MLflow Model Registry  │
                                   │           ✅              │
                                   └──────────────────────────┘
                                                  │
              ┌───────────────────────────────────▼──────────────────┐
              │                   Monitor ✅                           │
              │  Locust (load)  Prometheus (metrics)  Grafana (viz)   │
              │  Evidently AI (drift reports → S3)                    │
              │  PostgreSQL (prediction logs)                         │
              │  Drift Simulator (feature + concept + seasonal drift) │
              └───────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Category | Tool | Status |
|---|---|---|
| Cloud | AWS EC2, S3, VPC, IAM, ECR, EIP | ✅ Complete |
| IaC | Pulumi (Python) | ✅ Complete |
| CI/CD | GitHub Actions | ✅ Complete |
| Database | MongoDB 7.0 | ✅ Complete |
| Prediction Store | PostgreSQL | ✅ Complete |
| Feature Store | Feast + Redis | ✅ Complete |
| Experiment Tracking | MLflow 2.15 | ✅ Complete |
| Orchestration | Apache Airflow 2.10 | ✅ Complete |
| ML Models | XGBoost, LightGBM, Scikit-learn | ✅ Complete |
| Model Serving | FastAPI + Uvicorn + Gunicorn | ✅ Complete |
| Containerization | Docker + Docker Compose | ✅ Complete |
| Image Registry | AWS ECR | ✅ Complete |
| Load Testing | Locust | ✅ Complete |
| API Testing | Postman (15+ test scenarios) | ✅ Complete |
| Metrics Scraping | Prometheus | ✅ Complete |
| Dashboarding | Grafana | ✅ Complete |
| Alerting | Prometheus Alert Rules | ✅ Complete |
| Statistical Drift | Custom Prometheus Drift Gauges | ✅ Complete |
| Drift Reports | Evidently AI | ✅ Complete |

---

## Project Structure

```
mlops-fraud-detection/
│
│  ══════════════════════════════════════════════
│  ✅  PHASE 1 — TRAINING PIPELINE (COMPLETE)
│  ══════════════════════════════════════════════
│
├── infrastructure/                        # Pulumi IaC — one folder per service
│   ├── mongodb/
│   │   ├── main.py                        # VPC + EC2 for MongoDB
│   │   └── scripts/
│   │       └── mongodb-install.sh
│   ├── feast/
│   │   ├── main.py                        # VPC + EC2 for Feast + Redis
│   │   └── scripts/
│   │       ├── feast-install.sh
│   │       ├── setup_feast.sh
│   │       └── create_feast_config.sh
│   ├── mlflow/
│   │   ├── main.py                        # VPC + EC2 + S3 + IAM for MLflow
│   │   └── scripts/
│   │       └── mlflow-install.sh
│   └── airflow/
│       ├── main.py                        # VPC + EC2 for Airflow
│       └── scripts/
│           └── airflow-install.sh
│
├── pipelines/                             # Airflow DAG definitions
│   ├── training_pipeline.py               # ✅ XGBoost + LightGBM + IsolationForest
│   ├── preprocessing_pipeline.py          # Feature engineering DAG
│   └── retraining_pipeline.py             # Drift-triggered retraining DAG
│
├── feature_store/
│   ├── feature_store.yaml                 # Feast config (Redis online store)
│   ├── start_feast.py                     # Feast Flask server
│   └── features/
│       └── fraud_features.py
│
├── models/
│   ├── xgboost_fraud_model.json
│   ├── lightgbm_fraud_model.txt
│   └── isolation_forest_model.pkl
│
│  ══════════════════════════════════════════════
│  ✅  PHASE 2 — MODEL SERVING (COMPLETE)
│  ══════════════════════════════════════════════
│
├── serving/
│   ├── app/
│   │   ├── main.py                        # FastAPI — /predict /batch-predict /health /metrics
│   │   ├── models.py                      # SQLAlchemy models (PostgreSQL)
│   │   ├── schemas.py                     # Pydantic request/response schemas
│   │   └── model_loader.py                # Load model from S3 / MLflow registry
│   ├── Dockerfile                         # python:3.9-slim, Gunicorn, EXPOSE 8000
│   └── requirements.txt
│
│  ══════════════════════════════════════════════════════
│  ✅  PHASE 3 — LOAD TESTING & METRICS (COMPLETE)
│  ══════════════════════════════════════════════════════
│
├── load_testing/
│   ├── docker-compose.yml                 # FastAPI + Locust + Prometheus + Grafana
│   ├── locust/
│   │   └── locustfile.py                  # MLModelUser, HeavyUser, LightUser, BurstUser
│   └── prometheus/
│       └── prometheus.yml
│
│  ══════════════════════════════════════════════════════
│  ✅  PHASE 4 — DRIFT MONITORING (COMPLETE)
│  ══════════════════════════════════════════════════════
│
├── monitoring/
│   ├── prometheus_drift/
│   │   ├── docker-compose.yml             # FastAPI + PostgreSQL + Prometheus + Grafana
│   │   ├── main.py                        # FastAPI with FEATURE_DRIFT_GAUGE metrics
│   │   ├── models.py                      # PredictionRecord (SQLAlchemy)
│   │   ├── prometheus.yml
│   │   └── drift_simulator.py             # 4-phase drift simulation:
│   │                                      #   Phase 1: No drift (baseline)
│   │                                      #   Phase 2: Gradual feature drift
│   │                                      #   Phase 3: Concept drift
│   │                                      #   Phase 4: Return to normal
│   │
│   └── evidently_drift/
│       ├── monitor.py                     # Fetch PostgreSQL + S3 → Evidently report
│       ├── prediction_generator.py        # Generate synthetic predictions to DB
│       └── reports/
│           └── features/                  # Per-feature HTML drift reports → S3
│
│  ══════════════════════════════════════════════════════
│  ✅  PHASE 5 — CI/CD PIPELINE (COMPLETE)
│  ══════════════════════════════════════════════════════
│
├── services/                              # Microservices for CI/CD deployment
│   ├── ml-inference/
│   │   ├── app.py                         # Flask ML service (port 8001)
│   │   ├── requirements.txt
│   │   ├── Dockerfile                     # Gunicorn, non-root user
│   │   └── tests/
│   │       └── test_app.py                # Unit tests (health, predict, errors)
│   │
│   └── data-ingestion/
│       ├── app.py                         # Flask data service (port 8002)
│       ├── requirements.txt
│       ├── Dockerfile
│       └── tests/
│           └── test_app.py                # Unit tests (health, ingest, retrieve)
│
├── cicd-infrastructure/                   # Pulumi for CI/CD stack
│   ├── __main__.py                        # VPC + EC2 + ECR + EIP + Security Groups
│   ├── Pulumi.yaml
│   ├── Pulumi.dev.yaml
│   └── requirements.txt
│
├── .github/
│   └── workflows/
│       └── deploy.yml                     # Full CI/CD pipeline:
│                                          #   test (parallel) →
│                                          #   deploy-infrastructure (Pulumi) →
│                                          #   build-and-push → ECR (parallel) →
│                                          #   deploy-services (SSH + Docker Compose)
│
├── monitoring-cicd/                       # Monitoring for CI/CD stack
│   ├── prometheus/
│   │   ├── prometheus.yml                 # Scrape ml-inference + data-ingestion
│   │   └── alerts.yml                     # 6 alert rules:
│   │                                      #   ServiceDown (critical, 1min)
│   │                                      #   HighResponseTime (warning, p95>1s)
│   │                                      #   LowIngestionRate (info)
│   │                                      #   LargeDataSize (warning, >10MB)
│   │                                      #   MLInferenceServiceDown (critical)
│   │                                      #   DataIngestionServiceDown (critical)
│   └── grafana/
│       ├── dashboards/
│       │   └── mlops-dashboard.json       # 7-panel auto-provisioned dashboard:
│       │                                  #   Service Health, Ingestion Rate,
│       │                                  #   Latency p95/p99, Data Size,
│       │                                  #   Total Ingestions, Avg Response,
│       │                                  #   Services Online
│       └── provisioning/
│           ├── datasources/
│           │   └── prometheus.yml
│           └── dashboards/
│               └── dashboard.yml
│
├── postman/
│   └── MLOps_Pipeline_Collection.json     # 15+ test scenarios:
│                                          #   ML Inference (health, predict, metrics)
│                                          #   Data Ingestion (ingest, retrieve, list)
│                                          #   Monitoring (Prometheus, Grafana)
│                                          #   Performance & Load Testing
│                                          #   Error Handling (400, 404 cases)
│
│  ══════════════════════════════════════
│  📁  SHARED
│  ══════════════════════════════════════
│
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_feature_engineering.ipynb
│   └── 03_model_selection.ipynb
│
├── docker-compose.yml                     # Local full-stack testing
├── .gitignore
├── requirements.txt
└── README.md
```
 
---

## Pipeline Components

### 1. 📦 Data Storage — MongoDB ✅
- Stores raw IEEE-CIS Fraud Detection CSVs as MongoDB collections
- Collections: `train_transaction`, `test_transaction`, `train_identity`, `test_identity`
- Indexed on `TransactionID` for fast lookups
- Deployed in private subnet, accessible only via bastion host

### 2. 🏪 Feature Store — Feast + Redis ✅
- **Offline store**: Parquet files for historical feature retrieval during training
- **Online store**: Redis for low-latency real-time feature serving at inference
- Flask API on port 6566 for feature push and pull
- Training pipeline fetches features via HTTP

### 3. 📊 Experiment Tracking — MLflow ✅
- Tracks all model runs, hyperparameters, and metrics
- Stores artifacts in S3 (not local disk)
- UI accessible via SSH tunnel through bastion host
- Experiments: `fraud_detection_xgboost`, `fraud_detection_lightgbm`, `fraud_detection_isolation_forest`

### 4. ⚙️ Training Pipeline — Apache Airflow ✅
- Orchestrates full training as a DAG
- Trains three models in parallel after data preparation
- Logs all results to MLflow automatically
- Selects best model based on F1-score

### 5. 🌐 Model Serving — FastAPI + Docker ✅
- REST API with `/predict`, `/batch-predict`, `/health`, `/metrics`, `/drift` endpoints
- Pydantic input validation, Gunicorn production server
- Predictions logged to PostgreSQL for drift comparison
- Containerized with Docker, deployed on AWS EC2

### 6. 🔥 Load Testing — Locust ✅
Four user behavior profiles:
- **MLModelUser** — standard mixed traffic
- **HeavyUser** — rapid-fire predictions
- **LightUser** — infrequent, low-intensity
- **BurstUser** — sudden traffic spikes

Distributed master + worker with Prometheus metrics export.

### 7. 📈 Metrics & Dashboarding — Prometheus + Grafana ✅
- 15-second scrape interval from all services
- 7-panel Grafana dashboard auto-provisioned from JSON
- Auto-refreshes every 10 seconds, dark theme

### 8. 📉 Statistical Drift — Prometheus Gauges ✅
- Drift score = normalized difference between current and baseline (mean + std)
- Tracks `tenure`, `MonthlyCharges`, `TotalCharges`
- `churn_feature_drift` gauge per feature exposed to Prometheus
- Four-phase simulator: baseline → feature drift → concept drift → normal

### 9. 🛡️ Drift Reports — Evidently AI ✅
- Fetches reference dataset from S3 and current predictions from PostgreSQL
- HTML reports: `DataDriftPreset` + `DataQualityPreset`
- Per-feature reports for 5 key features
- All reports uploaded to S3 for audit trail

### 10. 🔄 CI/CD — GitHub Actions + Pulumi ✅
**Strategy**: Destroy-and-recreate (clean slate on every deploy)

**Pipeline jobs:**
- **test** (parallel): unit tests for both microservices
- **deploy-infrastructure**: Pulumi destroys old stack, recreates VPC + EC2 + ECR + EIP
- **build-and-push** (parallel): Docker build → tag → push to AWS ECR
- **deploy-services**: SSH into EC2 → configure monitoring → pull ECR images → docker-compose up → health check

**Prometheus alert rules (6 total):**
- `ServiceDown` — critical, fires after 1 min
- `HighResponseTime` — warning, p95 > 1s for 5 min
- `LowIngestionRate` — info, < 0.01 req/s for 10 min
- `LargeDataSize` — warning, p95 > 10MB
- `MLInferenceServiceDown` — critical, 2 min
- `DataIngestionServiceDown` — critical, 2 min

---

## CI/CD Workflow

### GitHub Secrets Required

| Secret | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `EC2_SSH_KEY` | Private SSH key for EC2 SSH access |
| `SSH_PUBLIC_KEY` | Public SSH key for EC2 key pair creation |
| `PULUMI_ACCESS_TOKEN` | Pulumi cloud token |

### Trigger
```bash
git add .
git commit -m "your changes"
git push origin main
# GitHub Actions triggers automatically
# Full deployment: ~10-15 minutes
```

### What Happens Automatically on Push
1. Unit tests run in parallel for both services
2. Pulumi destroys existing AWS stack completely
3. Fresh VPC, subnet, security groups, ECR repos, EC2, EIP provisioned
4. Docker images built and pushed to AWS ECR
5. SSH into new EC2, deploy all services via Docker Compose
6. Health checks validate `/health` endpoints return 200
7. All service URLs printed in Action logs

---

## Getting Started

### Prerequisites
- AWS account with programmatic access
- Python 3.10+, Docker, Docker Compose, Pulumi CLI
- GitHub account (for CI/CD)
- IEEE-CIS Fraud Detection dataset (Kaggle)

### Deploy via CI/CD (Recommended)
```bash
# 1. Fork and clone the repo
git clone https://github.com/<your-username>/mlops-fraud-detection

# 2. Add GitHub Secrets (Settings → Secrets → Actions):
#    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
#    EC2_SSH_KEY, SSH_PUBLIC_KEY, PULUMI_ACCESS_TOKEN

# 3. Push to main — everything deploys automatically
git push origin main
# Watch the Actions tab on GitHub
```

### Deploy Training Stack Manually
```bash
aws configure

cd infrastructure/mongodb && pulumi up --yes
cd infrastructure/feast  && pulumi up --yes
cd infrastructure/mlflow && pulumi up --yes
cd infrastructure/airflow && pulumi up --yes

# Access MLflow UI
ssh -L 5000:<mlflow_ip>:5000 ubuntu@<bastion_ip>
# Open: http://localhost:5000

# Access Airflow UI
ssh -L 8080:<airflow_ip>:8080 ubuntu@<bastion_ip>
# Open: http://localhost:8080  |  Login: admin / admin123
```

### Run Local Stack
```bash
docker-compose up --build -d
# FastAPI ML:    http://localhost:8001/docs
# FastAPI Data:  http://localhost:8002/docs
# Prometheus:    http://localhost:9090
# Grafana:       http://localhost:3000  (admin/admin)
# Locust:        http://localhost:8089
```

### Run Drift Monitoring
```bash
# Statistical drift
cd monitoring/prometheus_drift
docker-compose up -d
python3 drift_simulator.py

# Evidently AI reports
cd monitoring/evidently_drift
python3 prediction_generator.py --num-samples 100
python3 monitor.py
# Reports → s3://<your-bucket>/reports/
```

---

## API Reference

| Method | Endpoint | Service | Description |
|---|---|---|---|
| GET | `/health` | Both | Health check |
| POST | `/predict` | ML (8001) | Single prediction |
| GET | `/metrics` | Both | Prometheus metrics |
| POST | `/ingest` | Data (8002) | Ingest a data record |
| GET | `/data/<id>` | Data (8002) | Retrieve record by ID |
| GET | `/data` | Data (8002) | List recent records |
| GET | `/drift` | ML (8001) | Current drift scores |
| GET | `/model-info` | ML (8001) | Model metadata |
| GET | `/sample` | ML (8001) | Sample input for testing |

### Example Prediction
```bash
curl -X POST "http://localhost:8001/predict" \
  -H "Content-Type: application/json" \
  -d '{"features": [1.5, 2.3, 4.1, 0.8]}'
# {"prediction": 0.73, "model_version": "1.0.0", "timestamp": 1748000000.0}
```

### Example Drift Check
```bash
curl http://localhost:8001/drift
# {"tenure": 0.12, "MonthlyCharges": 0.45, "TotalCharges": 0.08}
```

---

## Roadmap

### Phase 1 — Training Pipeline ✅
- [x] MongoDB + Feast + MLflow + Airflow
- [x] Parallel model training (XGBoost, LightGBM, IsolationForest)
- [x] Automated model selection by F1-score

### Phase 2 — Model Serving ✅
- [x] FastAPI + Gunicorn + Docker on AWS EC2
- [x] PostgreSQL prediction logging

### Phase 3 — Load Testing & Metrics ✅
- [x] Locust with 4 user profiles
- [x] Prometheus + Grafana 7-panel dashboard

### Phase 4 — Drift Monitoring ✅
- [x] Statistical drift via Prometheus gauges (4-phase simulation)
- [x] Evidently AI full + per-feature reports → S3

### Phase 5 — CI/CD ✅
- [x] GitHub Actions: test → infra → build → deploy
- [x] Pulumi destroy-and-recreate strategy
- [x] AWS ECR Docker image registry
- [x] 6 Prometheus alert rules
- [x] 7-panel Grafana dashboard auto-provisioned
- [x] Postman collection with 15+ test scenarios

---

## Dataset

[IEEE-CIS Fraud Detection](https://www.kaggle.com/c/ieee-fraud-detection) — Kaggle dataset with anonymized transaction data for binary fraud classification.

| File | Description |
|---|---|
| `train_transaction.csv` | Training transactions (~590k rows) |
| `test_transaction.csv` | Test transactions (~507k rows) |
| `train_identity.csv` | Training identity data (~144k rows) |
| `test_identity.csv` | Test identity data (~141k rows) |

---

## Author

Built as a complete MLOps learning portfolio covering infrastructure provisioning, feature stores, experiment tracking, pipeline orchestration, containerized model serving, load testing, real-time metrics, statistical drift detection, Evidently AI drift reporting, and fully automated CI/CD on AWS.
