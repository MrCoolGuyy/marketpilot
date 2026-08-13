import pytest
from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
from marketpilot.notifications.telegram_notifier import TelegramNotifier
from marketpilot.config.settings import TelegramSettings
from pydantic import SecretStr

@pytest.fixture
def test_settings():
    return TelegramSettings(
        enabled=True,
        bot_token=SecretStr("fake_token"),
        chat_id="12345",
        send_startup=True,
        send_circuit_breaker=True
    )

def test_telegram_format_startup(test_settings):
    notifier = TelegramNotifier(test_settings)
    event = NotificationEvent(
        event_type=NotificationType.STARTUP,
        message_data={"version": "1.0", "git_commit": "abc", "config_hash": "xyz", "start_time": "now"}
    )
    
    msg = notifier._format_message(event)
    assert "MarketPilot RC-1 Started" in msg
    assert "Version: 1.0" in msg
    assert "Config Hash: xyz" in msg

def test_telegram_format_circuit_breaker(test_settings):
    notifier = TelegramNotifier(test_settings)
    event = NotificationEvent(
        event_type=NotificationType.CIRCUIT_BREAKER_HALTED,
        decision_id="DEC-123",
        message_data={"reason": "Test Error", "timestamp": "now"}
    )
    
    msg = notifier._format_message(event)
    assert "HALTED" in msg
    assert "Reason: Test Error" in msg
    assert "Decision ID: DEC-123" in msg
