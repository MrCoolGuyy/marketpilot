"""
MarketPilot Research - Confidence Calibration.

Evaluates how well the Strategy Engine's confidence scores align with actual win rates.
"""

import numpy as np
import pandas as pd

class ConfidenceCalibrator:
    @staticmethod
    def calculate_brier_score(confidences: np.ndarray, outcomes: np.ndarray) -> float:
        """
        Calculates the Brier Score (Mean Squared Error of predictions).
        confidences: Array of floats (0.0 to 1.0) representing predictive confidence.
        outcomes: Array of ints (1 for win, 0 for loss).
        Lower is better. Perfect = 0.0. Worst = 1.0.
        """
        if len(confidences) == 0:
            return 0.0
        return float(np.mean((confidences - outcomes) ** 2))
        
    @staticmethod
    def expected_calibration_error(confidences: np.ndarray, outcomes: np.ndarray, bins: int = 10) -> float:
        """
        Calculates the Expected Calibration Error (ECE).
        Divides predictions into bins and measures average deviation from true win rate.
        """
        if len(confidences) == 0:
            return 0.0
            
        bin_edges = np.linspace(0.0, 1.0, bins + 1)
        ece = 0.0
        
        for i in range(bins):
            bin_lower = bin_edges[i]
            bin_upper = bin_edges[i+1]
            
            # Find indices of predictions that fall into this bin
            in_bin = (confidences >= bin_lower) & (confidences < bin_upper)
            if i == bins - 1:
                in_bin = in_bin | (confidences == 1.0)
                
            n_in_bin = np.sum(in_bin)
            if n_in_bin > 0:
                avg_confidence = np.mean(confidences[in_bin])
                true_win_rate = np.mean(outcomes[in_bin])
                
                # Weight by bin size
                ece += (n_in_bin / len(confidences)) * abs(avg_confidence - true_win_rate)
                
        return float(ece)
