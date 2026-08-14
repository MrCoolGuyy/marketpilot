import os
from pathlib import Path
import re

file_path = "src/marketpilot/cli.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Imports
content = re.sub(
    r'from marketpilot\.telegram\.models import (?:PaperActionRejectedEvent|PaperPositionOpenedEvent|PaperPositionClosedEvent|HistoricalRunCompletedEvent).*?\n',
    'from marketpilot.notifications.notification_models import NotificationEvent, NotificationType\n',
    content
)

# Replace duplicate imports that might get introduced
content = re.sub(r'(from marketpilot\.notifications\.notification_models import NotificationEvent, NotificationType\n)+', 'from marketpilot.notifications.notification_models import NotificationEvent, NotificationType\n', content)

# 2. PaperActionRejectedEvent
# await telegram.notify(PaperActionRejectedEvent(symbol=symbol, action=..., reason=...))
def replace_rejected(m):
    symbol = m.group(1)
    action = m.group(2)
    reason = m.group(3)
    return f'await telegram.notify(NotificationEvent(event_type=NotificationType.PAPER_TRADE, message_data={{"message": f"⚠️ [PAPER ONLY] Action Rejected\\n\\nSymbol: {{{symbol}}}\\nAction: {{{action}}}\\nReason: {{{reason}}}\\n\\nNo real order was placed."}}))'

content = re.sub(
    r'await telegram\.notify\(\s*PaperActionRejectedEvent\(\s*symbol=(.*?),\s*action=(.*?),\s*reason=(.*?)\s*\)\s*\)',
    replace_rejected,
    content,
    flags=re.DOTALL
)

# 3. PaperPositionOpenedEvent
def replace_opened(m):
    symbol = m.group(1)
    direction = m.group(2)
    qty = m.group(3)
    entry = m.group(4)
    return f'await telegram.notify(NotificationEvent(event_type=NotificationType.PAPER_TRADE, message_data={{"message": f"🟢 [PAPER ONLY] Position Opened\\n\\nSymbol: {{{symbol}}}\\nDirection: {{{direction}}}\\nQty: {{{qty}}}\\nEntry: {{{entry}}}\\n\\nNo real order was placed."}}))'

content = re.sub(
    r'await telegram\.notify\(\s*PaperPositionOpenedEvent\(\s*symbol=(.*?),\s*direction=(.*?),\s*quantity=(.*?),\s*entry_price=(.*?)\s*\)\s*\)',
    replace_opened,
    content,
    flags=re.DOTALL
)

# 4. PaperPositionClosedEvent
def replace_closed(m):
    symbol = m.group(1)
    direction = m.group(2)
    exit = m.group(3)
    pnl = m.group(4)
    return f'await telegram.notify(NotificationEvent(event_type=NotificationType.PAPER_TRADE, message_data={{"message": f"🔴 [PAPER ONLY] Position Closed\\n\\nSymbol: {{{symbol}}}\\nDirection: {{{direction}}}\\nExit: {{{exit}}}\\nNet PnL: {{{pnl}}}\\n\\nNo real order was placed."}}))'

content = re.sub(
    r'await telegram\.notify\(\s*PaperPositionClosedEvent\(\s*symbol=(.*?),\s*direction=(.*?),\s*exit_price=(.*?),\s*net_pnl=(.*?)\s*\)\s*\)',
    replace_closed,
    content,
    flags=re.DOTALL
)

# 5. HistoricalRunCompletedEvent (backtest)
def replace_hist_backtest(m):
    run_type = m.group(1)
    symbol = m.group(2)
    interval = m.group(3)
    ret = m.group(4)
    return f'await telegram.notify(NotificationEvent(event_type=NotificationType.EXECUTION_SUCCESS, message_data={{"message": f"📊 [HISTORICAL ONLY] Run Completed\\nType: {{{run_type}}}\\nSymbol: {{{symbol}}} ({{{interval}}})\\nTotal Return: {{{ret}}}%"}}))'

content = re.sub(
    r'await telegram\.notify\(\s*HistoricalRunCompletedEvent\(\s*run_type=(.*?),\s*symbol=(.*?),\s*interval=(.*?),\s*total_return_pct=(.*?)\s*\)\s*\)',
    replace_hist_backtest,
    content,
    flags=re.DOTALL
)

# 6. HistoricalRunCompletedEvent (optimize)
def replace_hist_opt(m):
    run_type = m.group(1)
    symbol = m.group(2)
    interval = m.group(3)
    best = m.group(4)
    return f'await telegram.notify(NotificationEvent(event_type=NotificationType.EXECUTION_SUCCESS, message_data={{"message": f"📊 [HISTORICAL ONLY] Run Completed\\nType: {{{run_type}}}\\nSymbol: {{{symbol}}} ({{{interval}}})\\nBest: {{{best}}}"}}))'

content = re.sub(
    r'await telegram\.notify\(\s*HistoricalRunCompletedEvent\(\s*run_type=(.*?),\s*symbol=(.*?),\s*interval=(.*?),\s*best_candidate_label=(.*?)\s*\)\s*\)',
    replace_hist_opt,
    content,
    flags=re.DOTALL
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
