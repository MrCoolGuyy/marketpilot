"""
MarketPilot Dashboard — API Router.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal

from fastapi import APIRouter, Request, HTTPException, Query, Header, Depends
from pydantic import BaseModel

from marketpilot.core.enums import Interval, AssetType
from marketpilot.config.settings import AppSettings

router = APIRouter(prefix="/api")
logger = logging.getLogger("marketpilot.dashboard")

_CACHE: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 30

def _get_cached(key: str) -> dict | None:
    if key in _CACHE:
        data, timestamp = _CACHE[key]
        if time.time() - timestamp < _CACHE_TTL:
            return data
    return None

def _set_cached(key: str, data: dict) -> None:
    _CACHE[key] = (data, time.time())

@router.get("/health")
async def get_health(request: Request):
    """Health check endpoint."""
    # Ensure database is reachable
    db_ok = await request.app.state.db.health_check()
    if not db_ok:
        raise HTTPException(status_code=503, detail="Database unhealthy")
    return {"status": "ok"}

@router.get("/settings")
async def get_settings(request: Request):
    """Get public settings."""
    settings = request.app.state.settings
    return {
        "demo_execution_enabled": settings.demo.execution_enabled,
        "demo_auto_submit_enabled": settings.demo.auto_submit_enabled,
        "kill_switch": settings.demo.kill_switch,
        "max_daily_trades": settings.demo.max_daily_trades,
    }


@router.get("/scan")
async def scan_market(request: Request):
    """Run a market scan."""
    cache_key = "scan"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    scanner = request.app.state.scanner
    try:
        results = await scanner.scan()
        data = {"results": [r.model_dump(mode="json") for r in results]}
        _set_cached(cache_key, data)
        return data
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        raise HTTPException(status_code=500, detail="Scan failed")


@router.get("/market")
async def get_market(
    request: Request,
    symbol: str = Query(..., description="Trading pair symbol"),
    interval: int = Query(60, description="Time interval in minutes")
):
    """Get market data, indicators, and risk assessment."""
    try:
        inv = Interval(str(interval))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid interval")

    cache_key = f"market_{symbol}_{interval}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    client = request.app.state.client
    indicator_service = request.app.state.indicator_service
    strategy_service = request.app.state.strategy_service
    risk_service = request.app.state.risk_service
    
    try:
        # We only use public endpoints
        klines = await client.get_klines(
            symbol=symbol,
            interval=inv,
            asset_type=AssetType("linear"),
            limit=200
        )
        if not klines:
            raise HTTPException(status_code=404, detail="No klines found")
            
        # Filter out incomplete active candle
        closed_klines = [k for k in klines if k.is_closed]
        if not closed_klines:
            raise HTTPException(status_code=404, detail="No closed klines found")
            
        series = indicator_service.calculate(closed_klines)
        latest_indicator = series.latest
        
        signal = strategy_service.evaluate(series)
        
        # Risk requires equity. We read from paper account.
        db = request.app.state.db
        paper_service = request.app.state.paper_service
        
        async with db.session() as session:
            # We don't have current market prices for all positions, just pass an empty dict for now,
            # or the latest close price for this specific symbol
            prices = {symbol: Decimal(closed_klines[-1].close)}
            paper_snapshot = await paper_service.get_snapshot(session, prices)
            equity = paper_snapshot.equity
            
        latest_price = Decimal(closed_klines[-1].close)
        
        if latest_indicator is None or latest_indicator.atr is None:
            # Not enough data for indicators/ATR
            from marketpilot.models.risk import RiskAssessment
            assessment = RiskAssessment(
                symbol=signal.symbol,
                interval=signal.interval,
                open_time=signal.open_time,
                direction=signal.direction,
                eligible_for_paper_trading=False,
                reasons=("insufficient_indicator_data",),
                stop_loss=None,
                take_profit=None,
                theoretical_quantity=None,
                theoretical_notional=None,
                reward_risk_ratio=None,
            )
        else:
            latest_atr = latest_indicator.atr
            assessment = risk_service.assess(
                signal=signal,
                entry_price=latest_price,
                atr=latest_atr,
                account_equity=equity
            )
        
        data = {
            "symbol": symbol,
            "interval": interval,
            "latest_price": str(latest_price),
            "signal": signal.model_dump(mode="json"),
            "risk": assessment.model_dump(mode="json"),
            "indicators": latest_indicator.model_dump(mode="json") if latest_indicator else None,
            # Also return the last 50 candles for the chart
            "klines": [k.model_dump(mode="json") for k in closed_klines[-50:]]
        }
        _set_cached(cache_key, data)
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Market fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch market data")


@router.get("/paper")
async def get_paper(request: Request):
    """Get read-only paper trading snapshot with evaluations."""
    db = request.app.state.db
    paper_service = request.app.state.paper_service
    client = request.app.state.client
    
    try:
        from marketpilot.core.enums import AssetType
        # Bulk fetch all tickers to evaluate open positions properly
        tickers = await client.get_tickers(symbol="", asset_type=AssetType("linear"))
        prices = {t.symbol: t.last_price for t in tickers}
        
        async with db.session() as session:
            snapshot = await paper_service.get_snapshot(session, prices)
            
        from marketpilot.positions.service import PositionManagerService
        manager = PositionManagerService()
        decisions = manager.evaluate_positions(snapshot.positions, prices)
        
        decision_map = {d.symbol: d for d in decisions}
        
        # Inject decision into payload
        data = snapshot.model_dump(mode="json")
        for i, pos in enumerate(data.get("positions", [])):
            d = decision_map.get(pos["symbol"])
            if d:
                pos["decision_action"] = d.action.value
                pos["decision_reason"] = d.reason
            else:
                pos["decision_action"] = "N/A"
                pos["decision_reason"] = ""
                
        return {"data": data}
    except Exception as e:
        logger.error(f"Paper snapshot failed: {e}")
        # Always return safe read-only payload even if Bybit fetch fails
        try:
            async with db.session() as session:
                snapshot = await paper_service.get_snapshot(session, {})
            return {"data": snapshot.model_dump(mode="json")}
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to fetch paper snapshot")


@router.get("/backtest/latest")
async def get_backtest_latest(request: Request):
    """Get the latest backtest report."""
    report_store = request.app.state.report_store
    report = report_store.load_backtest()
    if not report:
        raise HTTPException(status_code=404, detail="No historical run available")
    return {"data": report.model_dump(mode="json")}


@router.get("/optimization/latest")
async def get_optimization_latest(request: Request):
    """Get the latest optimization report."""
    report_store = request.app.state.report_store
    report = report_store.load_optimization()
    if not report:
        raise HTTPException(status_code=404, detail="No historical run available")
    return {"data": report.model_dump(mode="json")}

@router.get("/research/latest")
async def get_research_latest():
    """Get the latest research report."""
    from marketpilot.research.store import ResearchStore
    store = ResearchStore()
    report = store.load_report()
    if not report:
        raise HTTPException(status_code=404, detail="No historical run available")
    return {"data": report.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Control Center POST Endpoints
# ---------------------------------------------------------------------------

async def verify_control_key(request: Request, x_marketpilot_control_key: str = Header(None)) -> AppSettings:
    """Dependency to verify the request comes from localhost with the correct secret key."""
    # Ensure localhost
    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        logger.warning(f"Rejected POST from non-localhost: {client_host}")
        raise HTTPException(status_code=403, detail="Forbidden: Control endpoints are restricted to localhost.")
        
    settings: AppSettings = request.app.state.settings
    expected_key = settings.dashboard_control_key.get_secret_value()
    
    if not expected_key:
        raise HTTPException(status_code=500, detail="Dashboard Control Key is not configured in environment.")
        
    if not x_marketpilot_control_key or x_marketpilot_control_key != expected_key:
        logger.warning("Rejected POST due to invalid control key.")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid control key.")
        
    return settings


class DemoOpenRequest(BaseModel):
    symbol: str

@router.post("/control/demo/open")
async def control_demo_open(req: DemoOpenRequest, request: Request, settings: AppSettings = Depends(verify_control_key)):
    """Manually open a demo position."""
    from marketpilot.demo.service import DemoExecutionService
    from marketpilot.core.enums import Interval, AssetType
    from decimal import Decimal
    
    client = request.app.state.client
    service = DemoExecutionService(settings)
    
    try:
        klines = await client.get_klines(symbol=req.symbol.upper(), interval=Interval.H1, limit=200, asset_type=AssetType.LINEAR)
        closed_klines = [k for k in klines if k.is_closed]
        if not closed_klines:
            raise HTTPException(status_code=400, detail="No closed klines")
            
        equity = Decimal("10000") # Need real equity? Autopilot queries it. For manual let's query it.
        bal_resp = await client._call(client._http.get_wallet_balance, accountType="UNIFIED")
        if "result" in bal_resp and "list" in bal_resp["result"]:
            for acc in bal_resp["result"]["list"]:
                equity = Decimal(acc.get("totalEquity", "0"))
                break
                
        record = await service.execute_open(req.symbol.upper(), Interval.H1.value, equity, closed_klines)
        if not record:
            raise HTTPException(status_code=400, detail="Execution rejected (Not eligible or disabled)")
            
        return {"status": "ok", "record": record.model_dump(mode="json")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Demo open failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class DemoCloseRequest(BaseModel):
    symbol: str
    quantity: str | None = None

@router.post("/control/demo/close")
async def control_demo_close(req: DemoCloseRequest, request: Request, settings: AppSettings = Depends(verify_control_key)):
    """Manually close a demo position."""
    from marketpilot.demo.service import DemoExecutionService
    from decimal import Decimal
    
    service = DemoExecutionService(settings)
    qty = Decimal(req.quantity) if req.quantity else None
    
    record = await service.execute_close(req.symbol.upper(), qty)
    if not record:
        raise HTTPException(status_code=400, detail="Failed to close position (None found, ambiguous, or error)")
        
    return {"status": "ok", "record": record.model_dump(mode="json")}


@router.post("/control/autopilot/run")
async def control_autopilot_run(request: Request, settings: AppSettings = Depends(verify_control_key)):
    """Run one cycle of the candidate autopilot."""
    from marketpilot.autopilot.service import AutopilotService
    
    service = AutopilotService(settings)
    try:
        decision = await service.run_cycle()
        if not decision:
            return {"status": "ok", "message": "No eligible candidate or halted by guards", "decision": None}
            
        return {"status": "ok", "decision": decision.model_dump(mode="json")}
    except Exception as e:
        logger.error(f"Autopilot cycle failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

