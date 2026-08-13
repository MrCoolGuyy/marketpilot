"""Tests for Candidate Autopilot."""

import pytest
from decimal import Decimal

from marketpilot.config.settings import AppSettings
from marketpilot.models.autopilot import AutopilotStatus
from marketpilot.models.strategy import SignalDirection

@pytest.mark.asyncio
async def test_autopilot_default_off():
    """Verify autopilot execution is OFF by default."""
    settings = AppSettings()
    assert not settings.demo.auto_submit_enabled
    assert not settings.demo.kill_switch
    assert settings.demo.max_daily_trades == 5
    
@pytest.mark.asyncio
async def test_autopilot_kill_switch(monkeypatch):
    """Verify kill switch blocks execution entirely."""
    settings = AppSettings()
    settings.demo.kill_switch = True
    
    from marketpilot.autopilot.service import AutopilotService
    service = AutopilotService(settings)
    
    decision = await service.run_cycle()
    assert decision is None

@pytest.mark.asyncio
async def test_autopilot_daily_limit_guard(monkeypatch):
    """Verify max daily trades guard."""
    settings = AppSettings()
    
    from marketpilot.autopilot.service import AutopilotService
    service = AutopilotService(settings)
    
    # Mock daily records
    monkeypatch.setattr(service, "store_records_today", lambda: [1,2,3,4,5])
    
    # Mock equity
    from unittest.mock import AsyncMock
    mock_client = AsyncMock()
    mock_client._call.return_value = {"result": {"list": [{"totalEquity": "10000"}]}}
    mock_client.get_positions.return_value = {"result": {"list": []}}
    
    monkeypatch.setattr("marketpilot.autopilot.service.BybitClient", lambda s: mock_client)
    
    decision = await service.run_cycle()
    assert decision is None # Blocked by daily limit
