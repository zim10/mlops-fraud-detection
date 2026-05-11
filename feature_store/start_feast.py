# feature_store/start_feast.py
"""
Feast Flask Server for Online Feature Serving
"""
from flask import Flask, request, jsonify
import pandas as pd
from feast import FeatureStore
import os

app = Flask(__name__)

# Initialize feature store
fs = FeatureStore(repo_path=os.path.dirname(__file__))

@app.route('/get-online-features', methods=['POST'])
def get_online_features():
    """Retrieve online features for a list of entity keys"""
    data = request.json
    entity_keys = data.get('entity_keys', [])
    
    try:
        features = fs.get_online_features(
            entity_rows=[{'transaction_id': k} for k in entity_keys],
            feature_refs=[
                'transaction_features:amount_stats_1h',
                'transaction_features:velocity_24h',
                'transaction_features:user_risk_score',
                'merchant_features:fraud_rate',
                'user_features:account_age_days'
            ]
        )
        
        df = features.to_df()
        return jsonify(df.to_dict(orient='records'))
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ingest-batch', methods=['POST'])
def ingest_batch():
    """Ingest batch features into online store"""
    data = request.json
    feature_views = data.get('feature_views', [])
    
    try:
        fs.materialize(
            start_date=pd.Timestamp(data.get('start_date')),
            end_date=pd.Timestamp(data.get('end_date')),
            feature_refs=feature_views
        )
        return jsonify({'status': 'success'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888, debug=True)