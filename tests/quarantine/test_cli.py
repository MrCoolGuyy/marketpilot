"""
MarketPilot CLI tests.
"""

import sys
from io import StringIO
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, UTC
from decimal import Decimal
import pytest
from loguru import logger

from marketpilot.cli import _cmd_scan
from marketpilot.config import get_settings
from marketpilot.models.scanner import ScanResult
from marketpilot.models.indicators import IndicatorPoint, IndicatorSeries
from marketpilot.models.market import Kline
from marketpilot.core.enums import AssetType, Interval


@pytest.fixture
def mock_scanner() -> AsyncMock:
    scanner = AsyncMock()
    return scanner

@pytest.mark.asyncio
async def test_cmd_scan_formats_positive_and_negative_percentages(mock_scanner: AsyncMock) -> None:
    # Setup mock results
    mock_scanner.scan.return_value = [
        ScanResult(
            symbol="BTCUSDT",
            asset_type=AssetType.LINEAR,
            last_price="50000",
            price_change_percent_24h="0.0068", # 0.68%
            turnover_24h="1000000",
        ),
        ScanResult(
            symbol="ETHUSDT",
            asset_type=AssetType.LINEAR,
            last_price="3000",
            price_change_percent_24h="-0.0150", # -1.50%
            turnover_24h="2000000",
        ),
    ]

    settings = get_settings()

    from unittest.mock import MagicMock
    mock_client_class = MagicMock()
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()

    with patch("marketpilot.exchange.bybit_client.BybitClient", new=mock_client_class):
        with patch("marketpilot.scanner.service.ScannerService", return_value=mock_scanner):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                await _cmd_scan(settings, [])
                
    output = mock_stdout.getvalue()
    
    # Assert positive percentage formatting
    assert "0.68%" in output
    assert "BTCUSDT" in output
    
    # Assert negative percentage formatting
    assert "-1.50%" in output

@pytest.mark.asyncio
async def test_cmd_scan_failure() -> None:
    settings = get_settings()
    
    mock_scanner = AsyncMock()
    mock_scanner.scan.side_effect = Exception("Upstream connection error")
    
    mock_client_class = MagicMock()
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    
    with patch("marketpilot.exchange.bybit_client.BybitClient", new=mock_client_class):
        with patch("marketpilot.scanner.service.ScannerService", return_value=mock_scanner):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with pytest.raises(SystemExit) as exc_info:
                    await _cmd_scan(settings, [])
                assert exc_info.value.code == 1
                
    assert "Scan failed: Upstream connection error" in mock_stdout.getvalue()

@pytest.mark.asyncio
async def test_cmd_indicators_success() -> None:
    settings = get_settings()

    # Create mock series
    mock_point = IndicatorPoint(
        open_time=datetime.now(tz=UTC),
        ema_fast=Decimal("100"),
        ema_slow=Decimal("90"),
        rsi=Decimal("60"),
        macd_line=Decimal("10"),
        macd_signal=Decimal("9"),
        macd_histogram=Decimal("1"),
        atr=Decimal("5"),
        volume_sma=Decimal("1000")
    )
    mock_series = IndicatorSeries(
        symbol="BTCUSDT",
        interval=Interval.H1,
        points=tuple([mock_point])
    )
    
    mock_service = MagicMock()
    mock_service.calculate.return_value = mock_series
    
    mock_client_class = MagicMock()
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    
    # Make open_time recent so it gets dropped as active
    mock_client.get_klines = AsyncMock(return_value=[
        Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.now(tz=UTC), open="1", high="1", low="1", close="1", volume="1", turnover="1"),
        Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.now(tz=UTC), open="1", high="1", low="1", close="1", volume="1", turnover="1")
    ])

    with patch("marketpilot.exchange.bybit_client.BybitClient", new=mock_client_class):
        with patch("marketpilot.indicators.service.IndicatorService", return_value=mock_service):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                from marketpilot.cli import _cmd_indicators
                await _cmd_indicators(settings, ["BTCUSDT", "--interval", "60", "--limit", "100"])

    output = mock_stdout.getvalue()
    assert "Indicators for BTCUSDT (60m" in output
    assert "EMA Fast (20)   : 100.0000" in output
    assert "RSI (14)          : 60.0000" in output

