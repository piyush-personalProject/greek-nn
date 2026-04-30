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

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import config
from schemas import (
    Portfolio, PortfolioPosition, Greeks, PortfolioGreeks, VolSurface,
    ComputeRiskRequest, ComputeRiskResponse, RiskAlert, TradeCreate,
    NewsEvent, EventVector
)
from nn_risk_engine import NNRiskEngine, BlackScholesGreeksCPU
from vol_surface_service import VolSurfaceService, create_mock_surface
from nlp_engine import NLPEngine
from vol_shock_model import VolShockModel
from news_ingestion import NewsIngestionService
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
    global risk_engine, vol_surface_service, nlp_engine, vol_shock_model, news_service, _current_vol_surface
    
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
            device="cpu"
        )
        logger.info(f"Vol Shock Model initialized in {vol_shock_model.model_mode} mode")
    
    # Initialize News Ingestion Service (Module 1)
    if config.enable_news_ingestion:
        news_service = NewsIngestionService()
        logger.info("News Ingestion Service initialized")
    
    # Create mock vol surface for demo
    _current_vol_surface = create_mock_surface(
        base_date=datetime.now(),
        base_vol=0.10
    )
    
    # Create demo portfolio
    _create_demo_portfolio()
    
    logger.info("FX Greeks Risk API initialized successfully")


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
            vol_shock_model = VolShockModel()
        
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
            
            for h in headlines:
                # Process through NLP
                event_vector = nlp_engine.process_news_event(h)
                
                # Predict vol shock
                vol_shock = vol_shock_model.predict_shock(event_vector)
                
                # Get shocked surface
                shocked_surface, shocked_version = vol_surface_service.get_shocked_surface(baseline_surface, vol_shock)
                
                # Compute new Greeks
                shocked_greeks = risk_engine.compute_portfolio_greeks(
                    portfolio=portfolio,
                    vol_surface=shocked_surface,
                    spot_rates=_current_spot_rates,
                    risk_free_rate=0.05
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


# ==================== Main Entry Point ====================

def main():
    """Run the API server."""
    uvicorn.run(
        "api:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.debug,
        log_level=config.log_level.lower()
    )


if __name__ == "__main__":
    main()
