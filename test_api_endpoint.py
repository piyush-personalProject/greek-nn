"""
Test script that mimics exactly what the API endpoint does (simplified without tracing).
"""
import sys
sys.path.insert(0, '.')

from datetime import datetime
from fastapi import HTTPException
from services.correlation_service import get_correlation_service
from nn_risk_engine import NNRiskEngine
from vol_surface_service import create_mock_surface
from logger import get_logger, setup_logging

# Setup logging like api.py does
setup_logging()
logger = get_logger(__name__)

# This is the API's _current_spot_rates
_current_spot_rates = {
    "EURUSD": 1.0850,
    "USDJPY": 149.50,
    "GBPUSD": 1.2650,
    "USDCHF": 0.8850,
    "AUDUSD": 0.6550,
    "USDCAD": 1.3450,
    "NZDUSD": 0.6050,
}

# Global risk_engine (like api.py)
risk_engine = None

# Initialize like api.py startup
print("Initializing...")
risk_engine = NNRiskEngine(model_mode="auto")
_current_vol_surface = create_mock_surface(base_date=datetime.now(), base_vol=0.10)

# Create portfolio positions (from api.py _create_demo_portfolio)
from schemas import Portfolio, PortfolioPosition, Greeks

positions = []
for i, (pos_data) in enumerate([
    {
        "position_id": "TRADE-001",
        "instrument": "EURUSD",
        "spot": 1.0850,
        "strike": 1.0900,
        "tenor": 1/12,
        "quantity": 1000000,
        "option_type": "CALL",
    },
    {
        "position_id": "TRADE-002",
        "instrument": "EURUSD",
        "spot": 1.0850,
        "strike": 1.0800,
        "tenor": 3/12,
        "quantity": -500000,
        "option_type": "PUT",
    },
    {
        "position_id": "TRADE-003",
        "instrument": "USDJPY",
        "spot": 149.50,
        "strike": 150.00,
        "tenor": 1/52,
        "quantity": 2000000,
        "option_type": "CALL",
    },
    {
        "position_id": "TRADE-004",
        "instrument": "GBPUSD",
        "spot": 1.2650,
        "strike": 1.2600,
        "tenor": 6/12,
        "quantity": 750000,
        "option_type": "PUT",
    },
    {
        "position_id": "TRADE-005",
        "instrument": "USDJPY",
        "spot": 149.50,
        "strike": 148.00,
        "tenor": 1/12,
        "quantity": -1500000,
        "option_type": "CALL",
    },
]):
    booking_spot_rate = pos_data["spot"]
    
    temp_portfolio = Portfolio(
        portfolio_id="FX-PORTFOLIO-01",
        timestamp=datetime.now(),
        positions=[
            PortfolioPosition(
                position_id=pos_data["position_id"],
                instrument=pos_data["instrument"],
                spot=booking_spot_rate,
                strike=pos_data["strike"],
                tenor=pos_data["tenor"],
                quantity=pos_data["quantity"],
                option_type=pos_data["option_type"],
                portfolio_id="FX-PORTFOLIO-01"
            )
        ],
        base_currency="USD"
    )
    
    initial_greeks = None
    try:
        initial_pg = risk_engine.compute_portfolio_greeks(
            portfolio=temp_portfolio,
            vol_surface=_current_vol_surface,
            spot_rates={pos_data["instrument"]: booking_spot_rate},
            risk_free_rate=0.05
        )
        initial_greeks = initial_pg.position_greeks.get(pos_data["position_id"])
    except Exception as e:
        print(f"Failed to compute initial Greeks for {pos_data['position_id']}: {e}")

    positions.append(PortfolioPosition(
        position_id=pos_data["position_id"],
        instrument=pos_data["instrument"],
        spot=pos_data["spot"],
        strike=pos_data["strike"],
        tenor=pos_data["tenor"],
        quantity=pos_data["quantity"],
        option_type=pos_data["option_type"],
        portfolio_id="FX-PORTFOLIO-01",
        booking_spot_rate=booking_spot_rate,
        booking_vol_surface_version=_current_vol_surface.version if _current_vol_surface else None,
        booking_timestamp=datetime.now(),
        initial_greeks=initial_greeks
    ))

portfolio = Portfolio(
    portfolio_id="FX-PORTFOLIO-01",
    timestamp=datetime.now(),
    positions=positions,
    base_currency="USD"
)

_portfolios = {"FX-PORTFOLIO-01": portfolio}

# Now mimic the API endpoint
portfolio_id = "FX-PORTFOLIO-01"

print("\n=== Mimicking API endpoint /api/correlation-risk-report ===")

try:
    if risk_engine is None:
        raise HTTPException(status_code=503, detail="Risk engine not available")
    
    if portfolio_id not in _portfolios:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    portfolio = _portfolios[portfolio_id]
    vol_surface = _current_vol_surface or create_mock_surface(datetime.now())
    
    print("Step 1: Compute baseline Greeks")
    baseline_greeks = risk_engine.compute_portfolio_greeks(
        portfolio=portfolio,
        vol_surface=vol_surface,
        spot_rates=_current_spot_rates,
        risk_free_rate=0.05
    )
    print(f"  Baseline delta: {baseline_greeks.total_greeks.delta}")
    
    print("Step 2: Get correlation service")
    corr_service = get_correlation_service()
    
    print("Step 3: Generate correlation risk report")
    report = corr_service.generate_correlation_risk_report(
        portfolio_id=portfolio_id,
        positions=portfolio.positions,
        position_greeks=baseline_greeks.position_greeks,
        total_greeks=baseline_greeks.total_greeks
    )
    
    print(f"\n=== SUCCESS ===")
    print(f"Report ID: {report.report_id}")
    print(f"Diversification ratio: {report.diversification_ratio}")
    print(f"Stress tests: {len(report.stress_tests)}")
    
except HTTPException:
    raise
except Exception as e:
    logger.error(f"Failed to generate correlation risk report: {e}")
    print(f"\n=== ERROR ===")
    print(f"{type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    raise HTTPException(status_code=500, detail=str(e))