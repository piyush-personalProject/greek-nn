# api.py
"""
FX Greeks UI API
FastAPI backend for front-office trader UI.
Provides real-time Greeks, spot horizon, and time ladder views.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import asyncio
import json

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import config
from schemas import (
    Portfolio, PortfolioPosition, Greeks, PortfolioGreeks, VolSurface,
    ComputeRiskRequest, ComputeRiskResponse, RiskAlert, TradeCreate,
    NewsEvent, EventVector, GreeksImpactWeights,
    SpotRateResponse, SpotRateChange, SpotRateHistoryItem,
    SpotRateAlertData, RiskAlertData, AlertsResponse,
    CombinedImpactRequest, CombinedImpactResponse, SpotImpactData
)
from nn_risk_engine import NNRiskEngine, BlackScholesGreeksCPU
from vol_surface_service import VolSurfaceService, create_mock_surface
from nlp_engine import NLPEngine
from vol_shock_model import VolShockModel
from news_ingestion import NewsIngestionService
from services.forex_service import ForexService, get_forex_service, init_forex_service
from services.alert_service import AlertService, get_alert_service, init_alert_service
from services.audit_service import init_audit_service, get_audit_service
from logger import get_logger, create_trace, setup_logging

# Initialize logging
setup_logging()

logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="FX Greeks Risk API",
    description="Real-time Greeks visualization for FX spot and options",
    version="1.0.0"
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(request, call_next):
    """Middleware to create trace context for each request."""
    from logger import create_trace, get_tracer
    
    # Extract or generate trace ID
    trace_id = request.headers.get("X-Trace-ID") or None
    
    with create_trace(name=request.url.path, trace_id=trace_id) as trace:
        # Add trace ID to response headers
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace.trace_id
        return response


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global services (initialized on startup)
risk_engine: Optional[NNRiskEngine] = None
vol_surface_service: Optional[VolSurfaceService] = None
nlp_engine: Optional[NLPEngine] = None
vol_shock_model: Optional[VolShockModel] = None
news_service: Optional[NewsIngestionService] = None
forex_service: Optional[ForexService] = None
alert_service: Optional[AlertService] = None

# In-memory portfolio store (replace with DB in production)
_portfolios: Dict[str, Portfolio] = {}
_current_vol_surface: Optional[VolSurface] = None
_current_spot_rates: Dict[str, float] = {
    "EURUSD": 1.0850,
    "USDJPY": 149.50,
    "GBPUSD": 1.2650,
    "USDCHF": 0.8850,
    "AUDUSD": 0.6550,
    "USDCAD": 1.3450,
    "NZDUSD": 0.6050,
}

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.append(connection)
        
        # Clean up dead connections
        for conn in dead_connections:
            self.disconnect(conn)

manager = ConnectionManager()


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global risk_engine, vol_surface_service, nlp_engine, vol_shock_model, news_service, forex_service, alert_service, _current_vol_surface
    
    logger.info("Initializing FX Greeks Risk API...")
    
    # Initialize risk engine (use auto mode to prefer ONNX, fallback to Black-Scholes)
    risk_engine = NNRiskEngine(model_mode="auto")
    
    # Initialize vol surface service
    vol_surface_service = VolSurfaceService()
    
    # Initialize NLP Engine (Module 2)
    if config.enable_nlp_engine:
        nlp_engine = NLPEngine(
            model_name=config.ml.nlp_model,
            device=config.ml.nlp_device
        )
        logger.info("NLP Engine initialized")
    
    # Initialize Vol Shock Model (Module 3)
    if config.enable_vol_shock:
        vol_shock_model = VolShockModel(
            model_path=config.ml.vol_model_path,
            device="cpu",
            nlp_engine=nlp_engine
        )
        logger.info(f"Vol Shock Model initialized in {vol_shock_model.model_mode} mode")
    
    # Initialize News Ingestion Service (Module 1)
    if config.enable_news_ingestion:
        news_service = NewsIngestionService()
        logger.info("News Ingestion Service initialized")
    
    # Initialize Forex Service for live spot rates
    if config.enable_live_spot_rates:
        forex_service = init_forex_service(
            api_key=config.forex_api.api_key,
            poll_interval=config.forex_api.poll_interval,
            timeout=config.forex_api.timeout
        )
        logger.info("Forex Service initialized")
        
        # Fetch initial spot rates
        try:
            initial_rates = await forex_service.fetch_rates()
            _current_spot_rates.update(initial_rates)
            logger.info(f"Initial spot rates fetched: {len(initial_rates)} pairs")
        except Exception as e:
            logger.warning(f"Failed to fetch initial spot rates: {e}")
    
    # Initialize Alert Service
    if config.enable_alerts:
        alert_service = init_alert_service(
            spot_move_threshold_pct=config.spot_alert.move_threshold_pct,
            alert_cooldown_sec=config.spot_alert.alert_interval_sec,
            max_alerts_per_hour=config.spot_alert.max_alerts_per_hour
        )
        logger.info("Alert Service initialized")
        
        # Start background spot rate alert monitor (60s interval)
        if forex_service:
            asyncio.create_task(_spot_rate_alert_monitor())
            logger.info("Spot rate alert monitor started (60s interval)")
    
    # Create mock vol surface for demo
    _current_vol_surface = create_mock_surface(
        base_date=datetime.now(),
        base_vol=0.10
    )
    
    # Create demo portfolio
    _create_demo_portfolio()
    
    # Verify portfolio was created
    portfolio = _portfolios.get("FX-PORTFOLIO-01")
    if portfolio:
        logger.info(f"Demo portfolio created with {len(portfolio.positions)} positions")
    else:
        logger.error("Failed to create demo portfolio!")
    
    logger.info("FX Greeks Risk API initialized successfully")


@app.get("/api/debug/portfolio-status")
async def debug_portfolio_status():
    """Debug endpoint to check portfolio status."""
    portfolio = _portfolios.get("FX-PORTFOLIO-01")
    if portfolio:
        return {
            "status": "ok",
            "portfolio_id": portfolio.portfolio_id,
            "positions_count": len(portfolio.positions),
            "positions": [
                {
                    "position_id": p.position_id,
                    "instrument": p.instrument,
                    "strike": p.strike,
                    "tenor": p.tenor,
                    "quantity": p.quantity,
                    "option_type": p.option_type
                }
                for p in portfolio.positions
            ]
        }
    else:
        return {
            "status": "error",
            "message": "Portfolio not found",
            "available_portfolios": list(_portfolios.keys())
        }


async def _spot_rate_alert_monitor():
    """
    Background task to monitor spot rates and trigger alerts.
    Polls every 60 seconds (1 minute) for more responsive alerts.
    """
    from services.forex_service import get_forex_service
    from services.alert_service import get_alert_service
    
    poll_interval = 60  # 60 seconds (1 minute) for more responsive alert detection
    
    logger.info(f"Starting spot rate alert monitor (interval: {poll_interval}s)")
    
    while True:
        try:
            forex = get_forex_service()
            alerts = get_alert_service()
            
            if forex and alerts:
                # Fetch current rates
                rates = await forex.fetch_rates()
                
                if rates:
                    logger.info(f"Spot rate monitor: checking {len(rates)} pairs")
                    
                    for pair, rate in rates.items():
                        change = forex.get_rate_change(pair)
                        
                        logger.info(f"Spot monitor checking {pair}: rate={rate}, change={change}")
                        
                        if change["current"] and change["baseline"]:
                            # Check if alert should be triggered
                            alert = alerts.check_spot_rate_alert(
                                pair, rate, change["baseline"]
                            )
                            
                            if alert:
                                logger.warning(f"ALERT TRIGGERED: {alert.message}")
                                # Broadcast alert via WebSocket if manager available
                                if manager:
                                    await manager.broadcast({
                                        "type": "spot_alert",
                                        "alert": {
                                            "alert_id": alert.alert_id,
                                            "pair": alert.pair,
                                            "alert_type": alert.alert_type,
                                            "current_rate": alert.current_rate,
                                            "baseline_rate": alert.baseline_rate,
                                            "change_pct": alert.change_pct,
                                            "threshold_pct": alert.threshold_pct,
                                            "timestamp": alert.timestamp.isoformat(),
                                            "message": alert.message
                                        }
                                    })
            else:
                logger.warning("Spot rate monitor: services not available")
                
        except Exception as e:
            logger.error(f"Spot rate monitor error: {e}")
        
        await asyncio.sleep(poll_interval)


def _create_demo_portfolio():
    """Create a demo portfolio for testing."""
    positions = [
        PortfolioPosition(
            position_id="TRADE-001",
            instrument="EURUSD",
            spot=1.0850,
            strike=1.0900,
            tenor=1/12,  # 1M
            quantity=1000000,
            option_type="CALL",
            portfolio_id="FX-PORTFOLIO-01"
        ),
        PortfolioPosition(
            position_id="TRADE-002",
            instrument="EURUSD",
            spot=1.0850,
            strike=1.0800,
            tenor=3/12,  # 3M
            quantity=-500000,
            option_type="PUT",
            portfolio_id="FX-PORTFOLIO-01"
        ),
        PortfolioPosition(
            position_id="TRADE-003",
            instrument="USDJPY",
            spot=149.50,
            strike=150.00,
            tenor=1/52,  # 1W
            quantity=2000000,
            option_type="CALL",
            portfolio_id="FX-PORTFOLIO-01"
        ),
        PortfolioPosition(
            position_id="TRADE-004",
            instrument="GBPUSD",
            spot=1.2650,
            strike=1.2600,
            tenor=6/12,  # 6M
            quantity=750000,
            option_type="PUT",
            portfolio_id="FX-PORTFOLIO-01"
        ),
        PortfolioPosition(
            position_id="TRADE-005",
            instrument="USDJPY",
            spot=149.50,
            strike=148.00,
            tenor=1/12,  # 1M
            quantity=-1500000,
            option_type="CALL",
            portfolio_id="FX-PORTFOLIO-01"
        ),
    ]
    
    _portfolios["FX-PORTFOLIO-01"] = Portfolio(
        portfolio_id="FX-PORTFOLIO-01",
        timestamp=datetime.now(),
        positions=positions,
        base_currency="USD"
    )


# ==================== API Endpoints ====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main UI."""
    with open("templates/index.html", "r") as f:
        return f.read()


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    services = {
        "risk_engine": risk_engine.health_check() if risk_engine else "unavailable",
        "vol_surface": vol_surface_service.health_check() if vol_surface_service else "unavailable",
    }
    
    if nlp_engine:
        services["nlp_engine"] = nlp_engine.health_check()
    else:
        services["nlp_engine"] = "disabled"
    
    if vol_shock_model:
        services["vol_shock_model"] = vol_shock_model.health_check()
    else:
        services["vol_shock_model"] = "disabled"
    
    if news_service:
        services["news_service"] = news_service.health_check()
    else:
        services["news_service"] = "disabled"
    
    if forex_service:
        services["forex_service"] = forex_service.health_check()
    else:
        services["forex_service"] = "disabled"
    
    if alert_service:
        services["alert_service"] = alert_service.health_check()
    else:
        services["alert_service"] = "disabled"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": services
    }


