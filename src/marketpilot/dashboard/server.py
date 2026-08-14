"""
MarketPilot Dashboard - Operational Mission Control.
"""

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager
import asyncio

from marketpilot.engines.health_monitor import HealthMonitor
from marketpilot.core.metrics_registry import MetricsRegistry
from marketpilot.engines.trading_pipeline import TradingPipeline
from marketpilot.engines.watchdog import Watchdog
from marketpilot.config.settings import AppSettings
from marketpilot.models.audit import AuditRecord
from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.exchange.public_adapter import PublicBybitMarketDataAdapter
from marketpilot.dashboard.feed import DashboardObservationFeed
from marketpilot.dashboard.store import DashboardReadStore
from marketpilot.dashboard.router import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = AppSettings()
    
    # Check if a fake client was injected for tests
    client = getattr(app.state, "client_override", None)
    if not client:
        # Real read-only client (no api keys needed for public endpoints used in feed)
        base_client = BybitClient(exchange_settings=settings.exchange, execution_mode=settings.execution_mode)
        client = PublicBybitMarketDataAdapter(base_client)
        
    if hasattr(client, "connect"):
        await client.connect()
        
    # Initialize DashboardReadStore
    store = DashboardReadStore()
    app.state.dashboard_read_store = store
    app.state.settings = settings
    app.state.client = client
    
    # Create the read-only observation feed task
    feed = DashboardObservationFeed(store=store, client=client, settings=settings)
    app.state.feed = feed
    feed_task = asyncio.create_task(feed.run_loop())
    
    yield
    
    # SHUTDOWN
    feed.is_running = False
    feed_task.cancel()
    try:
        await feed_task
    except asyncio.CancelledError:
        pass
    
    if hasattr(client, "disconnect"):
        await client.disconnect()
    elif hasattr(client, "close"):
        await client.close()

app = FastAPI(title="MarketPilot Mission Control", docs_url=None, redoc_url=None, lifespan=lifespan)
app.include_router(router)

# We will inject dependencies manually when starting the server
app.state.settings = None
app.state.client = None
app.state.feed = None
app.state.dashboard_read_store = None

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Optional: Mount static files if needed
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

def get_system_status():
    """Helper to collect data for the dashboard."""
    settings: AppSettings = app.state.settings
    feed = getattr(app.state, "feed", None)
    
    cb_state = "UNKNOWN" # Daemon health not shared in memory anymore
    
    # Correct Daemon Status logic using read store projection
    daemon_status = "UNKNOWN"
    store = getattr(app.state, "dashboard_read_store", None)
    if store:
        lifecycle = store.get_lifecycle()
        meta = store.get_projection_metadata()
        cadence = meta.get("evaluation_cadence_seconds", 60) if meta else 60
        from marketpilot.dashboard.router import _evaluate_projection_liveness
        is_stale, liveness = _evaluate_projection_liveness(lifecycle, cadence)
        daemon_status = liveness
    
    return {
        "status": daemon_status,
        "version": "1.0.0",
        "rc_version": "RC-1",
        "git_commit": "N/A", # Ideally read from env
        "config_hash": "LOCKED",
        "arch_status": "CORE FROZEN",
        "cb_state": cb_state,
        "health": {},
        "metrics": {},
        "market_data_feed": "DEGRADED" if (feed and feed.is_degraded) else "HEALTHY" if (feed and feed.is_running) else "STOPPED"
    }

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Renders the main dashboard page."""
    status = get_system_status()
    return templates.TemplateResponse(request=request, name="index.html", context={"status": status})

@app.get("/api/status")
async def api_status():
    """JSON endpoint for HTMX polling."""
    return get_system_status()

@app.get("/fragments/health", response_class=HTMLResponse)
async def fragment_health(request: Request):
    """HTMX fragment for health updates."""
    status = get_system_status()
    scheduler_running = False # Daemon memory decoupled
    return templates.TemplateResponse(request=request, name="fragments/health.html", context={"status": status, "scheduler_running": scheduler_running})

@app.get("/api/ready")
async def api_ready():
    """Readiness probe."""
    cb_state = "UNKNOWN"
    scheduler = "STOPPED" # Daemon memory decoupled
    return JSONResponse({
        "ready": True, # Dashboard is ready if feed is running
        "reason": None,
        "architecture": "PHASE_4_CAUSAL",
        "config_locked": True,
        "scheduler": scheduler,
        "circuit_breaker": cb_state
    })



@app.get("/decision/{decision_key}", response_class=HTMLResponse)
async def view_decision(request: Request, decision_key: str):
    """Live Decision Inspector reading from DashboardReadStore."""
    store = app.state.dashboard_read_store
    record_model = store.get_evidence_traceability(decision_key) if store else None
    record = record_model.model_dump() if record_model else None
        
    return templates.TemplateResponse(request=request, name="decision.html", context={"decision_id": decision_key, "record": record})

