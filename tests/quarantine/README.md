# Legacy Test Quarantine

This directory contains legacy tests that expect pre-sealed interfaces which are either non-existent or structurally incompatible with the sealed MarketPilot deterministic architecture (e.g. Risk Engine vs RiskManagerService).

Because this repository did not have prior Git history before Phase 1, these files are preserved here rather than immediately deleted, allowing future cleanup phases to explicitly decide on their removal.

## Quarantined Files
- `test_demo.py` (Expected `DemoExecutionService` referencing legacy `RiskManagerService`)
- `test_optimization.py` (Expected monolithic legacy models like `RiskAssessment`)
- `test_paper.py` (Expected legacy `RiskAssessment`)
- `test_research.py` (Expected legacy `RiskManagerService`)
- `test_risk.py` (Expected legacy `RiskAssessment`)
- `test_scanner.py` (Expected monolithic `ScannerService`)
- `test_strategy.py` (Expected monolithic `StrategyService`)
- `test_cli.py` (Cascading import failures from legacy models)
- `test_backtest.py` (Cascading import failures from legacy models)
- `test_dashboard.py` (Expected non-existent `create_app` factory)
- `test_autopilot.py` (Cascading import failures from legacy models via demo service)