@app.get("/api/portfolios")
async def list_portfolios():
    """List all portfolios."""
    return {
        "portfolios": [
            {
                "portfolio_id": p.portfolio_id,
                "timestamp": p.timestamp.isoformat(),
                "position_count": len(p.positions),
                "base_currency": p.base_currency
            }
            for p in _portfolios.values()
        ]
    }


@app.get("/api/portfolios/{portfolio_id}")
async def get_portfolio(portfolio_id: str):
    """Get portfolio details."""
    if portfolio_id not in _portfolios:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    portfolio = _portfolios[portfolio_id]
    return {
        "portfolio_id": portfolio.portfolio_id,
        "timestamp": portfolio.timestamp.isoformat(),
        "base_currency": portfolio.base_currency,
        "positions": [
            {
                **p.model_dump(),
                "timestamp": portfolio.timestamp.isoformat()
            }
            for p in portfolio.positions
        ]
    }


@app.post("/api/portfolios/{portfolio_id}/greeks")
async def compute_portfolio_greeks(
    portfolio_id: str,
    vol_surface_version: Optional[str] = None
):
    """Compute Greeks for a portfolio (spot horizon view)."""
    from logger import get_tracer, get_span_id
    
    with get_tracer().start_span("compute_greeks", portfolio_id=portfolio_id) as span:
        if portfolio_id not in _portfolios:
            span.log("Portfolio not found")
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        portfolio = _portfolios[portfolio_id]
        vol_surface = _current_vol_surface or create_mock_surface(datetime.now())
        
        span.log(f"Computing greeks for {len(portfolio.positions)} positions")
        
        try:
            portfolio_greeks = risk_engine.compute_portfolio_greeks(
                portfolio=portfolio,
                vol_surface=vol_surface,
                spot_rates=_current_spot_rates,
                risk_free_rate=0.05
            )
            
            span.log(f"Greeks computed successfully", level=20, 
                     total_delta=portfolio_greeks.total_greeks.delta,
                     total_vega=portfolio_greeks.total_greeks.vega)
            
            return {
                "portfolio_id": portfolio_greeks.portfolio_id,
                "timestamp": portfolio_greeks.timestamp.isoformat(),
                "vol_surface_version": portfolio_greeks.vol_surface_version,
                "total_greeks": portfolio_greeks.total_greeks.to_dict(),
                "position_greeks": {
                    pos_id: g.to_dict() 
                    for pos_id, g in portfolio_greeks.position_greeks.items()
                }
            }
        except Exception as e:
            span.log(f"Failed to compute Greeks: {e}", level=40)
            logger.error(f"Failed to compute Greeks: {e}", extra_fields={"portfolio_id": portfolio_id})
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/portfolios/{portfolio_id}/greeks/impacted")
async def compute_impacted_greeks(
    portfolio_id: str,
    vol_shock_id: str,
    weights: Optional[GreeksImpactWeights] = None,
    shocked_spot_rates: Optional[Dict[str, float]] = None,
    news_importance: Optional[float] = Query(None, description="News importance (0-1) for dynamic weight calculation"),
    news_sentiment_score: Optional[float] = Query(None, description="News sentiment score (-1 to 1) for dynamic weight calculation"),
    spot_rate_change_pct: Optional[float] = Query(None, description="Spot rate change percentage for dynamic weight calculation")
):
    """
    Compute Greeks with weighting between live spot rate and news shock impact.
    
    This endpoint blends between:
    - Base state using live spot rate (spot_rate_weight=1, vol_shock_weight=0)
    - Full shock state using shocked vol surface (spot_rate_weight=0, vol_shock_weight=1)
    - Any blended state with custom weights
    
    Args:
        portfolio_id: Portfolio to compute Greeks for
        vol_shock_id: ID of the vol shock to apply (from news impact)
        weights: Blending weights (default: vol_shock_weight=1.0 for full shock)
        shocked_spot_rates: Optional shocked spot rates for spot shock impact
        news_importance: News importance (0-1) - if provided along with other params, weights are computed dynamically
        news_sentiment_score: News sentiment score (-1 to 1) - if provided along with other params, weights are computed dynamically
        spot_rate_change_pct: Spot rate change percentage - if provided along with other params, weights are computed dynamically
        
    Dynamic Weight Calculation:
        If news_importance, news_sentiment_score, and spot_rate_change_pct are all provided,
        weights will be computed dynamically using GreeksImpactWeights.compute_dynamic_weights()
        based on news characteristics and spot rate movement.
    """
    from logger import get_tracer
    
    with get_tracer().start_span("compute_impacted_greeks", portfolio_id=portfolio_id) as span:
        if portfolio_id not in _portfolios:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        if vol_surface_service is None:
            raise HTTPException(status_code=503, detail="Vol surface service not available")
        
        if vol_shock_model is None:
            vol_shock_model = VolShockModel(nlp_engine=nlp_engine)
        
        portfolio = _portfolios[portfolio_id]
        base_vol_surface = _current_vol_surface or create_mock_surface(datetime.now())
        
        # Dynamic weight computation if all params provided
        if news_importance is not None and news_sentiment_score is not None and spot_rate_change_pct is not None:
            weights = GreeksImpactWeights.compute_dynamic_weights(
                news_importance=news_importance,
                news_sentiment_score=news_sentiment_score,
                spot_rate_change_pct=spot_rate_change_pct,
                base_spot_rate=1.0
            )
            span.log(f"Using dynamic weights: spot={weights.spot_rate_weight}, vol_shock={weights.vol_shock_weight}, spot_shock={weights.spot_shock_weight}")
        elif weights is None:
            # Default weights
            weights = GreeksImpactWeights(
                spot_rate_weight=0.0,
                vol_shock_weight=1.0,
                spot_shock_weight=0.0
            )
        
        span.log(f"Computing impacted greeks with weights: spot={weights.spot_rate_weight}, vol_shock={weights.vol_shock_weight}")
        
        try:
            # We need to find the vol shock by ID - for now, create a mock or use most recent
            # In production, this would come from a stored vol shock
            # For demo, we'll create a dummy vol shock based on the ID hash
            event_vector = EventVector(
                event_id=vol_shock_id,
                headline=f"Shock event {vol_shock_id}",
                event_type="MACRO",
                sentiment="NEUTRAL",
                sentiment_score=0.0,
                importance=0.5,
                surprise_factor=0.3,
                entities={"central_banks": [], "currencies": [], "indicators": []},
                processed_at=datetime.now(),
                source="api"
            )
            vol_shock = vol_shock_model.predict_shock(event_vector)
            
            # Get shocked surface
            shocked_vol_surface, shocked_version = vol_surface_service.get_shocked_surface(
                base_vol_surface, vol_shock
            )
            
            # Compute impacted (blended) Greeks
            impacted_greeks = risk_engine.compute_impacted_greeks(
                portfolio=portfolio,
                base_vol_surface=base_vol_surface,
                shocked_vol_surface=shocked_vol_surface,
                base_spot_rates=_current_spot_rates,
                shocked_spot_rates=shocked_spot_rates,
                weights=weights,
                risk_free_rate=0.05
            )
            
            # Also get baseline for comparison
            baseline_greeks = risk_engine.compute_portfolio_greeks(
                portfolio=portfolio,
                vol_surface=base_vol_surface,
                spot_rates=_current_spot_rates,
                risk_free_rate=0.05
            )
            
            # Calculate the delta (impact)
            delta_delta = impacted_greeks.total_greeks.delta - baseline_greeks.total_greeks.delta
            delta_gamma = impacted_greeks.total_greeks.gamma - baseline_greeks.total_greeks.gamma
            delta_vega = impacted_greeks.total_greeks.vega - baseline_greeks.total_greeks.vega
            delta_theta = impacted_greeks.total_greeks.theta - baseline_greeks.total_greeks.theta
            delta_rho = impacted_greeks.total_greeks.rho - baseline_greeks.total_greeks.rho
            
            return {
                "portfolio_id": impacted_greeks.portfolio_id,
                "timestamp": impacted_greeks.timestamp.isoformat(),
                "weights": {
                    "spot_rate_weight": weights.spot_rate_weight,
                    "vol_shock_weight": weights.vol_shock_weight,
                    "spot_shock_weight": weights.spot_shock_weight
                },
                "base_vol_surface_version": base_vol_surface.version,
                "shocked_vol_surface_version": shocked_version,
                "baseline_greeks": baseline_greeks.total_greeks.to_dict(),
                "impacted_greeks": impacted_greeks.total_greeks.to_dict(),
                "greeks_delta": {
                    "delta": round(delta_delta, 2),
                    "gamma": round(delta_gamma, 4),
                    "vega": round(delta_vega, 2),
                    "theta": round(delta_theta, 2),
                    "rho": round(delta_rho, 2)
                },
                "position_greeks": {
                    pos_id: g.to_dict() 
                    for pos_id, g in impacted_greeks.position_greeks.items()
                }
            }
        except Exception as e:
            span.log(f"Failed to compute impacted Greeks: {e}", level=40)
            logger.error(f"Failed to compute impacted Greeks: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/portfolios/{portfolio_id}/time-ladder")
