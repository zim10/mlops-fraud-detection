# monitoring/prometheus_drift/drift_simulator.py
"""
4-Phase Drift Simulation for Fraud Detection
"""
import numpy as np
from typing import Dict
import time

class DriftSimulator:
    """
    Simulates 4 phases of drift:
    Phase 1: No drift (baseline)
    Phase 2: Gradual feature drift
    Phase 3: Concept drift
    Phase 4: Return to normal
    """
    
    def __init__(self):
        self.current_phase = 1
        self.phase_durations = {
            1: 60,  # Phase 1: 60 seconds
            2: 120, # Phase 2: 120 seconds
            3: 90,  # Phase 3: 90 seconds
            4: 60   # Phase 4: 60 seconds
        }
        self.phase_start = time.time()
        
        # Feature names for drift tracking
        self.feature_names = [
            'transaction_amount',
            'time_since_last_transaction',
            'user_risk_score',
            'merchant_fraud_rate',
            'account_age_days'
        ]
    
    def get_current_phase(self) -> int:
        """Get current phase based on time"""
        elapsed = time.time() - self.phase_start
        
        if elapsed > sum(list(self.phase_durations.values())[:self.current_phase]):
            if self.current_phase < 4:
                self.current_phase += 1
                self.phase_start = time.time()
        
        return self.current_phase
    
    def get_phase_description(self) -> str:
        """Get description of current phase"""
        descriptions = {
            1: "No drift - baseline distribution",
            2: "Gradual feature drift - feature distributions shifting",
            3: "Concept drift - relationship between features and labels changing",
            4: "Return to normal - distributions stabilizing"
        }
        return descriptions.get(self.current_phase, "Unknown phase")
    
    def get_feature_drift_scores(self) -> Dict[str, float]:
        """Calculate feature drift scores based on phase"""
        scores = {}
        
        phase_factors = {
            1: 0.01,   # No drift
            2: 0.15,   # Moderate drift
            3: 0.25,   # High drift
            4: 0.08    # Stabilizing
        }
        
        drift_factor = phase_factors.get(self.current_phase, 0.01)
        
        for feature in self.feature_names:
            # Add some noise to make it realistic
            base_score = drift_factor * np.random.uniform(0.8, 1.2)
            scores[feature] = round(min(1.0, base_score), 4)
        
        return scores
    
    def get_concept_drift_score(self) -> float:
        """Calculate concept drift score"""
        concept_drift = {
            1: 0.02,
            2: 0.08,
            3: 0.35,
            4: 0.05
        }
        
        base_score = concept_drift.get(self.current_phase, 0.02)
        return round(base_score * np.random.uniform(0.9, 1.1), 4)
    
    def get_feature_drift_factor(self) -> float:
        """Get multiplicative factor for feature drift"""
        drift_scores = self.get_feature_drift_scores()
        return 1.0 + sum(drift_scores.values()) / len(drift_scores)
    
    def set_phase(self, phase: int):
        """Manually set the current phase"""
        self.current_phase = phase
        self.phase_start = time.time()
    
    def reset(self):
        """Reset to phase 1"""
        self.current_phase = 1
        self.phase_start = time.time()