#!/usr/bin/env python
"""Debug script to test Greeks computation."""

import sys
sys.path.insert(0, '.')

from datetime import datetime
from schemas import Portfolio, PortfolioPosition, Greeks, VolSurface
from nn_risk_engine import NNRiskEngine
from vol_surface_service import create_mock_surface

print("Starting debug test...")

vol_surface = create_mock_surface(datetime.now(), base_vol=0.10)
print(f"Vol Surface Tenors: {vol_surface.tenors}")

# Create single position
pos = PortfolioPosition(
    position_id='TEST-001',
    instrument='EURUSD',
    spot=1.0850,
    strike=1.0900,
    tenor=1/12,
    quantity=1000000,
    option_type='CALL',
    portfolio_id='TEST'
)

portfolio = Portfolio(
    portfolio_id='TEST',
    timestamp=datetime.now(),
    positions=[pos],
    base_currency='USD'
)

print("Creating risk engine...")
engine = NNRiskEngine(model_mode='blackscholes')
print(f"Engine mode: {engine.model_mode}")

print("Computing portfolio greeks...")
pg = engine.compute_portfolio_greeks(portfolio, vol_surface, {'EURUSD': 1.0850}, risk_free_rate=0.05)

print(f"Position IDs in result: {list(pg.position_greeks.keys())}")

if 'TEST-001' in pg.position_greeks:
    g = pg.position_greeks['TEST-001']
    print(f"Position Greeks for TEST-001:")
    print(f"  delta={g.delta}")
    print(f"  gamma={g.gamma}")
    print(f"  vega={g.vega}")
else:
    print("TEST-001 not found in position_greeks!")

print(f"Total Greeks: delta={pg.total_greeks.delta}")