async def get_time_ladder(
    portfolio_id: str,
    greek_type: str = Query("vega", description="Greek type: delta, gamma, vega, theta, rho")
):
    """Get time ladder view (Greeks bucketed by tenor)."""
    if portfolio_id not in _portfolios:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    portfolio = _portfolios[portfolio_id]
    vol_surface = _current_vol_surface or create_mock_surface(datetime.now())
    
    # Group positions by tenor bucket
    tenor_buckets = {
        "1W": [],
        "1M": [],
        "3M": [],
        "6M": [],
        "1Y": []
    }
    
    for position in portfolio.positions:
        bucket = _get_tenor_bucket(position.tenor)
        tenor_buckets[bucket].append(position)
    
    # Compute Greeks for each bucket
    ladder_data = []
    bucket_greeks = {}
    
    for bucket_name, positions in tenor_buckets.items():
        if not positions:
            continue
        
        # Create sub-portfolio for this bucket
        bucket_portfolio = Portfolio(
            portfolio_id=f"{portfolio_id}-{bucket_name}",
            timestamp=datetime.now(),
            positions=positions,
            base_currency=portfolio.base_currency
        )
        
        try:
            pg = risk_engine.compute_portfolio_greeks(
                portfolio=bucket_portfolio,
                vol_surface=vol_surface,
                spot_rates=_current_spot_rates,
                risk_free_rate=0.05
            )
            bucket_greeks[bucket_name] = pg.total_greeks
        except Exception as e:
            logger.warning(f"Failed to compute bucket {bucket_name}: {e}")
            bucket_greeks[bucket_name] = Greeks(delta=0, gamma=0, vega=0, theta=0, rho=0)
    
    # Build ladder response
    for bucket in ["1W", "1M", "3M", "6M", "1Y"]:
        g = bucket_greeks.get(bucket, Greeks(delta=0, gamma=0, vega=0, theta=0, rho=0))
        ladder_data.append({
            "tenor": bucket,
            "greeks": g.to_dict()
        })
    
    return {
        "portfolio_id": portfolio_id,
        "greek_type": greek_type,
        "timestamp": datetime.now().isoformat(),
        "ladder": ladder_data,
        "total": _sum_ladder_greeks(ladder_data)
    }


def _get_tenor_bucket(tenor: float) -> str:
    """Map tenor (in years) to bucket name."""
    if tenor <= 1/52:  # <= 1 week
        return "1W"
    elif tenor <= 1/12:  # <= 1 month
        return "1M"
    elif tenor <= 3/12:  # <= 3 months
        return "3M"
    elif tenor <= 6/12:  # <= 6 months
        return "6M"
    else:
        return "1Y"


def _sum_ladder_greeks(ladder: List[dict]) -> dict:
    """Sum Greeks across all ladder entries."""
    totals = {"delta": 0, "gamma": 0, "vega": 0, "theta": 0, "rho": 0, "vanna": 0, "volga": 0}
    for entry in ladder:
        for greek in totals.keys():
            val = entry["greeks"].get(greek, 0) or 0
            totals[greek] += val
    return totals


