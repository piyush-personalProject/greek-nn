# tests/conftest.py
"""
Pytest configuration and fixtures for GreekNN Risk System tests.

This module provides comprehensive test fixtures for unit and integration testing
across all system components.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from unittest.mock import Mock, AsyncMock, patch
import asyncio

from schemas import (
    Portfolio, PortfolioPosition, VolSurface, NewsEvent,
    EventVector, EventType, Sentiment, Greeks, VolShock,
    SpotRate, SpotRateResponse, GreeksImpactWeights
)
from config import AppConfig, DatabaseConfig, RedisConfig, MLConfig, RiskLimits


# ==================== Portfolio Fixtures ====================

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
def multi_position_portfolio() -> Portfolio:
    """Creates a portfolio with multiple positions across different pairs."""
    return Portfolio(
        portfolio_id="TEST-PORT-MULTI",
        timestamp=datetime.now(),
        positions=[
            PortfolioPosition(
                position_id="POS-EUR-001",
                instrument="EURUSD",
                spot=1.0850,
                strike=1.0900,
                tenor=1/12,  # 1M
                quantity=1000000,
                option_type="CALL",
                portfolio_id="TEST-PORT-MULTI"
            ),
            PortfolioPosition(
                position_id="POS-EUR-002",
                instrument="EURUSD",
                spot=1.0850,
                strike=1.0800,
                tenor=3/12,  # 3M
                quantity=-500000,
                option_type="PUT",
                portfolio_id="TEST-PORT-MULTI"
            ),
            PortfolioPosition(
                position_id="POS-JPY-001",
                instrument="USDJPY",
                spot=149.50,
                strike=150.00,
                tenor=1/52,  # 1W
                quantity=2000000,
                option_type="CALL",
                portfolio_id="TEST-PORT-MULTI"
            ),
            PortfolioPosition(
                position_id="POS-GBP-001",
                instrument="GBPUSD",
                spot=1.2650,
                strike=1.2600,
                tenor=6/12,  # 6M
                quantity=750000,
                option_type="PUT",
                portfolio_id="TEST-PORT-MULTI"
            ),
        ],
        base_currency="USD"
    )


@pytest.fixture
def empty_portfolio() -> Portfolio:
    """Creates an empty portfolio."""
    return Portfolio(
        portfolio_id="TEST-PORT-EMPTY",
        timestamp=datetime.now(),
        positions=[],
        base_currency="USD"
    )


# ==================== Vol Surface Fixtures ====================

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
def mock_vol_surface_list() -> VolSurface:
    """
    Creates a mock volatility surface with Python List[List[float]] volatilities.
    This mimics what the actual API creates, which uses lists not numpy arrays.
    """
    tenors = [0.0192, 0.0833, 0.25, 0.5, 1.0]  # 1W, 1M, 3M, 6M, 1Y
    strikes = [100, 102.5, 97.5, 105, 95]  # ATM, 25RR+, 25RR-, 25BF+, 25BF-
    
    # Use Python list, not numpy array - this is the key difference
    volatilities = [
        [0.16, 0.17, 0.15, 0.18, 0.14],  # 1W
        [0.15, 0.16, 0.14, 0.17, 0.13],  # 1M
        [0.13, 0.14, 0.12, 0.15, 0.11],  # 3M
        [0.12, 0.13, 0.11, 0.14, 0.10],  # 6M
        [0.11, 0.12, 0.10, 0.13, 0.09],  # 1Y
    ]
    
    return VolSurface(
        snapshot_id="mock_surface_list_2024",
        base_date=datetime.now(),
        tenors=tenors,
        strikes=strikes,
        volatilities=volatilities,  # List[List[float]], not np.array
        source="mock_list",
        version="test_v1.0"
    )


@pytest.fixture
def high_vol_surface() -> VolSurface:
    """Creates a high volatility surface for stress testing."""
    tenors = [0.0192, 0.0833, 0.25, 0.5, 1.0]
    strikes = [100, 102.5, 97.5, 105, 95]
    
    vols = np.array([
        [0.25, 0.27, 0.23, 0.28, 0.21],  # High vol 1W
        [0.22, 0.24, 0.20, 0.25, 0.18],  # High vol 1M
        [0.20, 0.22, 0.18, 0.23, 0.16],  # High vol 3M
        [0.18, 0.20, 0.16, 0.21, 0.14],  # High vol 6M
        [0.16, 0.18, 0.14, 0.19, 0.12],  # High vol 1Y
    ])
    
    return VolSurface(
        snapshot_id="high_vol_surface",
        base_date=datetime.now(),
        tenors=tenors,
        strikes=strikes,
        volatilities=vols,
        source="mock",
        version="high_vol_v1"
    )


# ==================== News Fixtures ====================

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
def sample_news_event_negative() -> NewsEvent:
    """Creates a negative sentiment news event."""
    return NewsEvent(
        headline="Fed raises interest rates by 50 basis points",
        source="Reuters",
        url="https://reuters.com/markets/fed-raises-rates",
        published_at=datetime.now(),
        content="The Federal Reserve raised interest rates by 50 basis points to combat inflation..."
    )


@pytest.fixture
def sample_news_event_central_bank() -> NewsEvent:
    """Creates a central bank news event."""
    return NewsEvent(
        headline="ECB surprises markets with hawkish stance",
        source="Financial Times",
        url="https://ft.com/markets/ecb-hawkish",
        published_at=datetime.now(),
        content="European Central Bank policymakers surprised markets with their hawkish stance..."
    )


@pytest.fixture
def news_event_list() -> List[NewsEvent]:
    """Creates a list of multiple news events."""
    base_time = datetime.now()
    return [
        NewsEvent(
            headline=f"Market update {i}",
            source=["Bloomberg", "Reuters", "FT"][i % 3],
            url=f"https://example.com/news/{i}",
            published_at=base_time - timedelta(hours=i),
            content=f"Market content {i}..."
        )
        for i in range(5)
    ]


# ==================== Event Vector Fixtures ====================

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
def negative_event_vector() -> EventVector:
    """Creates a negative sentiment event vector."""
    return EventVector(
        event_id="evt_002",
        headline="Fed raises interest rates by 50 basis points",
        event_type=EventType.INTEREST_RATE,
        sentiment=Sentiment.NEGATIVE,
        sentiment_score=-0.73,
        importance=0.85,
        surprise_factor=0.60,
        entities={"central_bank": ["Fed"], "currency": ["USD"]},
        processed_at=datetime.now(),
        source="NLP"
    )


# ==================== Vol Shock Fixtures ====================

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
def large_vol_shock() -> VolShock:
    """Creates a large volatility shock for stress testing."""
    return VolShock(
        shock_id="shock_large",
        event_vector=EventVector(
            event_id="evt_large",
            headline="Major market crash",
            event_type=EventType.MACRO,
            sentiment=Sentiment.NEGATIVE,
            sentiment_score=-0.95,
            importance=0.99,
            surprise_factor=0.90,
            entities={},
            processed_at=datetime.now(),
            source="NLP"
        ),
        delta_1W_ATM=0.15,
        delta_1M_ATM=0.12,
        delta_3M_ATM=0.10,
        delta_6M_ATM=0.08,
        delta_1Y_ATM=0.06,
        delta_1M_25RR=0.05,
        delta_1M_25BF=0.03,
        predicted_at=datetime.now(),
        model_version="1.0"
    )


# ==================== Greeks Fixtures ====================

@pytest.fixture
def sample_greeks() -> Greeks:
    """Creates sample Greeks values."""
    return Greeks(
        delta=450000.0,
        gamma=12000.0,
        vega=85000.0,
        theta=-1500.0,
        rho=32000.0,
        vanna=5000.0,
        volga=3000.0
    )


@pytest.fixture
def zero_greeks() -> Greeks:
    """Creates zero Greeks values."""
    return Greeks(
        delta=0.0,
        gamma=0.0,
        vega=0.0,
        theta=0.0,
        rho=0.0,
        vanna=None,
        volga=None
    )


# ==================== Spot Rate Fixtures ====================

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
def spot_rates_eurusd() -> Dict[str, float]:
    """Provides EURUSD spot rates."""
    return {
        "EURUSD": 1.0850,
        "USDJPY": 149.50,
        "GBPUSD": 1.2650,
        "USDCHF": 0.8850,
    }


# ==================== Configuration Fixtures ====================

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
def app_config_production() -> AppConfig:
    """Provides production-like configuration."""
    return AppConfig(
        environment="production",
        debug=False,
        log_level="WARNING"
    )


# ==================== Mock Fixtures ====================

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
        
        def keys(self, pattern):
            import fnmatch
            return [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern)]
    
    return MockRedis()


@pytest.fixture
def mock_http_client():
    """Provides a mock HTTP client for external API calls."""
    mock = Mock()
    mock.get = AsyncMock()
    mock.post = AsyncMock()
    mock.put = AsyncMock()
    mock.delete = AsyncMock()
    return mock


# ==================== Greeks Impact Weights Fixtures ====================

@pytest.fixture
def default_weights() -> GreeksImpactWeights:
    """Provides default Greeks impact weights."""
    return GreeksImpactWeights(
        spot_rate_weight=0.0,
        vol_shock_weight=1.0,
        spot_shock_weight=0.0
    )


@pytest.fixture
def blended_weights() -> GreeksImpactWeights:
    """Provides blended Greeks impact weights."""
    return GreeksImpactWeights(
        spot_rate_weight=0.3,
        vol_shock_weight=0.5,
        spot_shock_weight=0.2
    )


# ==================== Async Fixtures ====================

@pytest.fixture
def event_loop():
    """Creates an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==================== Helper Functions ====================

