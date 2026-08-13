# Daily Operational Checklist (Phase 8)

**Date**: YYYY-MM-DD
**Phase**: 8A (Dry Run) / 8B (Shadow Trading) / 8C (Stability)

## 1. System Vitality
- **Cycles Executed**: 
- **Uptime**: 
- **Average Cycle Latency**: 
- **P95 Cycle Latency**: 
- **Memory Usage**: 
- **CPU Usage**: 
- **Queue Depth**: 

## 2. Reliability State
- **Circuit Breaker Status**: NORMAL / WARNING / HALTED
- **UNKNOWN Executions**: 0
- **Recovery Events**: 0

## 3. Data Integrity
- **Journal Status**: OK
- **Research Dataset Status**: OK (Parquet written successfully)

## 4. Incident Summary
*(Record any anomalies classified strictly by Severity)*

| Severity | Description | Action Taken |
|----------|-------------|--------------|
| (P0/P1/P2/P3) | | |

* **P0 (Critical)**: Duplicate order, corrupted state -> Campaign Halted immediately.
* **P1 (High)**: Recovery failure -> Investigation required before continuing.
* **P2 (Medium)**: UNKNOWN resolved automatically -> Logged, campaign continues.
* **P3 (Low)**: Watchdog warning, API retry -> Monitoring.