@app.get("/api/spot-rates")
async def get_spot_rates():
    """Get current spot rates."""
    return {
        "timestamp": datetime.now().isoformat(),
        "rates": _current_spot_rates
    }


@app.get("/api/spot-rates/live")
async def get_live_spot_rates():
    """
    Get live spot rates from forex API.
    Fetches fresh rates from the configured forex data provider.
    """
    global forex_service
    
    if forex_service is None:
        if not config.enable_live_spot_rates:
            raise HTTPException(status_code=503, detail="Live spot rates disabled")
        forex_service = init_forex_service()
    
    try:
        rates = await forex_service.fetch_rates()
        status = forex_service.get_status()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "rates": rates,
            "is_stale": status.get("is_stale", False),
            "last_update": status.get("last_update"),
            "source": "live" if config.forex_api.api_key else "mock"
        }
    except Exception as e:
        logger.error(f"Failed to fetch live spot rates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/spot-rates/history")
async def get_spot_rate_history(
    pair: str = Query("EURUSD", description="Currency pair"),
    days: int = Query(30, description="Number of days of history", ge=1, le=365)
):
    """
    Get historical spot rate data for a currency pair.
    """
    global forex_service
    
    if forex_service is None:
        forex_service = init_forex_service()
    
    try:
        history = await forex_service.fetch_historical(pair, days)
        return {
            "pair": pair,
            "days": days,
            "timestamp": datetime.now().isoformat(),
            "history": history
        }
    except Exception as e:
        logger.error(f"Failed to fetch spot rate history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/spot-rates/changes")
async def get_spot_rate_changes():
    """
    Get spot rate changes from baseline.
    Shows how much each rate has moved from its baseline value.
    """
    global forex_service
    
    if forex_service is None:
        if not config.enable_live_spot_rates:
            raise HTTPException(status_code=503, detail="Live spot rates disabled")
        forex_service = init_forex_service()
    
    changes = []
    for pair in _current_spot_rates.keys():
        change = forex_service.get_rate_change(pair)
        if change["current"]:
            direction = "up" if change["current"] > change["baseline"] else "down" if change["current"] < change["baseline"] else "unchanged"
            changes.append({
                "pair": pair,
                "current": change["current"],
                "baseline": change["baseline"],
                "change_pct": change["change_pct"],
                "direction": direction
            })
    
    return {
        "timestamp": datetime.now().isoformat(),
        "changes": changes
    }


@app.post("/api/spot-rates/baseline")
async def update_spot_baseline():
    """
    Update the baseline rates to current rates.
    This resets the change tracking.
    """
    global forex_service
    
    if forex_service is None:
        raise HTTPException(status_code=503, detail="Forex service not available")
    
    forex_service.update_baseline()
    
    return {
        "status": "success",
        "message": "Baseline updated to current rates",
        "timestamp": datetime.now().isoformat()
    }


# ==================== Alert Endpoints ====================

@app.get("/api/alerts/spot-rates")
async def get_spot_rate_alerts(
    pair: Optional[str] = Query(None, description="Filter by currency pair"),
    limit: int = Query(50, description="Maximum alerts to return", ge=1, le=200)
):
    """
    Get spot rate movement alerts.
    """
    global alert_service
    
    if alert_service is None:
        alert_service = init_alert_service()
    
    alerts = alert_service.get_spot_alerts(pair=pair, limit=limit)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "count": len(alerts),
        "alerts": [
            {
                "alert_id": a.alert_id,
                "pair": a.pair,
                "alert_type": a.alert_type,
                "current_rate": a.current_rate,
                "baseline_rate": a.baseline_rate,
                "change_pct": a.change_pct,
                "threshold_pct": a.threshold_pct,
                "timestamp": a.timestamp.isoformat(),
                "message": a.message
            }
            for a in alerts
        ]
    }


@app.get("/api/alerts/all")
async def get_all_alerts(
    since: Optional[str] = Query(None, description="ISO timestamp to filter alerts"),
    limit: int = Query(100, description="Maximum alerts per category", ge=1, le=200)
):
    """
    Get all alerts (spot rate + risk limits).
    """
    global alert_service
    
    if alert_service is None:
        alert_service = init_alert_service()
    
    since_dt = datetime.fromisoformat(since) if since else None
    result = alert_service.get_all_alerts(since=since_dt, limit=limit)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "spot_alerts": [
            {
                "alert_id": a.alert_id,
                "pair": a.pair,
                "alert_type": a.alert_type,
                "current_rate": a.current_rate,
                "baseline_rate": a.baseline_rate,
                "change_pct": a.change_pct,
                "threshold_pct": a.threshold_pct,
                "timestamp": a.timestamp.isoformat(),
                "message": a.message
            }
            for a in result["spot_alerts"]
        ],
        "risk_alerts": [
            {
                "alert_id": a.alert_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "title": a.title,
                "message": a.message,
                "current_value": a.current_value,
                "threshold_value": a.threshold_value,
                "timestamp": a.timestamp.isoformat(),
                "acknowledged": a.acknowledged
            }
            for a in result["risk_alerts"]
        ],
        "total_count": len(result["spot_alerts"]) + len(result["risk_alerts"])
    }


@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """
    Acknowledge an alert.
    """
    global alert_service
    
    if alert_service is None:
        raise HTTPException(status_code=503, detail="Alert service not available")
    
    success = alert_service.acknowledge_alert(alert_id)
    
    if success:
        return {"status": "success", "alert_id": alert_id}
    else:
        raise HTTPException(status_code=404, detail="Alert not found")


# ==================== Combined Impact Endpoint ====================

