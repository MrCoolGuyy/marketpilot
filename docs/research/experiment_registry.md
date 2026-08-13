# MarketPilot Research Governance - Experiment Registry

Every change to the system's trading logic (thresholds, indicators, strategy parameters, risk models) must be documented as a formal experiment. 

**Rule:** No strategy goes to Live Trading without an accepted Experiment Report.

## Experiment Template

### 1. Metadata
- **Experiment ID**: EXP-0001
- **Date**: YYYY-MM-DD
- **Author**: Name
- **Status**: DRAFT | RUNNING | COMPLETED | REJECTED | ACCEPTED

### 2. Hypothesis
- **Goal**: What are you trying to improve? (e.g., "Reduce drawdown in RANGE regimes")
- **Hypothesis**: Why will this work? (e.g., "Adding an ADX > 25 filter will eliminate false breakouts")

### 3. Configuration & Artifacts
- **Config Hash**: The config_hash from the test run
- **Git Commit**: The commit containing the logic changes
- **Dataset Hash**: The dataset_hash from the Parquet files used
- **Analytics Version**: The version of the Research Engine used

### 4. Baseline vs Experiment Performance
| Metric | Baseline (Before) | Experiment (After) | Delta |
|--------|------------------|--------------------|-------|
| Win Rate | 55% | 61% | +6% |
| Expectancy | 0.3R | 0.5R | +0.2R |
| Profit Factor | 1.4 | 1.8 | +0.4 |
| Sharpe Ratio | 1.1 | 1.5 | +0.4 |
| Max Drawdown | -25% | -15% | +10% |

### 5. Conclusion & Governance
- **Is the improvement statistically significant?**
- **Did the Monte Carlo Probability of Ruin increase or decrease?**
- **Decision**: 
  - [ ] ACCEPTED (Merge to main, move to Paper Trading)
  - [ ] REJECTED (Revert changes, document failure)
