import re

file_path = 'src/marketpilot/cli.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace imports
content = re.sub(
    r'from marketpilot\.telegram\.notifier import TelegramNotifier',
    'from marketpilot.notifications.telegram_notifier import TelegramNotifier',
    content
)
content = re.sub(
    r'from marketpilot\.telegram\.models import .*',
    'from marketpilot.notifications.notification_models import NotificationEvent, NotificationType',
    content
)

# 2. PaperActionRejectedEvent
def replace_rejected(m):
    indent = m.group(1)
    symbol = m.group(2)
    action = m.group(3)
    reason = m.group(4)
    return f'{indent}await notifier.notify(NotificationEvent(event_type=NotificationType.PAPER_TRADE, message_data={{"message": f"⚠️ [PAPER ONLY] Action Rejected\\n\\nSymbol: {{{symbol}}}\\nAction: {{{action}}}\\nReason: {{{reason}}}\\n\\nNo real order was placed."}}))'

content = re.sub(
    r'^([ \t]*)await (?:telegram|notifier)\.notify\(\s*PaperActionRejectedEvent\(\s*symbol=(.*?),\s*action=(.*?),\s*reason=(.*?)\s*\)\s*\)',
    replace_rejected,
    content,
    flags=re.DOTALL | re.MULTILINE
)

# 3. PaperPositionOpenedEvent
def replace_opened(m):
    indent = m.group(1)
    symbol = m.group(2)
    direction = m.group(3)
    qty = m.group(4)
    entry = m.group(5)
    return f'{indent}await notifier.notify(NotificationEvent(event_type=NotificationType.PAPER_TRADE, message_data={{"message": f"🟢 [PAPER ONLY] Position Opened\\n\\nSymbol: {{{symbol}}}\\nDirection: {{{direction}}}\\nQty: {{{qty}}}\\nEntry: {{{entry}}}\\n\\nNo real order was placed."}}))'

content = re.sub(
    r'^([ \t]*)await (?:telegram|notifier)\.notify\(\s*PaperPositionOpenedEvent\(\s*symbol=(.*?),\s*direction=(.*?),\s*quantity=(.*?),\s*entry_price=(.*?)\s*\)\s*\)',
    replace_opened,
    content,
    flags=re.DOTALL | re.MULTILINE
)

# 4. PaperPositionClosedEvent
def replace_closed(m):
    indent = m.group(1)
    symbol = m.group(2)
    direction = m.group(3)
    exit_p = m.group(4)
    pnl = m.group(5)
    return f'{indent}await notifier.notify(NotificationEvent(event_type=NotificationType.PAPER_TRADE, message_data={{"message": f"🔴 [PAPER ONLY] Position Closed\\n\\nSymbol: {{{symbol}}}\\nDirection: {{{direction}}}\\nExit: {{{exit_p}}}\\nNet PnL: {{{pnl}}}\\n\\nNo real order was placed."}}))'

content = re.sub(
    r'^([ \t]*)await (?:telegram|notifier)\.notify\(\s*PaperPositionClosedEvent\(\s*symbol=(.*?),\s*direction=(.*?),\s*exit_price=(.*?),\s*net_pnl=(.*?)\s*\)\s*\)',
    replace_closed,
    content,
    flags=re.DOTALL | re.MULTILINE
)

# 5. HistoricalRunCompletedEvent (backtest)
def replace_hist_backtest(m):
    indent = m.group(1)
    run_type = m.group(2)
    symbol = m.group(3)
    interval = m.group(4)
    ret = m.group(5)
    return f"{indent}await notifier.notify(NotificationEvent(event_type=NotificationType.EXECUTION_SUCCESS, message_data={{\"message\": f\"📊 [HISTORICAL ONLY] Run Completed\\nType: backtest\\nSymbol: {{{symbol}}} ({{{interval}}})\\nTotal Return: {{{ret}}}%\"}}))"

content = re.sub(
    r'^([ \t]*)await (?:telegram|notifier)\.notify\(\s*HistoricalRunCompletedEvent\(\s*run_type=(.*?),\s*symbol=(.*?),\s*interval=(.*?),\s*total_return_pct=(.*?)\s*\)\s*\)',
    replace_hist_backtest,
    content,
    flags=re.DOTALL | re.MULTILINE
)

# 6. HistoricalRunCompletedEvent (optimize)
def replace_hist_opt(m):
    indent = m.group(1)
    run_type = m.group(2)
    symbol = m.group(3)
    interval = m.group(4)
    best = m.group(5)
    return f"{indent}await notifier.notify(NotificationEvent(event_type=NotificationType.EXECUTION_SUCCESS, message_data={{\"message\": f\"📊 [HISTORICAL ONLY] Run Completed\\nType: optimize\\nSymbol: {{{symbol}}} ({{{interval}}})\\nBest: {{{best}}}\"}}))"

content = re.sub(
    r'^([ \t]*)await (?:telegram|notifier)\.notify\(\s*HistoricalRunCompletedEvent\(\s*run_type=(.*?),\s*symbol=(.*?),\s*interval=(.*?),\s*best_candidate_label=(.*?)\s*\)\s*\)',
    replace_hist_opt,
    content,
    flags=re.DOTALL | re.MULTILINE
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