@pytest.mark.asyncio
async def test_cmd_indicators_invalid_args() -> None:
    settings = get_settings()
    
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        with pytest.raises(SystemExit):
            from marketpilot.cli import _cmd_indicators
            await _cmd_indicators(settings, ["BTCUSDT", "--limit", "-1"])
            
    assert "Error: --limit must be between 1 and 999." in mock_stdout.getvalue()

@pytest.mark.asyncio
async def test_cmd_indicators_active_vs_closed() -> None:
    settings = get_settings()
    
    mock_point = IndicatorPoint(
        open_time=datetime.now(tz=UTC),
        ema_fast=Decimal("100"), ema_slow=Decimal("90"), rsi=Decimal("60"),
        macd_line=Decimal("10"), macd_signal=Decimal("9"), macd_histogram=Decimal("1"),
        atr=Decimal("5"), volume_sma=Decimal("1000")
    )
    mock_series = IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=tuple([mock_point]))
    
    mock_service = MagicMock()
    mock_service.calculate.return_value = mock_series
    
    mock_client_class = MagicMock()
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    
    from datetime import timedelta
    old_time = datetime.now(tz=UTC) - timedelta(hours=2) # Already closed
    
    # 1. Closed kline - should not drop
    mock_client.get_klines = AsyncMock(return_value=[
        Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=old_time, open="1", high="1", low="1", close="1", volume="1", turnover="1")
    ])
    
    with patch("marketpilot.exchange.bybit_client.BybitClient", new=mock_client_class):
        with patch("marketpilot.indicators.service.IndicatorService", return_value=mock_service):
            with patch("sys.stdout", new_callable=StringIO):
                from marketpilot.cli import _cmd_indicators
                await _cmd_indicators(settings, ["BTCUSDT", "--interval", "60"])
                
    # Service calculate called with 1 kline because it's closed
    assert len(mock_service.calculate.call_args[0][0]) == 1
    
    # 2. Active kline - should drop (and exit because 0 klines left)
    active_time = datetime.now(tz=UTC)
    mock_client.get_klines = AsyncMock(return_value=[
        Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=active_time, open="1", high="1", low="1", close="1", volume="1", turnover="1")
    ])
    
    with patch("marketpilot.exchange.bybit_client.BybitClient", new=mock_client_class):
        with patch("marketpilot.indicators.service.IndicatorService", return_value=mock_service):
            with patch("sys.stdout", new_callable=StringIO):
                with pytest.raises(SystemExit) as exc_info:
                    await _cmd_indicators(settings, ["BTCUSDT", "--interval", "60"])
                assert exc_info.value.code == 0

@pytest.mark.asyncio
async def test_cmd_strategy_success() -> None:
    from marketpilot.models.strategy import StrategySignal, SignalDirection
    from marketpilot.cli import _cmd_strategy

    settings = get_settings()
    
    mock_signal = StrategySignal(
        symbol="BTCUSDT",
        interval=Interval.H1,
        open_time=datetime.now(tz=UTC),
        direction=SignalDirection.LONG,
        score=Decimal("100"),
        reasons=("long_conditions_met",)
    )
    
    mock_indicator_service = MagicMock()
    mock_strategy_service = MagicMock()
    mock_strategy_service.evaluate.return_value = mock_signal
    
    mock_client_class = MagicMock()
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    
    mock_client.get_klines = AsyncMock(return_value=[
        Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.now(tz=UTC), open="1", high="1", low="1", close="1", volume="1", turnover="1")
    ])

    with patch("marketpilot.exchange.bybit_client.BybitClient", new=mock_client_class):
        with patch("marketpilot.indicators.service.IndicatorService", return_value=mock_indicator_service):
            with patch("marketpilot.strategy.service.StrategyService", return_value=mock_strategy_service):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    # open time is active, so will exit 0
                    with pytest.raises(SystemExit) as exc_info:
                        await _cmd_strategy(settings, ["BTCUSDT"])
                    assert exc_info.value.code == 0

    # Test with closed candle
    from datetime import timedelta
    old_time = datetime.now(tz=UTC) - timedelta(hours=2)
    mock_client.get_klines = AsyncMock(return_value=[
        Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=old_time, open="1", high="1", low="1", close="1", volume="1", turnover="1")
    ])
    
    with patch("marketpilot.exchange.bybit_client.BybitClient", new=mock_client_class):
        with patch("marketpilot.indicators.service.IndicatorService", return_value=mock_indicator_service):
            with patch("marketpilot.strategy.service.StrategyService", return_value=mock_strategy_service):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    await _cmd_strategy(settings, ["BTCUSDT"])
                    
    output = mock_stdout.getvalue()
    assert "[ANALYSIS ONLY - NO ORDER EXECUTED]" in output
    assert "Strategy Analysis for BTCUSDT" in output
    assert "Direction   : LONG" in output
    assert "- long_conditions_met" in output