@app.post("/api/impact/combined")
async def get_combined_impact(
    request: CombinedImpactRequest = None
):
    """
    Calculate combined impact from spot rate movements and news-driven vol shocks.
    
    This endpoint blends:
    - Live spot rate movements (from forex API)
    - News-driven volatility shocks (from NLP + Vol Shock Model)
    
    Using configurable weights in GreeksImpactWeights.
    """
    from logger import get_tracer
    
    global forex_service, alert_service
    
    with get_tracer().start_span("combined_impact") as span:
        portfolio_id = request.portfolio_id if request else "FX-PORTFOLIO-01"
        
        if portfolio_id not in _portfolios:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        portfolio = _portfolios[portfolio_id]
        base_vol_surface = _current_vol_surface or create_mock_surface(datetime.now())
        
        # Default weights: 30% spot rate, 70% vol shock
        weights = request.weights if request and request.weights else GreeksImpactWeights(
            spot_rate_weight=0.3,
            vol_shock_weight=0.7
        )
        
        span.log(f"Computing combined impact with weights: spot={weights.spot_rate_weight}, vol_shock={weights.vol_shock_weight}")
        
        try:
            # 1. Get live spot rates
            if forex_service is None and config.enable_live_spot_rates:
                forex_service = init_forex_service()
            
            live_rates = {}
            spot_impacts = []
            if forex_service and config.enable_live_spot_rates:
                live_rates = await forex_service.fetch_rates()
                
                # Calculate spot rate impacts for each pair
                for pair, rate in live_rates.items():
                    change = forex_service.get_rate_change(pair)
                    if change["current"] and change["baseline"]:
                        # Rough estimate of Greek impact from spot move
                        # Delta impact proportional to rate change * notional
                        spot_impact_pct = change["change_pct"] / 100
                        
                        # Find positions for this pair
                        pair_positions = [p for p in portfolio.positions if p.instrument == pair]
                        for pos in pair_positions:
                            estimated_delta = pos.quantity * spot_impact_pct
                            estimated_gamma = abs(pos.quantity) * spot_impact_pct * 0.1  # Simplified
                            
                            spot_impacts.append({
                                "pair": pair,
                                "rate_change_pct": change["change_pct"],
                                "estimated_delta_impact": estimated_delta,
                                "estimated_gamma_impact": estimated_gamma
                            })
                        
                        # Check for spot rate alert
                        if alert_service and config.enable_alerts:
                            alert = alert_service.check_spot_rate_alert(
                                pair, rate, change["baseline"]
                            )
                            if alert:
                                span.log(f"Spot alert triggered for {pair}")
                        
                        # Update global rates
                        _current_spot_rates[pair] = rate
            
            # 2. Get baseline Greeks
            baseline_greeks = risk_engine.compute_portfolio_greeks(
                portfolio=portfolio,
                vol_surface=base_vol_surface,
                spot_rates=_current_spot_rates,
                risk_free_rate=0.05
            )
            
            # 3. Get latest news and process through NLP/Vol Shock
            vol_shock_impacts = []
            if news_service and nlp_engine and vol_shock_model and vol_surface_service:
                headlines = await news_service.fetch_all_headlines()
                headlines = sorted(headlines, key=lambda x: x.published_at, reverse=True)[:5]
                
                for h in headlines:
                    event_vector = nlp_engine.process_news_event(h)
                    vol_shock = vol_shock_model.predict_shock(event_vector)
                    shocked_surface, _ = vol_surface_service.get_shocked_surface(base_vol_surface, vol_shock)
                    
                    # Compute shocked Greeks
                    shocked_greeks = risk_engine.compute_portfolio_greeks(
                        portfolio=portfolio,
                        vol_surface=shocked_surface,
                        spot_rates=_current_spot_rates,
                        risk_free_rate=0.05
                    )
                    
                    vol_shock_impacts.append({
                        "headline": h.headline,
                        "event_type": event_vector.event_type.value,
                        "sentiment": event_vector.sentiment.value,
                        "vol_shocks": {
                            "1W_ATM": round(vol_shock.delta_1W_ATM, 5),
                            "1M_ATM": round(vol_shock.delta_1M_ATM, 5),
                            "3M_ATM": round(vol_shock.delta_3M_ATM, 5),
                        },
                        "greeks_delta": {
                            "delta": round(shocked_greeks.total_greeks.delta - baseline_greeks.total_greeks.delta, 2),
                            "vega": round(shocked_greeks.total_greeks.vega - baseline_greeks.total_greeks.vega, 2),
                        }
                    })
            
            # 4. Calculate combined impact using blending weights
            # Current Greeks use blended approach
            current_greeks = baseline_greeks.total_greeks
            
            # For spot impact, we apply spot_rate_weight to adjust Greeks
            # For vol shock, we apply vol_shock_weight
            
            # Calculate spot contribution (simplified - uses estimated impacts)
            spot_delta_total = sum(s.get("estimated_delta_impact", 0) for s in spot_impacts)
            spot_gamma_total = sum(s.get("estimated_gamma_impact", 0) for s in spot_impacts)
            
            # Calculate vol shock contribution from most impactful news
            vol_delta_total = 0.0
            vol_vega_total = 0.0
            if vol_shock_impacts:
                # Use the most impactful news for vol shock
                most_impactful = max(vol_shock_impacts, key=lambda x: abs(x["greeks_delta"].get("vega", 0)))
                vol_delta_total = most_impactful["greeks_delta"].get("delta", 0)
                vol_vega_total = most_impactful["greeks_delta"].get("vega", 0)
            
            # Blend the impacts
            blended_delta = (
                baseline_greeks.total_greeks.delta +
                (spot_delta_total * weights.spot_rate_weight) +
                (vol_delta_total * weights.vol_shock_weight)
            )
            blended_vega = (
                baseline_greeks.total_greeks.vega +
                (spot_gamma_total * weights.spot_rate_weight * 100) +  # Approximate conversion
                (vol_vega_total * weights.vol_shock_weight)
            )
            
            # Calculate deltas
            delta_delta = blended_delta - baseline_greeks.total_greeks.delta
            delta_vega = blended_vega - baseline_greeks.total_greeks.vega
            
            return {
                "timestamp": datetime.now().isoformat(),
                "portfolio_id": portfolio_id,
                "weights": {
                    "spot_rate_weight": weights.spot_rate_weight,
                    "vol_shock_weight": weights.vol_shock_weight
                },
                "baseline_greeks": baseline_greeks.total_greeks.to_dict(),
                "current_greeks": {
                    "delta": round(blended_delta, 2),
                    "gamma": baseline_greeks.total_greeks.gamma,
                    "vega": round(blended_vega, 2),
                    "theta": baseline_greeks.total_greeks.theta,
                    "rho": baseline_greeks.total_greeks.rho
                },
                "greeks_delta": {
                    "delta": round(delta_delta, 2),
                    "gamma": 0,
                    "vega": round(delta_vega, 2),
                    "theta": 0,
                    "rho": 0
                },
                "spot_impacts": spot_impacts,
                "vol_shock_impacts": vol_shock_impacts[:3],  # Top 3
                "live_rates": live_rates if live_rates else _current_spot_rates,
                "source": "live" if live_rates else "cached"
            }
            
        except Exception as e:
            span.log(f"Failed to compute combined impact: {e}", level=40)
            logger.error(f"Failed to compute combined impact: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vol-surface")
async def get_vol_surface():
    """Get current vol surface summary."""
    if _current_vol_surface is None:
        raise HTTPException(status_code=503, detail="Vol surface not available")
    
    vols_atm = []
    for i in range(len(_current_vol_surface.tenors)):
        vols_atm.append(_current_vol_surface.volatilities[i][0])
    return {
        "snapshot_id": _current_vol_surface.snapshot_id,
        "base_date": _current_vol_surface.base_date.isoformat(),
        "version": _current_vol_surface.version,
        "tenors": [f"{t:.4f}" for t in _current_vol_surface.tenors],
        "tenor_labels": ["1W", "1M", "3M", "6M", "1Y"],
        "strikes": _current_vol_surface.strikes,
        "vols_atm": vols_atm
    }


@app.get("/api/risk-summary")
async def get_risk_summary(portfolio_id: str = "FX-PORTFOLIO-01"):
    """Get comprehensive risk summary for dashboard."""
    if portfolio_id not in _portfolios:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    portfolio = _portfolios[portfolio_id]
    vol_surface = _current_vol_surface or create_mock_surface(datetime.now())
    
    # Compute full portfolio Greeks
    portfolio_greeks = risk_engine.compute_portfolio_greeks(
        portfolio=portfolio,
        vol_surface=vol_surface,
        spot_rates=_current_spot_rates,
        risk_free_rate=0.05
    )
    
    # Get time ladder
    ladder_response = await get_time_ladder(portfolio_id, "vega")
    
    return {
        "timestamp": datetime.now().isoformat(),
        "portfolio_id": portfolio_id,
        "spot_rates": _current_spot_rates,
        "total_greeks": portfolio_greeks.total_greeks.to_dict(),
        "time_ladder": ladder_response["ladder"],
        "position_count": len(portfolio.positions),
        "limits": {
            "vega_limit": config.risk_limits.vega_limit,
            "gamma_limit": config.risk_limits.gamma_limit,
            "delta_limit": config.risk_limits.delta_limit
        }
    }


