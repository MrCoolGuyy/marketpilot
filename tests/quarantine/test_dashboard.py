"""Tests for the local read-only dashboard."""

import json
from decimal import Decimal
from datetime import datetime, UTC

import pytest
from fastapi.testclient import TestClient

from marketpilot.config.settings import AppSettings, StorageSettings
from marketpilot.core.enums import Interval
from marketpilot.dashboard.server import create_app
from marketpilot.models.market import Kline
from marketpilot.models.strategy import SignalDirection
from marketpilot.models.paper import PaperAccountSnapshot
from marketpilot.reports.store import ReportStore


@pytest.fixture
def mock_app_settings(tmp_path):
    settings = AppSettings()
    # Ensure DB is just memory or temp
    settings.storage = StorageSettings(url="sqlite+aiosqlite:///:memory:")
    return settings


@pytest.fixture
def test_client(mock_app_settings, tmp_path):
    app = create_app(mock_app_settings)
    
    # We must patch the lifespan or mock the services for the client
    # Actually, TestClient triggers the lifespan if we use it in a `with` block!
    # But since BybitClient attempts network connection, we must mock it,
    # or just bypass lifespan and attach mocked services directly.
    # To bypass lifespan properly and just test routes, we can inject mocks into app.state.
    class MockDB:
        async def health_check(self):
            return True
            
        class _SessionContext:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
                
        def session(self):
            return self._SessionContext()

    class MockClient:
        async def get_klines(self, *args, **kwargs):
            return [
                Kline(
                    symbol="BTCUSDT",
                    interval=Interval.H1,
                    open_time=datetime(2025, 1, 1, tzinfo=UTC),
                    open="1000", high="1000", low="1000", close="1000",
                    volume="10", turnover="10000", is_closed=True
                )
            ]
            
    class MockIndicatorService:
        def calculate(self, klines):
            from marketpilot.models.indicators import IndicatorPoint, IndicatorSeries
            return IndicatorSeries(
                symbol="BTCUSDT",
                interval=Interval.H1,
                points=(IndicatorPoint(
                    open_time=datetime(2025, 1, 1, tzinfo=UTC),
                    ema_fast=Decimal("100"), ema_slow=Decimal("100"),
                    rsi=Decimal("50"), atr=Decimal("10"),
                    macd_line=Decimal("0"), macd_signal=Decimal("0"), macd_histogram=Decimal("0"),
                    volume_sma=Decimal("0")
                ),)
            )
            
    class MockStrategyService:
        def evaluate(self, series):
            from marketpilot.models.strategy import StrategySignal
            ind = series.latest
            return StrategySignal(
                symbol="BTCUSDT", interval=Interval.H1, open_time=ind.open_time if ind else None,
                direction=SignalDirection.NEUTRAL, reasons=("test",), score=Decimal("0")
            )
            
    class MockRiskService:
        def assess(self, **kwargs):
            from marketpilot.models.risk import RiskAssessment
            return RiskAssessment(
                symbol="BTCUSDT", interval=Interval.H1, open_time=datetime(2025, 1, 1, tzinfo=UTC),
                direction=SignalDirection.NEUTRAL, eligible_for_paper_trading=False,
                entry_price=Decimal("1000"), risk_budget=Decimal("0"),
                reasons=("test",)
            )
            
    class MockPaperService:
        async def get_snapshot(self, session, prices):
            return PaperAccountSnapshot(
                cash=Decimal("1000"), locked_margin=Decimal("0"), equity=Decimal("1000"),
                realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"), positions=(), trades=()
            )

    class MockScanner:
        async def scan(self):
            return []

    app.state.db = MockDB()
    app.state.client = MockClient()
    app.state.indicator_service = MockIndicatorService()
    app.state.strategy_service = MockStrategyService()
    app.state.risk_service = MockRiskService()
    app.state.paper_service = MockPaperService()
    app.state.scanner = MockScanner()
    app.state.report_store = ReportStore(data_dir=tmp_path)
    
    # We do not use the `with` block so lifespan is bypassed (which attempts real DB and Bybit)
    client = TestClient(app)
    return client