@pytest.mark.asyncio
async def test_cmd_risk_success() -> None:
    from marketpilot.models.risk import RiskAssessment
    from marketpilot.models.strategy import SignalDirection
    from marketpilot.cli import _cmd_risk

    settings = get_settings()
    
    mock_assessment = RiskAssessment(
        symbol="BTCUSDT",
        interval=Interval.H1,
        open_time=datetime.now(tz=UTC),
        direction=SignalDirection.LONG,
        eligible_for_paper_trading=True,
        entry_price=Decimal("1000"),
        stop_loss=Decimal("970"),
        take_profit=Decimal("1060"),
        stop_distance=Decimal("30"),
        reward_risk_ratio=Decimal("2.0"),
        risk_budget=Decimal("100"),
        theoretical_quantity=Decimal("3.3333"),
        theoretical_notional=Decimal("3333.3"),
        reasons=("risk_parameters_valid",)
    )
    
    mock_risk_service = MagicMock()
    mock_risk_service.assess.return_value = mock_assessment
    
    mock_client_class = MagicMock()
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    
    from datetime import timedelta
    old_time = datetime.now(tz=UTC) - timedelta(hours=2)
    mock_client.get_klines = AsyncMock(return_value=[
        Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=old_time, open="1000", high="1000", low="1000", close="1000", volume="1000", turnover="1000")
    ])

    with patch("marketpilot.exchange.bybit_client.BybitClient", new=mock_client_class):
        with patch("marketpilot.indicators.service.IndicatorService", return_value=MagicMock()):
            with patch("marketpilot.strategy.service.StrategyService", return_value=MagicMock()):
                with patch("marketpilot.risk.service.RiskManagerService", return_value=mock_risk_service):
                    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                        await _cmd_risk(settings, ["BTCUSDT", "--equity", "10000"])
                        
    output = mock_stdout.getvalue()
    assert "[ANALYSIS ONLY - PAPER TRADING ELIGIBILITY]" in output
    assert "Risk Assessment for BTCUSDT" in output
    assert "Entry Price : 1000.0000" in output
    assert "Theo. Qty   : 3.3333 (Base)" in output


@pytest.mark.asyncio
async def test_cmd_risk_invalid_equity() -> None:
    from marketpilot.cli import _cmd_risk
    settings = get_settings()

    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        with pytest.raises(SystemExit):
            await _cmd_risk(settings, ["BTCUSDT", "--equity", "-500"])
    
    assert "Error: --equity must be a positive finite number." in mock_stdout.getvalue()
    
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        with pytest.raises(SystemExit):
            await _cmd_risk(settings, ["BTCUSDT", "--equity", "NaN"])
            
    assert "Error: --equity must be a positive finite number." in mock_stdout.getvalue()


@pytest.mark.asyncio
async def test_cmd_paper_reset_missing_confirm() -> None:
    from marketpilot.cli import _cmd_paper
    settings = get_settings()
    settings.storage.url = "sqlite+aiosqlite:///:memory:"

    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        with pytest.raises(SystemExit):
            await _cmd_paper(settings, ["reset"])
            
    assert "Error: Paper reset requires --confirm." in mock_stdout.getvalue()


@pytest.mark.asyncio
async def test_cmd_paper_open_missing_confirm() -> None:
    from marketpilot.cli import _cmd_paper
    settings = get_settings()
    settings.storage.url = "sqlite+aiosqlite:///:memory:"

    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        with pytest.raises(SystemExit):
            await _cmd_paper(settings, ["open", "BTCUSDT"])
            
    assert "Error: Paper open requires --confirm." in mock_stdout.getvalue()


@pytest.mark.asyncio
async def test_cmd_paper_close_missing_confirm() -> None:
    from marketpilot.cli import _cmd_paper
    settings = get_settings()
    settings.storage.url = "sqlite+aiosqlite:///:memory:"

    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        with pytest.raises(SystemExit):
            await _cmd_paper(settings, ["close", "BTCUSDT"])
            
    assert "Error: Paper close requires --confirm." in mock_stdout.getvalue()




