"""Tests for Scanner Engine."""

from decimal import Decimal
from marketpilot.config.settings import ScannerSettings
from marketpilot.engines.scanner_engine import ScannerEngine
from marketpilot.models.scanner import InstrumentSnapshot, TrendAge
from marketpilot.core.enums import AssetType

def test_scanner_engine_ranking() -> None:
    settings = ScannerSettings(
        weight_liquidity=0.2,
        weight_spread=0.1,
        weight_atr=0.15,
        weight_momentum=0.15,
        weight_trend_strength=0.1,
        weight_funding=0.1,
        weight_open_interest=0.1,
        weight_trend_age=0.1,
        minimum_liquidity=1000.0,
        minimum_volume=1.0,
        minimum_atr_percent=0.01,
        maximum_spread_bps=50.0,
        max_results=2
    )
    engine = ScannerEngine(settings)
    
    # Passes thresholds but worst metrics
    snap1 = InstrumentSnapshot(
        symbol="BTCUSDT",
        asset_type=AssetType.LINEAR,
        last_price=Decimal("50000"),
        liquidity_turnover_24h=Decimal("1000000"), 
        volume_24h=Decimal("20"),
        spread_bps=Decimal("10"), 
        atr_percent=Decimal("0.02"), 
        momentum_24h=Decimal("0.01"), 
        trend_strength=Decimal("0.2"), 
        trend_age_candles=80, # LATE
        funding_rate=Decimal("0.0001"),
        open_interest=Decimal("50000")
    )
    
    # Fails thresholds (spread > 50)
    snap2 = InstrumentSnapshot(
        symbol="ETHUSDT",
        asset_type=AssetType.LINEAR,
        last_price=Decimal("3000"),
        liquidity_turnover_24h=Decimal("5000000"), 
        volume_24h=Decimal("1500"),
        spread_bps=Decimal("100"), # FAILS THRESHOLD
        atr_percent=Decimal("0.05"), 
        momentum_24h=Decimal("-0.05"), 
        trend_strength=Decimal("0.5"), 
        trend_age_candles=15, # EARLY
        funding_rate=Decimal("-0.0005"), 
        open_interest=Decimal("100000")
    )
    
    # Passes, best metrics
    snap3 = InstrumentSnapshot(
        symbol="SOLUSDT",
        asset_type=AssetType.LINEAR,
        last_price=Decimal("100"),
        liquidity_turnover_24h=Decimal("10000000"), 
        volume_24h=Decimal("100000"),
        spread_bps=Decimal("1"), 
        atr_percent=Decimal("0.10"), 
        momentum_24h=Decimal("0.15"), 
        trend_strength=Decimal("0.9"), 
        trend_age_candles=3, # NEW
        funding_rate=Decimal("0.0010"), 
        open_interest=Decimal("200000") 
    )
    
    result = engine.evaluate([snap1, snap2, snap3])
    
    # 2 passed thresholds out of 3 -> Market health = 66.67
    assert result.market_health == Decimal("66.67")
    
    # Max results is 2, and we have 2 valid candidates
    assert len(result.top_candidates) == 2 
    
    # SOLUSDT has the best metrics across the board
    assert result.top_candidates[0].symbol == "SOLUSDT"
    # SOLUSDT should have score 100 since it is max on all positive factors
    assert result.top_candidates[0].market_quality == Decimal("100.00")
    assert result.top_candidates[0].trend_age == TrendAge.NEW
    
    # BTCUSDT is the worst valid
    assert result.top_candidates[1].symbol == "BTCUSDT"
    assert result.top_candidates[1].market_quality == Decimal("0.00")
    assert result.top_candidates[1].trend_age == TrendAge.LATE
    
    # Check breakdown exists with penalty format
    assert "Liquidity" in result.top_candidates[0].score_breakdown
    
    assert result.metadata.processing_time_ms > 0

def test_scanner_engine_empty() -> None:
    settings = ScannerSettings()
    engine = ScannerEngine(settings)
    
    result = engine.evaluate([])
    assert len(result.top_candidates) == 0
    assert result.market_health == Decimal("0")
