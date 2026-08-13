"""Tests for Telegram Notifications."""

import json
from decimal import Decimal
from unittest.mock import patch, MagicMock

import httpx
import pytest

from marketpilot.config.settings import TelegramSettings
from marketpilot.models.strategy import SignalDirection
from marketpilot.telegram.models import PaperPositionOpenedEvent
from marketpilot.telegram.notifier import TelegramNotifier


def test_disabled_makes_no_requests():
    settings = TelegramSettings(enabled=False, bot_token="fake", chat_id="123")
    notifier = TelegramNotifier(settings)
    assert not notifier.is_enabled
    
    event = PaperPositionOpenedEvent(
        symbol="BTCUSDT",
        direction=SignalDirection.LONG,
        quantity=Decimal("1"),
        entry_price=Decimal("1000")
    )
    
    with patch("httpx.AsyncClient.post") as mock_post:
        import asyncio
        asyncio.run(notifier.notify(event))
        mock_post.assert_not_called()


def test_incomplete_makes_no_requests():
    # Missing bot token
    from pydantic import SecretStr
    settings = TelegramSettings(enabled=True, chat_id="123", bot_token=SecretStr(""))
    notifier = TelegramNotifier(settings)
    assert not notifier.is_enabled


def test_safe_formatters():
    event = PaperPositionOpenedEvent(
        symbol="BTCUSDT",
        direction=SignalDirection.LONG,
        quantity=Decimal("0.5"),
        entry_price=Decimal("1000")
    )
    text = event.render()
    assert "[PAPER ONLY]" in text
    assert "No real order was placed" in text
    assert "BTCUSDT" in text
    assert "0.5000" in text


@pytest.mark.asyncio
async def test_notify_success():
    settings = TelegramSettings(enabled=True, bot_token="fake_token", chat_id="12345")
    notifier = TelegramNotifier(settings)
    assert notifier.is_enabled
    
    event = PaperPositionOpenedEvent(
        symbol="BTCUSDT",
        direction=SignalDirection.LONG,
        quantity=Decimal("1"),
        entry_price=Decimal("1000")
    )
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    
    with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
        await notifier.notify(event)
        
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert "botfake_token" in url
        
        kwargs = mock_post.call_args[1]
        assert kwargs["json"]["chat_id"] == "12345"
        assert "[PAPER ONLY]" in kwargs["json"]["text"]


@pytest.mark.asyncio
async def test_notify_failure_no_raise():
    settings = TelegramSettings(enabled=True, bot_token="fake", chat_id="123")
    notifier = TelegramNotifier(settings)
    
    event = PaperPositionOpenedEvent(
        symbol="BTCUSDT", direction=SignalDirection.LONG,
        quantity=Decimal("1"), entry_price=Decimal("1000")
    )
    
    # Test Timeout Exception
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("timeout")) as mock_post:
        await notifier.notify(event)
        # 1 initial + 2 retries = 3 calls
        assert mock_post.call_count == 3
        
    # Test 4xx Response (no retry)
    mock_400 = MagicMock()
    mock_400.status_code = 400
    with patch("httpx.AsyncClient.post", return_value=mock_400) as mock_post:
        await notifier.notify(event)
        assert mock_post.call_count == 1
        
    # Test 5xx Response (retry)
    mock_500 = MagicMock()
    mock_500.status_code = 500
    with patch("httpx.AsyncClient.post", return_value=mock_500) as mock_post:
        await notifier.notify(event)
        assert mock_post.call_count == 3
