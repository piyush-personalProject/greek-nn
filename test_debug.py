import sys
sys.path.insert(0, '.')
from datetime import datetime
from vol_surface_service import create_mock_surface
from nn_risk_engine import NNRiskEngine
from schemas import Portfolio, PortfolioPosition

positions = [PortfolioPosition(
    position_id='TRADE-001', 
    instrument='EURUSD', 
    spot=1.0850, 
    strike=1.0900, 
    tenor=1/12, 
    quantity=1000000, 
    option_type='CALL', 
    portfolio_id='FX-PORTFOLIO-01'
)]

portfolio = Portfolio(
    portfolio_id='FX-PORTFOLIO-01', 
    timestamp=datetime.now(), 
    positions=positions, 
    base_currency='USD'
)
surface = create_mock_surface(datetime.now(), base_vol=0.10)
spot_rates = {'EURUSD': 1.085}

engine = NNRiskEngine()
result = engine.compute_portfolio_greeks(
    portfolio=portfolio, 
    vol_surface=surface, 
    spot_rates=spot_rates, 
    risk_free_rate=0.05
)

print('Type:', type(result.total_greeks))
print('Delta:', result.total_greeks.delta)
print('Is dict:', isinstance(result.total_greeks, dict))