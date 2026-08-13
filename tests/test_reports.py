"""Tests for local report store."""

import json
from decimal import Decimal
from datetime import datetime, UTC
from pathlib import Path

import pytest
from pydantic import ValidationError

from marketpilot.core.enums import Interval
from marketpilot.models.backtest import BacktestResult, BacktestMetrics, BacktestTrade
from marketpilot.models.strategy import SignalDirection
from marketpilot.reports.store import ReportStore


@pytest.fixture
def temp_store(tmp_path: Path) -> ReportStore:
    return ReportStore(data_dir=tmp_path)


def test_save_and_load_backtest(temp_store: ReportStore) -> None:
    trade = BacktestTrade(
        direction=SignalDirection.LONG,
        signal_time=datetime(2025, 1, 1, tzinfo=UTC),
        entry_time=datetime(2025, 1, 1, 1, tzinfo=UTC),
        exit_time=datetime(2025, 1, 2, tzinfo=UTC),
        entry_price=Decimal("1000.123456789"),
        exit_price=Decimal("2000.987654321"),
        quantity=Decimal("0.05"),
        entry_fee=Decimal("1.5"),
        exit_fee=Decimal("3.0"),
        realized_pnl=Decimal("45.5"),
        exit_reason="take_profit"
    )
    metrics = BacktestMetrics(
        starting_equity=Decimal("1000"),
        ending_equity=Decimal("1045.5"),
        total_return_fraction=Decimal("0.0455"),
        max_drawdown_fraction=Decimal("0.01"),
        trade_count=1,
        win_rate=Decimal("1.0"),
        profit_factor=Decimal("999.0")
    )
    result = BacktestResult(
        symbol="BTCUSDT",
        interval=Interval.H1,
        start_time=datetime(2024, 12, 1, tzinfo=UTC),
        end_time=datetime(2025, 1, 2, tzinfo=UTC),
        trades=(trade,),
        equity_curve=(Decimal("1000"), Decimal("1045.5")),
        metrics=metrics
    )

    temp_store.save_backtest(result)
    
    # Verify file content manually to ensure Decimals are strings
    target_path = temp_store.data_dir / "backtest.latest.json"
    assert target_path.exists()
    
    with open(target_path, "r", encoding="utf-8") as f:
        raw_json = json.load(f)
    
    # Check payload is present
    payload = raw_json["payload"]
    assert payload["symbol"] == "BTCUSDT"
    
    # In Pydantic v2 model_dump_json(), Decimals are serialized as strings 
    # to avoid float precision loss (by default when mode='json'). 
    # Let's verify string serialization
    assert isinstance(payload["trades"][0]["entry_price"], str)
    assert payload["trades"][0]["entry_price"] == "1000.123456789"
    
    # Test load
    loaded = temp_store.load_backtest()
    assert loaded is not None
    assert loaded.symbol == "BTCUSDT"
    assert loaded.trades[0].entry_price == Decimal("1000.123456789")
    assert loaded.trades[0].signal_time == datetime(2025, 1, 1, tzinfo=UTC)


def test_load_missing_report(temp_store: ReportStore) -> None:
    assert temp_store.load_backtest() is None
    assert temp_store.load_optimization() is None


def test_load_corrupt_report(temp_store: ReportStore) -> None:
    target_path = temp_store.data_dir / "backtest.latest.json"
    
    # Bad JSON syntax
    with open(target_path, "w", encoding="utf-8") as f:
        f.write("{ bad json ")
    
    assert temp_store.load_backtest() is None

    # Valid JSON but fails Pydantic validation (missing fields)
    with open(target_path, "w", encoding="utf-8") as f:
        f.write('{"schema_version": 1, "payload": {"symbol": "BTC"}}')
        
    assert temp_store.load_backtest() is None
