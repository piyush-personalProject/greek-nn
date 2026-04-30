# conftest.py
"""
Pytest configuration and fixtures for GreekNN Risk System tests.
"""
import pytest
import numpy as np
from datetime import datetime
from typing import Dict, List

from schemas import (
    Portfolio, PortfolioPosition, VolSurface, NewsEvent,
    EventVector, EventType, Sentiment, Greeks, VolShock
)
from config import AppConfig, DatabaseConfig, RedisConfig, MLConfig, RiskLimits


@pytest.fixture
def sample_portfolio() -> Portfolio:
    """Creates a sample portfolio for testing."""
    return Portfolio(
        portfolio_id="TEST-PORT-001",
        timestamp=datetime.now(),
        positions=[
            PortfolioPosition(
                position_id="POS-001",
                instrument="USD/SGD",
                spot=1.3400,
                strike=1.3500,
                tenor=0.25,
                quantity=1000000,
                option_type="CALL",
                portfolio_id="TEST-PORT-001"
            ),
            PortfolioPosition(
                position_id="POS-002",
                instrument="USD/SGD",
                spot=1.3400,
                strike=1.3300,
                tenor=0.5,
                quantity=500000,
                option_type="PUT",
                portfolio_id="TEST-PORT-001"
            )
        ],
        base_currency="USD"
    )


@pytest.fixture
def single_position_portfolio() -> Portfolio:
    """Creates a portfolio with a single position."""
    return Portfolio(
        portfolio_id="TEST-PORT-SINGLE",
        timestamp=datetime.now(),
        positions=[
            PortfolioPosition(
                position_id="POS-SINGLE",
                instrument="EUR/USD",
                spot=1.0800,
                strike=1.0850,
                tenor=0.0833,  # ~1 month
                quantity=2000000,
                option_type="CALL",
                portfolio_id="TEST-PORT-SINGLE"
            )
        ],
        base_currency="USD"
    )


@pytest.fixture
def mock_vol_surface() -> VolSurface:
    """Creates a mock volatility surface."""
    tenors = [0.0192, 0.0833, 0.25, 0.5, 1.0]  # 1W, 1M, 3M, 6M, 1Y
    strikes = [100, 102.5, 97.5, 105, 95]  # ATM, 25RR+, 25RR-, 25BF+, 25BF-
    
    # Create a typical vol surface with term structure
    vols = np.array([
        [0.16, 0.17, 0.15, 0.18, 0.14],  # 1W
        [0.15, 0.16, 0.14, 0.17, 0.13],  # 1M
        [0.13, 0.14, 0.12, 0.15, 0.11],  # 3M
        [0.12, 0.13, 0.11, 0.14, 0.10],  # 6M
        [0.11, 0.12, 0.10, 0.13, 0.09],  # 1Y
    ])
    
    return VolSurface(
        snapshot_id="mock_surface_2024",
        base_date=datetime.now(),
        tenors=tenors,
        strikes=strikes,
        volatilities=vols,
        source="mock",
        version="test_v1.0"
    )


@pytest.fixture
def sample_news_event() -> NewsEvent:
    """Creates a sample news event."""
    return NewsEvent(
        headline="Fed signals potential rate cut in Q2",
        source="Bloomberg",
        url="https://example.com/news/123",
        published_at=datetime.now(),
        content="The Federal Reserve indicated that interest rates may be reduced in the second quarter..."
    )


@pytest.fixture
def sample_event_vector() -> EventVector:
    """Creates a sample event vector from NLP processing."""
    return EventVector(
        event_id="evt_001",
        headline="Fed signals potential rate cut in Q2",
        event_type=EventType.INTEREST_RATE,
        sentiment=Sentiment.POSITIVE,
        sentiment_score=0.65,
        importance=0.75,
        surprise_factor=0.45,
        entities={"central_bank": ["Fed"], "currency": ["USD"]},
        processed_at=datetime.now(),
        source="NLP"
    )


@pytest.fixture
def sample_vol_shock() -> VolShock:
    """Creates a sample volatility shock."""
    return VolShock(
        shock_id="shock_001",
        event_vector=EventVector(
            event_id="evt_001",
            headline="Fed signals potential rate cut in Q2",
            event_type=EventType.INTEREST_RATE,
            sentiment=Sentiment.POSITIVE,
            sentiment_score=0.65,
            importance=0.75,
            surprise_factor=0.45,
            entities={"central_bank": ["Fed"]},
            processed_at=datetime.now(),
            source="NLP"
        ),
        delta_1W_ATM=0.02,
        delta_1M_ATM=0.03,
        delta_3M_ATM=0.025,
        delta_6M_ATM=0.02,
        delta_1Y_ATM=0.015,
        delta_1M_25RR=0.01,
        delta_1M_25BF=0.005,
        predicted_at=datetime.now(),
        model_version="1.0"
    )


@pytest.fixture
def spot_rates() -> Dict[str, float]:
    """Provides typical spot rates for testing."""
    return {
        "USD/SGD": 1.3400,
        "EUR/USD": 1.0800,
        "USD/JPY": 148.50,
        "GBP/USD": 1.2650
    }


@pytest.fixture
def risk_limits() -> RiskLimits:
    """Provides default risk limits for testing."""
    return RiskLimits(
        vega_limit=100000.0,
        gamma_limit=50000.0,
        delta_limit=500000.0,
        rho_limit=100000.0,
        shock_threshold=0.01
    )


@pytest.fixture
def app_config() -> AppConfig:
    """Provides application configuration for testing."""
    return AppConfig(
        environment="testing",
        debug=True,
        log_level="DEBUG"
    )


@pytest.fixture
def mock_redis():
    """Provides a mock Redis client."""
    class MockRedis:
        def __init__(self):
            self._data = {}
        
        def get(self, key):
            return self._data.get(key)
        
        def setex(self, key, ttl, value):
            self._data[key] = value
        
        def ping(self):
            return True
    
    return MockRedis()