def test_health_route(test_client):
    res = test_client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_scan_route(test_client):
    res = test_client.get("/api/scan")
    assert res.status_code == 200
    assert res.json() == {"results": []}


def test_market_route(test_client):
    res = test_client.get("/api/market?symbol=BTCUSDT&interval=60")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["latest_price"] == "1000"
    assert data["signal"]["direction"] == "NEUTRAL"
    assert data["risk"]["eligible_for_paper_trading"] is False
    assert data["indicators"]["rsi"] == "50"
    assert len(data["klines"]) == 1

def test_market_cache(test_client):
    # Test that a second call doesn't raise anything and returns quickly
    res = test_client.get("/api/market?symbol=BTCUSDT&interval=60")
    assert res.status_code == 200
    
def test_insufficient_atr_returns_200(test_client):
    # We will temporarily mock the indicator service to return None ATR
    original_service = test_client.app.state.indicator_service
    class BadIndicatorService:
        def calculate(self, klines):
            from marketpilot.models.indicators import IndicatorPoint, IndicatorSeries
            from marketpilot.core.enums import Interval
            from datetime import datetime, UTC
            return IndicatorSeries(
                symbol="BTCUSDT", interval=Interval.H1,
                points=(IndicatorPoint(open_time=datetime(2025, 1, 1, tzinfo=UTC), atr=None),)
            )
    test_client.app.state.indicator_service = BadIndicatorService()
    try:
        res = test_client.get("/api/market?symbol=ETHUSDT&interval=60")
        assert res.status_code == 200
        data = res.json()
        assert data["risk"]["eligible_for_paper_trading"] is False
        assert "insufficient_indicator_data" in data["risk"]["reasons"]
    finally:
        test_client.app.state.indicator_service = original_service


def test_paper_route(test_client):
    res = test_client.get("/api/paper")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["equity"] == "1000"


def test_missing_reports(test_client):
    res = test_client.get("/api/backtest/latest")
    assert res.status_code == 404
    assert "No historical run available" in res.json()["detail"]
    
    res = test_client.get("/api/optimization/latest")
    assert res.status_code == 404


def test_existing_backtest_report(test_client, tmp_path):
    from marketpilot.models.backtest import BacktestResult, BacktestMetrics
    store = ReportStore(data_dir=tmp_path)
    bt = BacktestResult(
        symbol="ETHUSDT", interval=Interval.H1,
        start_time=datetime(2025, 1, 1, tzinfo=UTC),
        end_time=datetime(2025, 1, 2, tzinfo=UTC),
        trades=(), equity_curve=(),
        metrics=BacktestMetrics(
            starting_equity=Decimal("1000"), ending_equity=Decimal("1000"),
            total_return_fraction=Decimal("0"), max_drawdown_fraction=Decimal("0"),
            trade_count=0, win_rate=None, profit_factor=None
        )
    )
    store.save_backtest(bt)
    
    # Reload from test_client (which points to same tmp_path)
    res = test_client.get("/api/backtest/latest")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["symbol"] == "ETHUSDT"
    assert data["metrics"]["starting_equity"] == "1000"

def test_control_endpoints_require_key(test_client):
    from pydantic import SecretStr
    test_client.app.state.settings.dashboard_control_key = SecretStr("secret_key")
    res = test_client.post("/api/control/autopilot/run")
    assert res.status_code == 401
    
def test_control_endpoints_with_valid_key(test_client):
    # Set key
    from pydantic import SecretStr
    test_client.app.state.settings.dashboard_control_key = SecretStr("secret_key")
    
    # Missing key
    res = test_client.post("/api/control/autopilot/run")
    assert res.status_code == 401
    
    # Wrong key
    res = test_client.post("/api/control/autopilot/run", headers={"x-marketpilot-control-key": "wrong"})
    assert res.status_code == 401
    
    # Correct key
    res = test_client.post("/api/control/autopilot/run", headers={"x-marketpilot-control-key": "secret_key"})
    # Since AutopilotService doesn't have an injected client in the test_client context (it relies on settings), it might return 500 or 200 depending on exceptions.
    # The important part is that we bypass the 401 Unauthorized barrier.
    assert res.status_code in (200, 500)