def create_test_portfolio(
    portfolio_id: str = "TEST-001",
    positions: Optional[List[PortfolioPosition]] = None
) -> Portfolio:
    """Helper to create test portfolios."""
    return Portfolio(
        portfolio_id=portfolio_id,
        timestamp=datetime.now(),
        positions=positions or [],
        base_currency="USD"
    )


def create_test_position(
    position_id: str = "POS-001",
    instrument: str = "EURUSD",
    spot: float = 1.0850,
    strike: float = 1.0900,
    tenor: float = 1/12,
    quantity: float = 1000000,
    option_type: str = "CALL",
    portfolio_id: str = "TEST-001"
) -> PortfolioPosition:
    """Helper to create test positions."""
    return PortfolioPosition(
        position_id=position_id,
        instrument=instrument,
        spot=spot,
        strike=strike,
        tenor=tenor,
        quantity=quantity,
        option_type=option_type,
        portfolio_id=portfolio_id
    )


def create_test_vol_surface(
    snapshot_id: str = "TEST-SURFACE",
    version: str = "v1",
    base_vol: float = 0.10
) -> VolSurface:
    """Helper to create test vol surfaces."""
    tenors = [0.0192, 0.0833, 0.25, 0.5, 1.0]
    strikes = [100, 102.5, 97.5, 105, 95]
    
    vols = np.array([
        [base_vol + 0.02, base_vol + 0.03, base_vol + 0.01, base_vol + 0.04, base_vol],
        [base_vol + 0.01, base_vol + 0.02, base_vol, base_vol + 0.03, base_vol - 0.01],
        [base_vol - 0.01, base_vol, base_vol - 0.02, base_vol + 0.01, base_vol - 0.03],
        [base_vol - 0.02, base_vol - 0.01, base_vol - 0.03, base_vol, base_vol - 0.04],
        [base_vol - 0.03, base_vol - 0.02, base_vol - 0.04, base_vol - 0.01, base_vol - 0.05],
    ])
    
    return VolSurface(
        snapshot_id=snapshot_id,
        base_date=datetime.now(),
        tenors=tenors,
        strikes=strikes,
        volatilities=vols,
        source="test",
        version=version
    )