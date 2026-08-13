"""
Tests for MarketPilot Paper Trading module.
"""

import uuid
from datetime import datetime, UTC
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from marketpilot.config.settings import PaperSettings
from marketpilot.core.enums import Interval
from marketpilot.models.risk import RiskAssessment
from marketpilot.models.strategy import SignalDirection
from marketpilot.paper.service import PaperTradingService
from marketpilot.storage.repository import PaperAccountRepository
from marketpilot.storage.tables import Base


@pytest.fixture
async def paper_db_session() -> AsyncSession:
    """Fixture for an isolated temporary database for paper trading."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    yield session
    
    await session.close()
    await engine.dispose()


@pytest.fixture
def paper_settings() -> PaperSettings:
    return PaperSettings(
        initial_equity=Decimal("10000"),
        leverage=5,
        taker_fee_fraction=Decimal("0.001"),  # 0.1%
        slippage_bps=Decimal("10") # 0.1%
    )


@pytest.fixture
def mock_risk_long() -> RiskAssessment:
    return RiskAssessment(
        symbol="BTCUSDT",
        interval=Interval.H1,
        open_time=datetime.now(tz=UTC),
        direction=SignalDirection.LONG,
        eligible_for_paper_trading=True,
        entry_price=Decimal("1000"),
        stop_loss=Decimal("950"),
        take_profit=Decimal("1100"),
        stop_distance=Decimal("50"),
        reward_risk_ratio=Decimal("2.0"),
        risk_budget=Decimal("100"),
        theoretical_quantity=Decimal("2.0"),
        theoretical_notional=Decimal("2000"),
        reasons=("valid",)
    )


@pytest.fixture
def mock_risk_short() -> RiskAssessment:
    return RiskAssessment(
        symbol="BTCUSDT",
        interval=Interval.H1,
        open_time=datetime.now(tz=UTC),
        direction=SignalDirection.SHORT,
        eligible_for_paper_trading=True,
        entry_price=Decimal("1000"),
        stop_loss=Decimal("1050"),
        take_profit=Decimal("900"),
        stop_distance=Decimal("50"),
        reward_risk_ratio=Decimal("2.0"),
        risk_budget=Decimal("100"),
        theoretical_quantity=Decimal("2.0"),
        theoretical_notional=Decimal("2000"),
        reasons=("valid",)
    )


@pytest.mark.asyncio
async def test_paper_trading_long_lifecycle(paper_db_session: AsyncSession, paper_settings: PaperSettings, mock_risk_long: RiskAssessment) -> None:
    service = PaperTradingService(paper_settings)
    
    # 1. Reset
    await service.reset(paper_db_session)
    await paper_db_session.commit()
    
    # 2. Open Long
    market_price = Decimal("1000")
    # slippage = 10 bps = 0.001 -> fill = 1000 * 1.001 = 1001
    # notional = 2.0 * 1001 = 2002
    # margin = 2002 / 5 = 400.4
    # fee = 2002 * 0.001 = 2.002
    # req cash = 400.4 + 2.002 = 402.402
    
    trade = await service.open_position(paper_db_session, mock_risk_long, market_price)
    await paper_db_session.commit()
    
    assert trade.direction == SignalDirection.LONG
    assert trade.entry_price == Decimal("1001")
    assert trade.entry_fee == Decimal("2002") * Decimal("0.001")
    
    # Check Snapshot
    snap = await service.get_snapshot(paper_db_session, {"BTCUSDT": Decimal("1005")})
    assert len(snap.positions) == 1
    assert snap.positions[0].quantity == Decimal("2.0")
    assert snap.cash == Decimal("10000") - Decimal("402.402")
    assert snap.locked_margin == Decimal("400.4")
    
    # unrealized PnL: LONG = (1005 - 1001) * 2.0 = 8
    assert snap.unrealized_pnl == Decimal("8")
    assert snap.equity == snap.cash + snap.locked_margin + snap.unrealized_pnl
    
    # 3. Close Long
    exit_market = Decimal("1100")
    # exit slippage = 1100 * 0.999 = 1098.9
    # exit notional = 2.0 * 1098.9 = 2197.8
    # exit fee = 2197.8 * 0.001 = 2.1978
    # gross pnl = (1098.9 - 1001) * 2.0 = 195.8
    # net pnl = 195.8 - 2.002 - 2.1978 = 191.6002
    
    closed_trade = await service.close_position(paper_db_session, "BTCUSDT", exit_market)
    await paper_db_session.commit()
    
    assert closed_trade.status == "CLOSED"
    assert closed_trade.exit_price == Decimal("1098.9")
    assert closed_trade.realized_pnl == Decimal("191.6002")
    
    snap2 = await service.get_snapshot(paper_db_session, {})
    assert len(snap2.positions) == 0
    assert snap2.locked_margin == Decimal("0")
    assert snap2.cash == Decimal("10000") + Decimal("191.6002")
    assert snap2.realized_pnl == Decimal("191.6002")


@pytest.mark.asyncio
async def test_paper_trading_short_lifecycle(paper_db_session: AsyncSession, paper_settings: PaperSettings, mock_risk_short: RiskAssessment) -> None:
    service = PaperTradingService(paper_settings)
    await service.reset(paper_db_session)
    await paper_db_session.commit()
    
    # Short open
    market_price = Decimal("1000")
    # slippage = 10 bps = 0.001 -> fill = 1000 * 0.999 = 999
    # notional = 2.0 * 999 = 1998
    # margin = 1998 / 5 = 399.6
    # fee = 1998 * 0.001 = 1.998
    trade = await service.open_position(paper_db_session, mock_risk_short, market_price)
    await paper_db_session.commit()
    
    assert trade.direction == SignalDirection.SHORT
    assert trade.entry_price == Decimal("999")
    
    # Mark to market (price dropped to 990) -> (entry 999 - mark 990) * 2 = 18
    snap = await service.get_snapshot(paper_db_session, {"BTCUSDT": Decimal("990")})
    assert snap.unrealized_pnl == Decimal("18")
    
    # Close short
    exit_market = Decimal("900")
    # exit slippage = 900 * 1.001 = 900.9
    # exit notional = 2.0 * 900.9 = 1801.8
    # exit fee = 1801.8 * 0.001 = 1.8018
    # gross pnl = (999 - 900.9) * 2.0 = 196.2
    # net pnl = 196.2 - 1.998 - 1.8018 = 192.4002
    
    closed_trade = await service.close_position(paper_db_session, "BTCUSDT", exit_market)
    await paper_db_session.commit()
    
    assert closed_trade.realized_pnl == Decimal("192.4002")


@pytest.mark.asyncio
async def test_paper_trading_transaction_rollback(paper_db_session: AsyncSession, paper_settings: PaperSettings, mock_risk_long: RiskAssessment) -> None:
    service = PaperTradingService(paper_settings)
    await service.reset(paper_db_session)
    await paper_db_session.commit()
    
    # Test that if a commit fails or we rollback, the state is unharmed
    async with paper_db_session.begin_nested():
        await service.open_position(paper_db_session, mock_risk_long, Decimal("1000"))
        await paper_db_session.rollback()
        
    snap = await service.get_snapshot(paper_db_session, {})
    assert len(snap.positions) == 0
    assert snap.cash == Decimal("10000")


@pytest.mark.asyncio
async def test_paper_trading_insufficient_cash(paper_db_session: AsyncSession, paper_settings: PaperSettings, mock_risk_long: RiskAssessment) -> None:
    service = PaperTradingService(paper_settings)
    
    # Reset with $1 of equity
    repo = PaperAccountRepository(paper_db_session)
    await repo.reset("1.0")
    await paper_db_session.commit()
    
    with pytest.raises(ValueError, match="Insufficient cash"):
        await service.open_position(paper_db_session, mock_risk_long, Decimal("1000"))


@pytest.mark.asyncio
async def test_paper_trading_duplicate_position(paper_db_session: AsyncSession, paper_settings: PaperSettings, mock_risk_long: RiskAssessment) -> None:
    service = PaperTradingService(paper_settings)
    await service.reset(paper_db_session)
    await paper_db_session.commit()
    
    await service.open_position(paper_db_session, mock_risk_long, Decimal("1000"))
    await paper_db_session.commit()
    
    with pytest.raises(ValueError, match="already open"):
        await service.open_position(paper_db_session, mock_risk_long, Decimal("1000"))


@pytest.mark.asyncio
async def test_paper_trading_reject_risk(paper_db_session: AsyncSession, paper_settings: PaperSettings) -> None:
    service = PaperTradingService(paper_settings)
    await service.reset(paper_db_session)
    await paper_db_session.commit()
    
    risk = RiskAssessment(
        symbol="BTCUSDT",
        interval=Interval.H1,
        open_time=datetime.now(tz=UTC),
        direction=SignalDirection.NEUTRAL,
        eligible_for_paper_trading=False,
        reasons=("bad",)
    )
    with pytest.raises(ValueError, match="not eligible"):
        await service.open_position(paper_db_session, risk, Decimal("1000"))