@app.get("/api/news")
async def get_news(keyword: Optional[str] = None, max_results: int = 20):
    """Get recent news headlines."""
    from logger import get_tracer
    
    with get_tracer().start_span("news_fetch", keyword=keyword, max_results=max_results) as span:
        if news_service is None:
            logger.error("News service unavailable - not initialized")
            raise HTTPException(status_code=503, detail="News service not available")
        
        try:
            headlines = await news_service.fetch_all_headlines()
            
            if keyword:
                headlines = news_service.get_recent_by_keyword(keyword, max_results)
                span.log(f"Filtered headlines by keyword '{keyword}': {len(headlines)} results")
            else:
                headlines = sorted(headlines, key=lambda x: x.published_at, reverse=True)[:max_results]
            
            span.log(f"Returning {len(headlines)} headlines")
            
            return {
                "timestamp": datetime.now().isoformat(),
                "count": len(headlines),
                "headlines": [
                    {
                        "headline": h.headline,
                        "source": h.source,
                        "url": h.url,
                        "published_at": h.published_at.isoformat() if h.published_at else None,
                        "content": h.content
                    }
                    for h in headlines
                ]
            }
        except Exception as e:
            span.log(f"Failed to fetch news: {e}", level=40)
            logger.error(f"Failed to fetch news: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news-with-impact")
async def get_news_with_impact(
    max_results: int = 10,
    min_sentiment_score: float = Query(0.3, description="Minimum absolute sentiment score to include (0-1)")
):
    """
    Get news headlines WITH their Greeks impact - single call to avoid duplicate fetching.
    Combines /api/news and /api/news-impact functionality.
    
    Args:
        max_results: Maximum number of headlines to process
        min_sentiment_score: Minimum absolute sentiment score to include (default 0.3).
                           Only news with |sentiment_score| >= this value will be included.
    """
    from logger import get_tracer
    
    with get_tracer().start_span("news_with_impact", max_results=max_results) as span:
        global vol_shock_model
        
        if news_service is None:
            raise HTTPException(status_code=503, detail="News service not available")
        
        if nlp_engine is None:
            raise HTTPException(status_code=503, detail="NLP engine not available")
        
        if vol_shock_model is None:
            vol_shock_model = VolShockModel(nlp_engine=nlp_engine)
        
        if risk_engine is None:
            raise HTTPException(status_code=503, detail="Risk engine not available")
        
        try:
            # Get baseline Greeks (before any news)
            portfolio = _portfolios.get("FX-PORTFOLIO-01")
            if not portfolio:
                raise HTTPException(status_code=404, detail="Portfolio not found")
            
            baseline_surface = _current_vol_surface or create_mock_surface(datetime.now())
            baseline_greeks = risk_engine.compute_portfolio_greeks(
                portfolio=portfolio,
                vol_surface=baseline_surface,
                spot_rates=_current_spot_rates,
                risk_free_rate=0.05
            )
            
            # Fetch recent news ONCE
            headlines = await news_service.fetch_all_headlines()
            headlines = sorted(headlines, key=lambda x: x.published_at, reverse=True)[:max_results]

            impact_results = []

            # Initialize audit trace for this batch
            trace_id = f"news-batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            audit = get_audit_service()
            audit.begin_trace(trace_id)

            for h in headlines:
                # Persist news event to audit trail
                audit.persist_news_event(trace_id, h)

                # Process through NLP
                event_vector = nlp_engine.process_news_event(h)

                # Persist event vector to audit trail
                audit.persist_event_vector(trace_id, event_vector)

                # Predict vol shock
                vol_shock = vol_shock_model.predict_shock(event_vector)

                # Persist vol shock to audit trail
                audit.persist_vol_shock(trace_id, vol_shock)

                # Get shocked surface
                shocked_surface, shocked_version = vol_surface_service.get_shocked_surface(baseline_surface, vol_shock)

                # Persist vol surface to audit trail
                audit.persist_vol_surface(trace_id, vol_shock.shock_id, shocked_surface)

                # Compute new Greeks
                shocked_greeks = risk_engine.compute_portfolio_greeks(
                    portfolio=portfolio,
                    vol_surface=shocked_surface,
                    spot_rates=_current_spot_rates,
                    risk_free_rate=0.05
                )

                # Persist Greeks to audit trail
                greeks_snapshot_id = f"greeks-{event_vector.event_id}"
                audit.persist_greeks(
                    trace_id,
                    portfolio.portfolio_id,
                    shocked_surface.snapshot_id,
                    shocked_greeks.total_greeks,
                    greeks_snapshot_id
                )

                # Calculate deltas
                delta_delta = shocked_greeks.total_greeks.delta - baseline_greeks.total_greeks.delta
                delta_gamma = shocked_greeks.total_greeks.gamma - baseline_greeks.total_greeks.gamma
                delta_vega = shocked_greeks.total_greeks.vega - baseline_greeks.total_greeks.vega
                delta_theta = shocked_greeks.total_greeks.theta - baseline_greeks.total_greeks.theta
                delta_rho = shocked_greeks.total_greeks.rho - baseline_greeks.total_greeks.rho
                
                impact_results.append({
                    "headline": h.headline,
                    "source": h.source,
                    "url": h.url,
                    "published_at": h.published_at.isoformat() if h.published_at else None,
                    "content": h.content,
                    "event_type": event_vector.event_type.value,
                    "sentiment": event_vector.sentiment.value,
                    "sentiment_score": round(event_vector.sentiment_score, 3),
                    "importance": round(event_vector.importance, 3),
                    "affected_pairs": vol_shock.affected_pairs,
                    "greeks_impact": {
                        "delta": round(delta_delta, 2),
                        "gamma": round(delta_gamma, 4),
                        "vega": round(delta_vega, 2),
                        "theta": round(delta_theta, 2),
                        "rho": round(delta_rho, 2)
                    },
                    "vol_shocks": {
                        "1W_ATM": round(vol_shock.delta_1W_ATM, 5),
                        "1M_ATM": round(vol_shock.delta_1M_ATM, 5),
                        "3M_ATM": round(vol_shock.delta_3M_ATM, 5),
                        "6M_ATM": round(vol_shock.delta_6M_ATM, 5),
                        "1Y_ATM": round(vol_shock.delta_1Y_ATM, 5)
                    }
                })
            
            # Sort news by sentiment score (descending - strongest sentiment first)
            impact_results = sorted(impact_results, key=lambda x: x["sentiment_score"], reverse=True)
            
            # Filter by minimum absolute sentiment score
            original_count = len(impact_results)
            impact_results = [r for r in impact_results if abs(r["sentiment_score"]) >= min_sentiment_score]
            
            span.log(f"Processed {original_count} news with impact, filtered to {len(impact_results)} with |sentiment_score| >= {min_sentiment_score}")
            
            return {
                "timestamp": datetime.now().isoformat(),
                "trace_id": trace_id,
                "count": len(impact_results),
                "total_processed": original_count,
                "filter_applied": min_sentiment_score,
                "baseline_greeks": baseline_greeks.total_greeks.to_dict(),
                "news_impacts": impact_results
            }
        except Exception as e:
            span.log(f"Failed to compute news with impact: {e}", level=40)
            logger.error(f"Failed to compute news with impact: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/news/exclude")
