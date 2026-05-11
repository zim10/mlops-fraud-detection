# pipelines/training_pipeline.py
"""
Fraud Detection Training Pipeline - Airflow DAG
Trains XGBoost, LightGBM, and Isolation Forest models
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

default_args = {
    'owner': 'mlops',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'fraud_training_pipeline',
    default_args=default_args,
    description='Train fraud detection models',
    schedule_interval='@daily',
    catchup=False,
    tags=['fraud', 'training', 'ml']
)

def extract_data():
    """Extract data from PostgreSQL"""
    import pandas as pd
    from sqlalchemy import create_engine
    
    engine = create_engine('postgresql://user:pass@localhost:5432/fraud_detection')
    
    query = """
        SELECT * FROM transactions 
        WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
    """
    df = pd.read_sql_query(query, engine)
    df.to_csv('/tmp/transactions.csv', index=False)
    
    return '/tmp/transactions.csv'

def preprocess_data():
    """Preprocess and engineer features"""
    import pandas as pd
    import numpy as np
    
    df = pd.read_csv('/tmp/transactions.csv')
    
    # Feature engineering
    df['transaction_velocity'] = df['amount'] / df['time_since_last_transaction']
    df['hour_of_day'] = pd.to_datetime(df['timestamp']).dt.hour
    df['is_weekend'] = pd.to_datetime(df['timestamp']).dt.dayofweek >= 5
    df['amount_log'] = np.log1p(df['amount'])
    
    # Encode categorical features
    df = pd.get_dummies(df, columns=['merchant_category', 'user_country'])
    
    df.to_csv('/tmp/preprocessed_data.csv', index=False)
    
    return '/tmp/preprocessed_data.csv'

def train_xgboost():
    """Train XGBoost model"""
    import pandas as pd
    import xgboost as xgb
    import joblib
    import mlflow
    import mlflow.xgboost
    
    mlflow.set_tracking_uri('http://localhost:5000')
    mlflow.set_experiment('fraud-detection-xgboost')
    
    df = pd.read_csv('/tmp/preprocessed_data.csv')
    X = df.drop(['transaction_id', 'is_fraud', 'timestamp'], axis=1)
    y = df['is_fraud']
    
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=len(y[y==0]) / len(y[y==1])
    )
    
    with mlflow.start_run():
        model.fit(X, y)
        
        # Log model
        mlflow.xgboost.log_model(model, 'model')
        
        # Save locally
        joblib.dump(model, '/opt/models/xgboost_fraud_model.json')
    
    return 'XGBoost model trained'

def train_lightgbm():
    """Train LightGBM model"""
    import pandas as pd
    import lightgbm as lgb
    import joblib
    import mlflow
    import mlflow.lightgbm
    
    mlflow.set_tracking_uri('http://localhost:5000')
    mlflow.set_experiment('fraud-detection-lightgbm')
    
    df = pd.read_csv('/tmp/preprocessed_data.csv')
    X = df.drop(['transaction_id', 'is_fraud', 'timestamp'], axis=1)
    y = df['is_fraud']
    
    model = lgb.LGBMClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        class_weight='balanced'
    )
    
    with mlflow.start_run():
        model.fit(X, y)
        mlflow.lightgbm.log_model(model, 'model')
        model.booster_.save_model('/opt/models/lightgbm_fraud_model.txt')
    
    return 'LightGBM model trained'

def train_isolation_forest():
    """Train Isolation Forest for anomaly detection"""
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import IsolationForest
    import joblib
    import mlflow
    from mlflow.sklearn import log_model
    
    mlflow.set_tracking_uri('http://localhost:5000')
    mlflow.set_experiment('fraud-detection-isolation-forest')
    
    df = pd.read_csv('/tmp/preprocessed_data.csv')
    X = df.drop(['transaction_id', 'is_fraud', 'timestamp'], axis=1)
    
    # Select numeric features only
    X_numeric = X.select_dtypes(include=[np.number])
    
    # Handle inf/nan
    X_numeric = X_numeric.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    model = IsolationForest(
        n_estimators=100,
        contamination=0.01,
        random_state=42
    )
    
    with mlflow.start_run():
        model.fit(X_numeric)
        log_model(model, 'model')
        joblib.dump(model, '/opt/models/isolation_forest_model.pkl')
    
    return 'Isolation Forest model trained'

def evaluate_models():
    """Evaluate all trained models"""
    import pandas as pd
    import numpy as np
    from sklearn.metrics import roc_auc_score, precision_recall_fscore_support
    import joblib
    
    df = pd.read_csv('/tmp/preprocessed_data.csv')
    X = df.drop(['transaction_id', 'is_fraud', 'timestamp'], axis=1)
    y = df['is_fraud']
    
    results = {}
    
    # Evaluate XGBoost
    xgb_model = joblib.load('/opt/models/xgboost_fraud_model.json')
    xgb_preds = xgb_model.predict_proba(X)[:, 1]
    results['xgboost_auc'] = roc_auc_score(y, xgb_preds)
    
    # Evaluate LightGBM
    import lightgbm as lgb
    lgb_model = lgb.Booster(model_file='/opt/models/lightgbm_fraud_model.txt')
    lgb_preds = lgb_model.predict(X)
    results['lightgbm_auc'] = roc_auc_score(y, lgb_preds)
    
    # Evaluate Isolation Forest
    if_model = joblib.load('/opt/models/isolation_forest_model.pkl')
    if_scores = if_model.decision_function(X)
    results['isolation_forest_auc'] = roc_auc_score(y, -if_scores)
    
    print(f"Model Evaluation Results: {results}")
    
    return results

# DAG Tasks
extract = PythonOperator(
    task_id='extract_data',
    python_callable=extract_data,
    dag=dag
)

preprocess = PythonOperator(
    task_id='preprocess_data',
    python_callable=preprocess_data,
    dag=dag
)

train_xgb = PythonOperator(
    task_id='train_xgboost',
    python_callable=train_xgboost,
    dag=dag
)

train_lgb = PythonOperator(
    task_id='train_lightgbm',
    python_callable=train_lightgbm,
    dag=dag
)

train_if = PythonOperator(
    task_id='train_isolation_forest',
    python_callable=train_isolation_forest,
    dag=dag
)

evaluate = PythonOperator(
    task_id='evaluate_models',
    python_callable=evaluate_models,
    dag=dag
)

# Task dependencies
extract >> preprocess >> [train_xgb, train_lgb, train_if] >> evaluate