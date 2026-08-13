"""Tests for Decision Audit Engine."""

import time
import json
from decimal import Decimal
from pathlib import Path

from marketpilot.engines.decision_audit_engine import DecisionAuditEngine
from marketpilot.models.audit import AuditRecord
from marketpilot.models.scanner import InstrumentSnapshot
from marketpilot.models.regime import MarketRegime
from marketpilot.models.strategy import StrategyResult, SignalDirection, StrategyEvaluation
from marketpilot.models.risk import RiskDecision
from marketpilot.core.enums import AssetType

def test_decision_audit_engine(tmp_path: Path) -> None:
    engine = DecisionAuditEngine(log_dir=str(tmp_path))
    
    snap = InstrumentSnapshot(
        symbol="BTCUSDT",
        asset_type=AssetType.LINEAR,
        last_price=Decimal("100"),
        liquidity_turnover_24h=Decimal("1000000"),
        volume_24h=Decimal("20"),
        spread_bps=Decimal("10"),
        atr_percent=Decimal("0.02"),
        momentum_24h=Decimal("0.01"),
        trend_strength=Decimal("0.2"),
        trend_age_candles=10,
        market_quality=Decimal("90"),
        score_breakdown={"Liquidity": "+10"}
    )
    
    strat_result_1 = StrategyResult(
        strategy_name="EMA Pullback",
        signal=SignalDirection.LONG,
        confidence=Decimal("80"),
        reason_code="BULL_EMA_TOUCH",
        metrics={"RSI": "45"},
        candidate_trade=StrategyEvaluation(
            expected_win_rate=Decimal("55"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("130"),
            expected_rr=Decimal("3.0")
        )
    )
    
    strat_result_2 = StrategyResult(
        strategy_name="Momentum",
        signal=SignalDirection.HOLD,
        confidence=Decimal("0"),
        reason_code="WEAK_MOMENTUM",
        metrics={"RSI": "45"}
    )
    
    risk = RiskDecision(
        approved=True,
        reason="Approved",
        position_size=Decimal("1"),
        risk_amount=Decimal("10"),
        sl=Decimal("90"),
        tp=Decimal("130"),
        rr=Decimal("3.0")
    )
    
    record = AuditRecord(
        decision_id="dec-123",
        timestamp=time.time(),
        config_hash="abc",
        market_snapshot=snap,
        feature_vector={"EMA20": "99", "EMA50": "95"},
        regime_snapshot=MarketRegime.TRENDING_BULL,
        strategy_results=[strat_result_1, strat_result_2],
        risk_result=risk,
        trade_plan=None,
        validation_passed=True,
        validation_reason="OK",
        quantized_plan=None,
        execution_submitted=True,
        total_processing_time_ms=10.5
    )
    
    engine.log(record)
    
    # Check JSONL
    assert engine.jsonl_path.exists()
    lines = engine.jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["decision_id"] == "dec-123"
    
    # Check Markdown
    md_file = engine.md_dir / "dec-123.md"
    assert md_file.exists()
    content = md_file.read_text(encoding="utf-8")
    assert "# Audit Report: dec-123" in content
    assert "EMA Pullback" in content
    assert "BULL_EMA_TOUCH" in content
