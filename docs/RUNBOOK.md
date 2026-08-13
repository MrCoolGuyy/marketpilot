# MarketPilot Operational Runbook

This document is the absolute source of truth for operating the MarketPilot daemon in Production (including Dry Run, Shadow Trading, and Live environments). 
If you cannot safely operate the system using ONLY this document, the runbook is incomplete.

## 1. Daemon Lifecycle

### Starting the Daemon
The daemon must always be started using the official CLI entrypoint to ensure environment variables and config hashes are correctly initialized.
\\\ash
# Start in the foreground (for monitoring)
uv run marketpilot daemon start

# Start as a background service (Linux systemd/Windows service equivalent)
uv run marketpilot daemon start --detached
\\\

### Stopping the Daemon (Graceful Shutdown)
**NEVER SIGKILL (kill -9) the daemon.** Always use SIGTERM or SIGINT (Ctrl+C).
The daemon intercepts these signals to perform a graceful shutdown:
1. Stops the Scheduler (no new cycles).
2. Drains the active Event Queue.
3. Completes pending Reconciliation.
4. Flushes the Journal to disk/database.
5. Persists the Position Manager state.
6. Exits with code 0.

## 2. Configuration Management

### Changing Configuration
**Rule: CONFIGURATION FREEZE IS ACTIVE DURING CAMPAIGNS.**
During Phase 8A-8C, you may **not** change strategies, thresholds, EMA/ATR params, or risk rules. 
If an emergency change is required:
1. The current Campaign is instantly voided.
2. Update config.yaml.
3. Restart the daemon. 
4. The system will log a new config_hash.
5. You must begin a new Phase 8A Dry Run.

## 3. Incident Management & Circuit Breakers

### Reading Incidents
When an anomaly occurs, check the Audit Journal (logs/audit.jsonl). Look for lines where event_type="WATCHDOG_ALERT" or event_type="CIRCUIT_BREAKER_TRIPPED".

### Handling a HALTED Circuit Breaker
If the Watchdog detects a cycle hang >90s, or Execution fails 5x consecutively, the Circuit Breaker transitions to HALTED.
1. **Symptom**: The daemon stops placing orders but remains alive.
2. **Diagnosis**: Check the latest Watchdog and HealthMonitor logs to find the stalling engine.
3. **Resolution**:
   - Manually verify Exchange status (is Bybit down?).
   - If a local state issue, safely restart the daemon (Graceful Shutdown -> Start).
   - The Recovery Engine will automatically reconstruct state on boot.

## 4. Recovery & Reconciliation

### Restoring the Journal
If the Journal DB is corrupted:
1. Stop the daemon.
2. Locate the most recent backup in ackups/journal/.
3. Overwrite data/journal.db with the backup.
4. Start the daemon. The Recovery Engine will poll the exchange for any missing trades since the backup timestamp.

### Verifying Reconciliation
If ReconciliationCompletedEvent throws an error or reports a mismatch:
1. Extract the decision_id from the log.
2. Query the Exchange API manually for the client_order_id (which equals decision_id).
3. Compare the Exchange's executed QTY/Price with the TradePlan in the Journal.
4. If a partial fill occurred during an unrecoverable crash, manually close the remainder of the position via the Exchange UI and append a manual TradeExecutionRecord to the Journal.

---
*Maintained by the MarketPilot Principal Engineering Team. Do not operate without understanding these procedures.*

## 5. Observability (Phase 6A)

### Operational Dashboard
The Mission Control Dashboard provides a real-time operational view without mutating state.
- **URL**: http://localhost:8000/ (When the daemon is running)
- **Features**: Live view of Daemon Status, Health Monitors, Engine Metrics, and Circuit Breaker states using lightweight HTMX.

### Telegram Notifications
Real-time critical alerts are pushed via Telegram.
- **Configuration**: Set TELEGRAM_ENABLED=true, TELEGRAM_BOT_TOKEN, and TELEGRAM_CHAT_ID in .env.
- **Alert Types**: Startup, Shutdown, Circuit Breaker (Halted/Recovered), Recovery events, Executions, Daily Summaries, and Critical Incidents.
