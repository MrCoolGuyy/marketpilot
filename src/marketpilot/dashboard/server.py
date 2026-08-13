"""
MarketPilot Dashboard - Operational Mission Control.
"""

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from marketpilot.engines.health_monitor import HealthMonitor
from marketpilot.core.metrics_registry import MetricsRegistry
from marketpilot.engines.trading_pipeline import TradingPipeline
from marketpilot.engines.watchdog import Watchdog
from marketpilot.config.settings import AppSettings
from marketpilot.models.audit import AuditRecord

app = FastAPI(title="MarketPilot Mission Control", docs_url=None, redoc_url=None)

# We will inject dependencies manually when starting the server
app.state.daemon = None
app.state.health = None
app.state.metrics = None
app.state.pipeline = None
app.state.watchdog = None
app.state.settings = None

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Optional: Mount static files if needed
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

def get_system_status():
    """Helper to collect data for the dashboard."""
    health: HealthMonitor = app.state.health
    watchdog: Watchdog = app.state.watchdog
    settings: AppSettings = app.state.settings
    metrics: MetricsRegistry = app.state.metrics
    pipeline: TradingPipeline = app.state.pipeline
    
    cb_state = "UNKNOWN"
    if health and health.cb:
        cb_state = health.cb.state.value

    return {
        "status": "RUNNING" if watchdog else "STOPPED",
        "version": "1.0.0",
        "rc_version": "RC-1",
        "git_commit": "N/A", # Ideally read from env
        "config_hash": "LOCKED",
        "arch_status": "CORE FROZEN",
        "cb_state": cb_state,
        "health": health.get_health_snapshot() if health else {},
        "metrics": metrics.get_all_metrics() if metrics else {},
    }

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Renders the main dashboard page."""
    status = get_system_status()
    return templates.TemplateResponse("index.html", {"request": request, "status": status})

@app.get("/api/status")
async def api_status():
    """JSON endpoint for HTMX polling."""
    return get_system_status()

@app.get("/fragments/health", response_class=HTMLResponse)
async def fragment_health(request: Request):
    """HTMX fragment for health updates."""
    status = get_system_status()
    # Read the state directly from cb
    daemon = app.state.daemon
    scheduler_running = daemon.scheduler._is_running if daemon and daemon.scheduler else False
    return templates.TemplateResponse("fragments/health.html", {"request": request, "status": status, "scheduler_running": scheduler_running})

@app.get("/api/ready")
async def api_ready():
    """Readiness probe."""
    daemon = app.state.daemon
    cb_state = app.state.health.cb.state.value if app.state.health and app.state.health.cb else "UNKNOWN"
    scheduler = "RUNNING" if (daemon and daemon.scheduler and daemon.scheduler._is_running) else "STOPPED"
    return JSONResponse({
        "ready": cb_state == "NORMAL",
        "reason": None if cb_state == "NORMAL" else "Circuit Breaker is not NORMAL",
        "architecture": "FROZEN",
        "config_locked": True,
        "scheduler": scheduler,
        "circuit_breaker": cb_state
    })

@app.post("/api/halt")
async def api_halt(request: Request, control_key: str = Form(...)):
    """Operator Kill Switch."""
    settings: AppSettings = app.state.settings
    if control_key != settings.dashboard_control_key.get_secret_value():
        raise HTTPException(status_code=403, detail="Invalid control key")
        
    daemon = app.state.daemon
    client_ip = request.client.host if request.client else "unknown"
    if daemon:
        await daemon.halt_trading(operator="Dashboard", ip=client_ip, reason="Manual Operator Halt")
        
    with open("operator_audit.log", "a") as f:
        from datetime import datetime
        f.write(f"{datetime.utcnow().isoformat()} - Operator: Dashboard - IP: {client_ip} - Action: HALT - Reason: Manual Operator Halt\n")
    
    return HTMLResponse("<span class='pill err'>HALTED</span>")

@app.post("/api/resume")
async def api_resume(request: Request, control_key: str = Form(...)):
    """Operator Resume."""
    settings: AppSettings = app.state.settings
    if control_key != settings.dashboard_control_key.get_secret_value():
        raise HTTPException(status_code=403, detail="Invalid control key")
        
    daemon = app.state.daemon
    client_ip = request.client.host if request.client else "unknown"
    if daemon:
        await daemon.resume_trading(operator="Dashboard", ip=client_ip, reason="Manual Operator Resume")
        
    with open("operator_audit.log", "a") as f:
        from datetime import datetime
        f.write(f"{datetime.utcnow().isoformat()} - Operator: Dashboard - IP: {client_ip} - Action: RESUME - Reason: Manual Operator Resume\n")
        
    return HTMLResponse("<span class='pill ok'>RUNNING</span>")

@app.get("/decision/{decision_id}", response_class=HTMLResponse)
async def view_decision(request: Request, decision_id: str):
    """Live Decision Inspector reading from AuditRecord."""
    daemon = app.state.daemon
    record = None
    if daemon and daemon.pipeline and daemon.pipeline.audit_engine:
        record = daemon.pipeline.audit_engine._journal.get(decision_id) # Direct access for dashboard
        
    return templates.TemplateResponse("decision.html", {"request": request, "decision_id": decision_id, "record": record})

