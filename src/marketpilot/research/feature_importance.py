"""
MarketPilot Research - Feature Importance.

Calculates Mutual Information between discrete market features and trade outcomes.
"""

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif

class FeatureAnalyzer:
    @staticmethod
    def calculate_mutual_information(features_df: pd.DataFrame, outcomes_series: pd.Series) -> dict[str, float]:
        """
        Calculates Mutual Information scores for each feature column against the trade outcome.
        Higher score = feature is more predictive of win/loss.
        """
        if features_df.empty or len(features_df) != len(outcomes_series):
            return {}
            
        # Select only numeric columns
        numeric_df = features_df.select_dtypes(include=[np.number])
        if numeric_df.empty:
            return {}
            
        # Drop NaNs
        mask = numeric_df.notna().all(axis=1) & outcomes_series.notna()
        numeric_df = numeric_df[mask]
        y = outcomes_series[mask]
        
        if numeric_df.empty:
            return {}
            
        mi_scores = mutual_info_classif(numeric_df, y, random_state=42)
        
        result = {}
        for idx, col in enumerate(numeric_df.columns):
            result[col] = float(mi_scores[idx])
            
        return result
