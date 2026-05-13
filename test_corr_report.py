import sys
from services.correlation_service import get_correlation_service
from schemas import Greeks, PortfolioPosition
from datetime import datetime

corr_service = get_correlation_service()

positions = [
    PortfolioPosition(
        position_id='TEST-001',
        instrument='EURUSD',
        spot=1.0850,
        strike=1.0900,
        tenor=0.0833,
        quantity=1000000,
        option_type='CALL',
        portfolio_id='TEST'
    )
]

position_greeks = {
    'TEST-001': Greeks(delta=100, gamma=0.5, vega=50, theta=-10, rho=5)
}

total_greeks = Greeks(delta=100, gamma=0.5, vega=50, theta=-10, rho=5)

print('Starting report generation...', flush=True)
sys.stdout.flush()

try:
    report = corr_service.generate_correlation_risk_report(
        portfolio_id='TEST',
        positions=positions,
        position_greeks=position_greeks,
        total_greeks=total_greeks
    )
    print(f'Report: {report.report_id}', flush=True)
    print(f'Stress tests: {len(report.stress_tests)}', flush=True)
    print(f'Diversification ratio: {report.diversification_ratio}', flush=True)
    for st in report.stress_tests:
        print(f'  - {st.scenario.scenario_id}: {st.scenario.name}', flush=True)
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}', flush=True)
    import traceback
    traceback.print_exc()