async def compute_greeks_with_excluded_news(
    excluded_headlines: List[str] = Body(..., description="List of headlines to exclude from Greeks calculation"),
    portfolio_id: str = Query("FX-PORTFOLIO-01", description="Portfolio ID")
):
    """
    Compute Greeks after excluding specific news items.
    
    This endpoint allows removing news items from consideration and recalculating
    the Greeks impact based only on the remaining news.
    
    Args:
        excluded_headlines: List of headlines to exclude from calculation
        portfolio_id: Portfolio to compute Greeks for
    """
    from logger import get_tracer
    
    with get_tracer().start_span("compute_greeks_exclude_news", excluded_count=len(excluded_headlines)) as span:
        global vol_shock_model
        
        if news_service is None:
            raise HTTPException(status_code=503, detail="News service not available")
        
        if nlp_engine is None:
            raise HTTPException(status_code=503, detail="NLP engine not available")
        
        if vol_shock_model is None:
            vol_shock_model = VolShockModel(nlp_engine=nlp_engine)
        
        if risk_engine is None:
            raise HTTPException(status_code=503, detail="Risk engine not available")
        
        try:
            portfolio = _portfolios.get(portfolio_id)
            if not portfolio:
                raise HTTPException(status_code=404, detail="Portfolio not found")
            
            baseline_surface = _current_vol_surface or create_mock_surface(datetime.now())
            
            # Get baseline Greeks (before any news)
            baseline_greeks = risk_engine.compute_portfolio_greeks(
                portfolio=portfolio,
                vol_surface=baseline_surface,
                spot_rates=_current_spot_rates,
                risk_free_rate=0.05
            )
            
            # Fetch all headlines
            all_headlines = await news_service.fetch_all_headlines()
            all_headlines = sorted(all_headlines, key=lambda x: x.published_at, reverse=True)
            
            # Filter out excluded headlines
            filtered_headlines = [h for h in all_headlines if h.headline not in excluded_headlines]
            
            span.log(f"Computing Greeks with {len(filtered_headlines)} news (excluded {len(excluded_headlines)})")
            
            # Initialize audit trace
            trace_id = f"exclude-batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            audit = get_audit_service()
            audit.begin_trace(trace_id)
            
            cumulative_greeks = Greeks(
                delta=baseline_greeks.total_greeks.delta,
                gamma=baseline_greeks.total_greeks.gamma,
                vega=baseline_greeks.total_greeks.vega,
                theta=baseline_greeks.total_greeks.theta,
                rho=baseline_greeks.total_greeks.rho
            )
            cumulative_impacts = []
            
            for h in filtered_headlines:
                # Process through NLP
                event_vector = nlp_engine.process_news_event(h)
                
                # Predict vol shock
                vol_shock = vol_shock_model.predict_shock(event_vector)
                
                # Get shocked surface
                shocked_surface, _ = vol_surface_service.get_shocked_surface(baseline_surface, vol_shock)
                
                # Compute new Greeks
                shocked_greeks = risk_engine.compute_portfolio_greeks(
                    portfolio=portfolio,
                    vol_surface=shocked_surface,
                    spot_rates=_current_spot_rates,
                    risk_free_rate=0.05
                )
                
                # Track cumulative impact
                delta_delta = shocked_greeks.total_greeks.delta - cumulative_greeks.delta
                delta_gamma = shocked_greeks.total_greeks.gamma - cumulative_greeks.gamma
                delta_vega = shocked_greeks.total_greeks.vega - cumulative_greeks.vega
                delta_theta = shocked_greeks.total_greeks.theta - cumulative_greeks.theta
                delta_rho = shocked_greeks.total_greeks.rho - cumulative_greeks.rho
                
                cumulative_greeks = shocked_greeks.total_greeks
                
                cumulative_impacts.append({
                    "headline": h.headline,
                    "source": h.source,
                    "sentiment_score": round(event_vector.sentiment_score, 3),
                    "event_type": event_vector.event_type.value,
                    "greeks_impact": {
                        "delta": round(delta_delta, 2),
                        "gamma": round(delta_gamma, 4),
                        "vega": round(delta_vega, 2),
                        "theta": round(delta_theta, 2),
                        "rho": round(delta_rho, 2)
                    }
                })
            
            # Sort by absolute sentiment score
            cumulative_impacts = sorted(cumulative_impacts, key=lambda x: abs(x["sentiment_score"]), reverse=True)
            
            # Calculate deltas from baseline
            final_delta = cumulative_greeks.delta - baseline_greeks.total_greeks.delta
            final_gamma = cumulative_greeks.gamma - baseline_greeks.total_greeks.gamma
            final_vega = cumulative_greeks.vega - baseline_greeks.total_greeks.vega
            final_theta = cumulative_greeks.theta - baseline_greeks.total_greeks.theta
            final_rho = cumulative_greeks.rho - baseline_greeks.total_greeks.rho
            
            return {
                "timestamp": datetime.now().isoformat(),
                "trace_id": trace_id,
                "portfolio_id": portfolio_id,
                "excluded_count": len(excluded_headlines),
                "included_count": len(filtered_headlines),
                "baseline_greeks": baseline_greeks.total_greeks.to_dict(),
                "current_greeks": cumulative_greeks.to_dict(),
                "greeks_delta": {
                    "delta": round(final_delta, 2),
                    "gamma": round(final_gamma, 4),
                    "vega": round(final_vega, 2),
                    "theta": round(final_theta, 2),
                    "rho": round(final_rho, 2)
                },
                "news_impacts": cumulative_impacts
            }
        except Exception as e:
            span.log(f"Failed to compute Greeks with excluded news: {e}", level=40)
            logger.error(f"Failed to compute Greeks with excluded news: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news-impact")
