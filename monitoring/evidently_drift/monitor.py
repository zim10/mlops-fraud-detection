# monitoring/evidently_drift/monitor.py
"""
Evidently AI Drift Monitoring
Fetches predictions and generates drift reports
"""
import pandas as pd
from sqlalchemy import create_engine
import boto3
from evidently.dashboard import Dashboard
from evidently.tabs import DataDriftTab, CatTargetDriftTab
import os
from datetime import datetime, timedelta

class DriftMonitor:
    """Monitor drift using Evidently AI"""
    
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL', 'postgresql://fraud:password@localhost:5432/fraud_detection')
        self.s3_bucket = os.getenv('S3_BUCKET', 'mlops-fraud-detection-reports')
        self.engine = create_engine(self.db_url)
        self.s3_client = boto3.client('s3')
    
    def fetch_predictions(self, days: int = 7) -> pd.DataFrame:
        """Fetch prediction records from database"""
        query = f"""
            SELECT * FROM prediction_records 
            WHERE created_at >= CURRENT_DATE - INTERVAL '{days} days'
            ORDER BY created_at DESC
        """
        return pd.read_sql_query(query, self.engine)
    
    def fetch_reference_data(self, days: int = 30) -> pd.DataFrame:
        """Fetch reference data (older baseline)"""
        query = f"""
            SELECT * FROM prediction_records 
            WHERE created_at >= CURRENT_DATE - INTERVAL '{days} days'
            AND created_at < CURRENT_DATE - INTERVAL '7 days'
            ORDER BY created_at DESC
            LIMIT 10000
        """
        return pd.read_sql_query(query, self.engine)
    
    def calculate_drift_report(self, current_data: pd.DataFrame, reference_data: pd.DataFrame):
        """Generate drift report using Evidently"""
        # Select numeric features for drift analysis
        feature_columns = [
            'amount', 'fraud_probability',
            'time_since_last_transaction', 'user_risk_score'
        ]
        
        # Filter to available columns
        available_cols = [c for c in feature_columns if c in current_data.columns]
        
        current = current_data[available_cols].copy()
        reference = reference_data[available_cols].copy()
        
        # Create dashboard
        dashboard = Dashboard(tabs=[
            DataDriftTab(),
            CatTargetDriftTab()
        ])
        
        dashboard.calculate(
            reference_data=reference,
            current_data=current,
            column_mapping=None
        )
        
        return dashboard
    
    def save_report(self, dashboard, report_name: str):
        """Save report locally and upload to S3"""
        # Save locally
        local_path = f"reports/{report_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        os.makedirs('reports', exist_ok=True)
        dashboard.save_html(local_path)
        
        # Upload to S3
        s3_path = f"drift-reports/{report_name}/{os.path.basename(local_path)}"
        try:
            self.s3_client.upload_file(local_path, self.s3_bucket, s3_path)
            print(f"Report uploaded to s3://{self.s3_bucket}/{s3_path}")
        except Exception as e:
            print(f"S3 upload failed: {e}")
        
        return local_path
    
    def run_monitoring(self):
        """Run full drift monitoring cycle"""
        print("Starting drift monitoring...")
        
        # Fetch data
        current = self.fetch_predictions(days=7)
        reference = self.fetch_reference_data(days=30)
        
        if current.empty or reference.empty:
            print("Insufficient data for drift analysis")
            return None
        
        # Generate report
        dashboard = self.calculate_drift_report(current, reference)
        
        # Save report
        report_path = self.save_report(dashboard, "fraud_drift_analysis")
        
        print(f"Drift report saved to: {report_path}")
        
        return report_path

if __name__ == "__main__":
    monitor = DriftMonitor()
    monitor.run_monitoring()