async def get_news_impact(max_results: int = 10):
    """
    Get news with their impact on Greeks.
    Shows which news caused what change in portfolio Greeks.
    """
    from logger import get_tracer
    
    with get_tracer().start_span("news_impact", max_results=max_results) as span:
        global vol_shock_model
        
        if news_service is None:
            raise HTTPException(status_code=503, detail="News service not available")
        
        if nlp_engine is None:
            raise HTTPException(status_code=503, detail="NLP engine not available")
        
        if vol_shock_model is None:
            vol_shock_model = VolShockModel(nlp_engine=nlp_engine)
        
        if risk_engine is None:
            raise HTTPException(status_code=503, detail="Risk engine not available")
        
        try:
            # Get baseline Greeks (before any news)
            portfolio = _portfolios.get("FX-PORTFOLIO-01")
            if not portfolio:
                raise HTTPException(status_code=404, detail="Portfolio not found")
            
            baseline_surface = _current_vol_surface or create_mock_surface(datetime.now())
            baseline_greeks = risk_engine.compute_portfolio_greeks(
                portfolio=portfolio,
                vol_surface=baseline_surface,
                spot_rates=_current_spot_rates,
                risk_free_rate=0.05
            )
            
            # Fetch recent news
            headlines = await news_service.fetch_all_headlines()
            headlines = sorted(headlines, key=lambda x: x.published_at, reverse=True)[:max_results]

            impact_results = []

            # Initialize audit trace for this batch
            trace_id = f"news-batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            audit = get_audit_service()
            audit.begin_trace(trace_id)

            for h in headlines:
                # Persist news event to audit trail
                audit.persist_news_event(trace_id, h)

                # Process through NLP
                event_vector = nlp_engine.process_news_event(h)

                # Persist event vector to audit trail
                audit.persist_event_vector(trace_id, event_vector)

                # Predict vol shock
                vol_shock = vol_shock_model.predict_shock(event_vector)

                # Persist vol shock to audit trail
                audit.persist_vol_shock(trace_id, vol_shock)

                # Get shocked surface
                shocked_surface, shocked_version = vol_surface_service.get_shocked_surface(baseline_surface, vol_shock)

                # Persist vol surface to audit trail
                audit.persist_vol_surface(trace_id, vol_shock.shock_id, shocked_surface)

                # Compute new Greeks
                shocked_greeks = risk_engine.compute_portfolio_greeks(
                    portfolio=portfolio,
                    vol_surface=shocked_surface,
                    spot_rates=_current_spot_rates,
                    risk_free_rate=0.05
                )

                # Persist Greeks to audit trail
                greeks_snapshot_id = f"greeks-{event_vector.event_id}"
                audit.persist_greeks(
                    trace_id,
                    portfolio.portfolio_id,
                    shocked_surface.snapshot_id,
                    shocked_greeks.total_greeks,
                    greeks_snapshot_id
                )

                # Calculate deltas
                delta_delta = shocked_greeks.total_greeks.delta - baseline_greeks.total_greeks.delta
                delta_gamma = shocked_greeks.total_greeks.gamma - baseline_greeks.total_greeks.gamma
                delta_vega = shocked_greeks.total_greeks.vega - baseline_greeks.total_greeks.vega
                delta_theta = shocked_greeks.total_greeks.theta - baseline_greeks.total_greeks.theta
                delta_rho = shocked_greeks.total_greeks.rho - baseline_greeks.total_greeks.rho
                
                impact_results.append({
                    "headline": h.headline,
                    "source": h.source,
                    "url": h.url,
                    "published_at": h.published_at.isoformat() if h.published_at else None,
                    "event_type": event_vector.event_type.value,
                    "sentiment": event_vector.sentiment.value,
                    "sentiment_score": round(event_vector.sentiment_score, 3),
                    "importance": round(event_vector.importance, 3),
                    "affected_pairs": vol_shock.affected_pairs,
                    "greeks_impact": {
                        "delta": round(delta_delta, 2),
                        "gamma": round(delta_gamma, 4),
                        "vega": round(delta_vega, 2),
                        "theta": round(delta_theta, 2),
                        "rho": round(delta_rho, 2)
                    },
                    "vol_shocks": {
                        "1W_ATM": round(vol_shock.delta_1W_ATM, 5),
                        "1M_ATM": round(vol_shock.delta_1M_ATM, 5),
                        "3M_ATM": round(vol_shock.delta_3M_ATM, 5),
                        "6M_ATM": round(vol_shock.delta_6M_ATM, 5),
                        "1Y_ATM": round(vol_shock.delta_1Y_ATM, 5)
                    }
                })
            
            # Sort news by sentiment score (descending - strongest sentiment first)
            impact_results = sorted(impact_results, key=lambda x: x["sentiment_score"], reverse=True)
            
            span.log(f"Processed {len(impact_results)} news for impact analysis")
            
            return {
                "timestamp": datetime.now().isoformat(),
                "count": len(impact_results),
                "baseline_greeks": baseline_greeks.total_greeks.to_dict(),
                "news_impacts": impact_results
            }
        except Exception as e:
            span.log(f"Failed to compute news impact: {e}", level=40)
            logger.error(f"Failed to compute news impact: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ==================== WebSocket for Real-time Updates ====================

@app.websocket("/ws/greeks")
async def websocket_greeks(websocket: WebSocket):
    """WebSocket endpoint for real-time Greeks updates."""
    await manager.connect(websocket)
    
    try:
        while True:
            # Send periodic updates
            await asyncio.sleep(1)  # Update every second
            
            # Compute current risk state
            risk_state = await _compute_current_risk_state()
            await websocket.send_json(risk_state)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def _compute_current_risk_state() -> dict:
    """Compute current risk state for ticking display."""
    portfolio_id = "FX-PORTFOLIO-01"
    
    if portfolio_id not in _portfolios:
        return {"error": "Portfolio not found"}
    
    portfolio = _portfolios[portfolio_id]
    vol_surface = _current_vol_surface or create_mock_surface(datetime.now())
    
    try:
        portfolio_greeks = risk_engine.compute_portfolio_greeks(
            portfolio=portfolio,
            vol_surface=vol_surface,
            spot_rates=_current_spot_rates,
            risk_free_rate=0.05
        )
        
        # Add small random jitter to simulate market movement
        jitter = {k: v + (hash(datetime.now().isoformat()) % 100 - 50) / 100000 
                  for k, v in portfolio_greeks.total_greeks.to_dict().items()}
        
        return {
            "type": "tick",
            "timestamp": datetime.now().isoformat(),
            "portfolio_id": portfolio_id,
            "total_greeks": jitter,
            "spot_rates": _current_spot_rates
        }
    except Exception as e:
        return {"error": str(e)}


# ==================== Maker/Dealer Trade Entry ====================

@app.post("/api/trades")
async def create_trade(
    trade: TradeCreate
):
    """Create a new trade (maker/dealer function)."""
    portfolio_id = trade.portfolio_id
    if portfolio_id not in _portfolios:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    portfolio = _portfolios[portfolio_id]
    
    # Generate new trade ID
    trade_id = f"TRADE-{len(portfolio.positions) + 1:03d}"
    
    # Get spot for instrument
    spot = _current_spot_rates.get(trade.instrument, 1.0)
    
    new_position = PortfolioPosition(
        position_id=trade_id,
        instrument=trade.instrument,
        spot=spot,
        strike=trade.strike,
        tenor=trade.tenor,
        quantity=trade.quantity,
        option_type=trade.option_type.upper(),
        portfolio_id=portfolio_id
    )
    
    portfolio.positions.append(new_position)
    portfolio.timestamp = datetime.now()
    
    # Broadcast update to all connected clients
    await manager.broadcast({
        "type": "trade_added",
        "trade_id": trade_id,
        "instrument": trade.instrument,
        "timestamp": datetime.now().isoformat()
    })
    
    return {
        "status": "success",
        "trade_id": trade_id,
        "position": new_position.model_dump()
    }


@app.delete("/api/trades/{trade_id}")
async def delete_trade(trade_id: str, portfolio_id: str = "FX-PORTFOLIO-01"):
    """Delete a trade from portfolio."""
    if portfolio_id not in _portfolios:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    portfolio = _portfolios[portfolio_id]
    
    original_count = len(portfolio.positions)
    portfolio.positions = [p for p in portfolio.positions if p.position_id != trade_id]
    
    if len(portfolio.positions) == original_count:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    portfolio.timestamp = datetime.now()
    
    # Broadcast update
    await manager.broadcast({
        "type": "trade_removed",
        "trade_id": trade_id,
        "timestamp": datetime.now().isoformat()
    })
    
    return {"status": "success", "trade_id": trade_id}


# ==================== Audit/Traceability Endpoints ====================

@app.get("/api/audit/trace/{trace_id}")
async def get_trace(trace_id: str):
    """
    Get full trace for news-to-Greeks pipeline.
    
    Returns all stages linked by trace_id:
    - News events
    - Event vectors (NLP output)
    - Vol shocks
    - Vol surfaces
    - Greeks snapshots
    """
    from logger import get_tracer
    
    with get_tracer().start_span("audit_get_trace", trace_id=trace_id) as span:
        audit = get_audit_service()
        trace = audit.get_trace(trace_id)
        
        if not trace:
            raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
        
        return trace


@app.get("/api/audit/traces")
async def get_traces(limit: int = 20, status: Optional[str] = None):
    """
    Get recent traces, optionally filtered by status.
    
    Args:
        limit: Maximum number of traces to return
        status: Filter by status ('active', 'completed', 'error')
    """
    audit = get_audit_service()
    
    if status == "active":
        traces = audit.get_active_traces()
    elif status:
        # Filter by status in-memory
        all_traces = audit.get_recent_traces(limit * 2)
        traces = [t for t in all_traces if t.get('status') == status][:limit]
    else:
        traces = audit.get_recent_traces(limit)
    
    return {
        "count": len(traces),
        "traces": traces
    }


@app.post("/api/audit/trace/{trace_id}/end")
async def end_trace(trace_id: str, status: str = "completed"):
    """
    Mark a trace as ended.
    
    Args:
        trace_id: Trace identifier
        status: Final status ('completed', 'error')
    """
    audit = get_audit_service()
    audit.end_trace(trace_id, status)
    return {"status": "success", "trace_id": trace_id, "final_status": status}


# ==================== Main Entry Point ====================

def main():
    """Run the API server."""
    # Initialize audit service
    init_audit_service(":memory:")
    
    uvicorn.run(
        "api:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.debug,
        log_level=config.log_level.lower()
    )


if __name__ == "__main__":
    main()
