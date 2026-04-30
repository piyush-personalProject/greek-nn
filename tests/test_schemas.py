# test_schemas.py
"""
Unit tests for Pydantic schemas.
Tests data validation, serialization, and enum values.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from schemas import (
    NewsEvent, EventVector, EventType, Sentiment,
    VolShock, VolSurface, Portfolio, PortfolioPosition,
    Greeks, PortfolioGreeks, RiskAlert, RiskLog,
    ComputeRiskRequest, ComputeRiskResponse, HealthCheck
)


class TestEventType:
    """Tests for EventType enum."""
    
    def test_all_event_types_defined(self):
        """Test that all expected event types exist."""
        assert EventType.INTEREST_RATE.value == "interest_rate"
        assert EventType.INFLATION.value == "inflation"
        assert EventType.EMPLOYMENT.value == "employment"
        assert EventType.CENTRAL_BANK.value == "central_bank"
        assert EventType.MACRO.value == "macro"
        assert EventType.TECHNICAL.value == "technical"
        assert EventType.UNKNOWN.value == "unknown"
    
    def test_event_type_is_string_enum(self):
        """Test EventType is a string enum."""
        assert isinstance(EventType.INTEREST_RATE, str)


class TestSentiment:
    """Tests for Sentiment enum."""
    
    def test_all_sentiments_defined(self):
        """Test that all sentiments exist."""
        assert Sentiment.POSITIVE.value == "positive"
        assert Sentiment.NEUTRAL.value == "neutral"
        assert Sentiment.NEGATIVE.value == "negative"
    
    def test_sentiment_is_string_enum(self):
        """Test Sentiment is a string enum."""
        assert isinstance(Sentiment.POSITIVE, str)


class TestNewsEvent:
    """Tests for NewsEvent schema."""
    
    def test_valid_news_event(self):
        """Test creating a valid NewsEvent."""
        event = NewsEvent(
            headline="Fed raises rates by 25bps",
            source="Bloomberg",
            url="https://bloomberg.com/article/123",
            published_at=datetime.now(),
            content="The Federal Reserve announced..."
        )
        
        assert event.headline == "Fed raises rates by 25bps"
        assert event.source == "Bloomberg"
    
    def test_news_event_with_optional_fields(self):
        """Test NewsEvent with optional importance field."""
        event = NewsEvent(
            headline="Test",
            source="Test",
            url="http://test.com",
            published_at=datetime.now(),
            importance="high"
        )
        
        assert event.importance == "high"
    
    def test_news_event_invalid_url(self):
        """Test that URL validation works (allowing any URL for now)."""
        event = NewsEvent(
            headline="Test",
            source="Test",
            url="not-a-valid-url",  # In production, would validate
            published_at=datetime.now()
        )
        # Currently URL is plain string, no strict validation
        assert event.url == "not-a-valid-url"


class TestEventVector:
    """Tests for EventVector schema."""
    
    def test_valid_event_vector(self):
        """Test creating a valid EventVector."""
        vector = EventVector(
            event_id="evt_001",
            headline="Fed raises rates",
            event_type=EventType.INTEREST_RATE,
            sentiment=Sentiment.NEGATIVE,
            sentiment_score=-0.75,
            importance=0.85,
            surprise_factor=0.6,
            entities={"central_bank": ["Fed"]},
            processed_at=datetime.now(),
            source="NLP"
        )
        
        assert vector.event_id == "evt_001"
        assert vector.event_type == EventType.INTEREST_RATE
        assert vector.sentiment == Sentiment.NEGATIVE
    
    def test_sentiment_score_range(self):
        """Test sentiment score validation (must be -1 to 1)."""
        # Valid range
        vector = EventVector(
            event_id="evt_001",
            headline="Test",
            event_type=EventType.MACRO,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.5,
            importance=0.5,
            surprise_factor=0.5,
            entities={},
            processed_at=datetime.now(),
            source="test"
        )
        assert vector.sentiment_score == 0.5
    
    def test_importance_range(self):
        """Test importance validation (must be 0 to 1)."""
        vector = EventVector(
            event_id="evt_001",
            headline="Test",
            event_type=EventType.MACRO,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.0,
            importance=1.0,
            surprise_factor=0.5,
            entities={},
            processed_at=datetime.now(),
            source="test"
        )
        assert vector.importance == 1.0
    
    def test_surprise_factor_range(self):
        """Test surprise factor validation (must be 0 to 1)."""
        vector = EventVector(
            event_id="evt_001",
            headline="Test",
            event_type=EventType.MACRO,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.0,
            importance=0.5,
            surprise_factor=0.0,
            entities={},
            processed_at=datetime.now(),
            source="test"
        )
        assert vector.surprise_factor == 0.0


class TestVolShock:
    """Tests for VolShock schema."""
    
    def test_valid_vol_shock(self, sample_event_vector):
        """Test creating a valid VolShock."""
        shock = VolShock(
            shock_id="shock_001",
            event_vector=sample_event_vector,
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
        
        assert shock.shock_id == "shock_001"
        assert shock.delta_1M_ATM == 0.03
    
    def test_vol_shock_negative_deltas(self, sample_event_vector):
        """Test that negative deltas are allowed (vol decreases)."""
        shock = VolShock(
            shock_id="shock_002",
            event_vector=sample_event_vector,
            delta_1W_ATM=-0.01,
            delta_1M_ATM=-0.02,
            delta_3M_ATM=-0.015,
            delta_6M_ATM=-0.01,
            delta_1Y_ATM=-0.005,
            delta_1M_25RR=-0.005,
            delta_1M_25BF=-0.002,
            predicted_at=datetime.now(),
            model_version="1.0"
        )
        
        assert shock.delta_1M_ATM < 0


class TestVolSurface:
    """Tests for VolSurface schema."""
    
    def test_vol_surface_requires_arrays(self):
        """Test that VolSurface requires array-like data."""
        import numpy as np
        
        surface = VolSurface(
            snapshot_id="surface_001",
            base_date=datetime.now(),
            tenors=[0.25, 0.5, 1.0],
            strikes=[95, 100, 105],
            volatilities=[[0.15, 0.16, 0.14], [0.14, 0.15, 0.13]],
            source="test",
            version="v1.0"
        )
        
        assert surface.snapshot_id == "surface_001"
        assert len(surface.tenors) == 3
        assert len(surface.volatilities) == 2
        assert len(surface.volatilities[0]) == 3
    
    def test_vol_surface_shape_validation(self):
        """Test that volatilities shape matches tenors x strikes."""
        surface = VolSurface(
            snapshot_id="test",
            base_date=datetime.now(),
            tenors=[0.25, 0.5],  # 2 tenors
            strikes=[95, 100, 105],  # 3 strikes
            volatilities=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            source="test",
            version="v1"
        )
        
        assert len(surface.volatilities) == 2
        assert len(surface.volatilities[0]) == 3


class TestPortfolio:
    """Tests for Portfolio schema."""
    
    def test_valid_portfolio(self):
        """Test creating a valid portfolio."""
        portfolio = Portfolio(
            portfolio_id="PORT-001",
            timestamp=datetime.now(),
            positions=[
                PortfolioPosition(
                    position_id="POS-001",
                    instrument="USD/SGD",
                    spot=1.34,
                    strike=1.35,
                    tenor=0.25,
                    quantity=1000000,
                    option_type="CALL",
                    portfolio_id="PORT-001"
                )
            ],
            base_currency="USD"
        )
        
        assert portfolio.portfolio_id == "PORT-001"
        assert len(portfolio.positions) == 1
    
    def test_portfolio_default_currency(self):
        """Test portfolio default currency is USD."""
        portfolio = Portfolio(
            portfolio_id="PORT-001",
            timestamp=datetime.now(),
            positions=[]
        )
        
        assert portfolio.base_currency == "USD"


class TestPortfolioPosition:
    """Tests for PortfolioPosition schema."""
    
    def test_valid_position(self):
        """Test creating a valid position."""
        position = PortfolioPosition(
            position_id="POS-001",
            instrument="USD/SGD",
            spot=1.34,
            strike=1.35,
            tenor=0.25,
            quantity=1000000,
            option_type="CALL",
            portfolio_id="PORT-001"
        )
        
        assert position.spot > 0
        assert position.strike > 0
        assert position.tenor > 0
    
    def test_position_spot_must_be_positive(self):
        """Test that spot must be greater than 0."""
        with pytest.raises(ValidationError):
            PortfolioPosition(
                position_id="POS-001",
                instrument="USD/SGD",
                spot=-1.0,  # Invalid
                strike=1.35,
                tenor=0.25,
                quantity=1000000,
                option_type="CALL",
                portfolio_id="PORT-001"
            )
    
    def test_position_option_types(self):
        """Test valid option types."""
        call = PortfolioPosition(
            position_id="POS-1",
            instrument="USD/SGD",
            spot=1.34,
            strike=1.35,
            tenor=0.25,
            quantity=1000000,
            option_type="CALL",
            portfolio_id="PORT-001"
        )
        
        put = PortfolioPosition(
            position_id="POS-2",
            instrument="USD/SGD",
            spot=1.34,
            strike=1.35,
            tenor=0.25,
            quantity=1000000,
            option_type="PUT",
            portfolio_id="PORT-001"
        )
        
        assert call.option_type == "CALL"
        assert put.option_type == "PUT"


class TestGreeks:
    """Tests for Greeks schema."""
    
    def test_greeks_creation(self):
        """Test creating Greeks."""
        greeks = Greeks(
            delta=100.0,
            gamma=50.0,
            vega=75.0,
            theta=-10.0,
            rho=25.0
        )
        
        assert greeks.delta == 100.0
        assert greeks.gamma == 50.0
    
    def test_greeks_addition(self):
        """Test adding two Greeks objects."""
        greeks1 = Greeks(delta=100, gamma=50, vega=75, theta=-10, rho=25)
        greeks2 = Greeks(delta=50, gamma=25, vega=30, theta=-5, rho=10)
        
        result = greeks1 + greeks2
        
        assert result.delta == 150
        assert result.gamma == 75
        assert result.vega == 105
    
    def test_greeks_to_dict(self):
        """Test Greeks to_dict method."""
        greeks = Greeks(
            delta=100.0,
            gamma=50.0,
            vega=75.0,
            theta=-10.0,
            rho=25.0,
            vanna=5.0,
            volga=3.0
        )
        
        d = greeks.to_dict()
        
        assert d["delta"] == 100.0
        assert d["vanna"] == 5.0
        assert d["volga"] == 3.0


class TestRiskAlert:
    """Tests for RiskAlert schema."""
    
    def test_valid_risk_alert(self, sample_event_vector):
        """Test creating a valid risk alert."""
        alert = RiskAlert(
            alert_id="alert_001",
            portfolio_id="PORT-001",
            timestamp=datetime.now(),
            risk_type="vega",
            current_value=150000.0,
            limit_value=100000.0,
            exceeded_by=50000.0,
            event=sample_event_vector,
            action_recommended="Reduce vega exposure"
        )
        
        assert alert.risk_type == "vega"
        assert alert.exceeded_by == 50000.0


class TestComputeRiskRequest:
    """Tests for ComputeRiskRequest schema."""
    
    def test_valid_request(self):
        """Test creating a valid risk compute request."""
        request = ComputeRiskRequest(
            portfolio_id="PORT-001",
            positions=[
                PortfolioPosition(
                    position_id="POS-001",
                    instrument="USD/SGD",
                    spot=1.34,
                    strike=1.35,
                    tenor=0.25,
                    quantity=1000000,
                    option_type="CALL",
                    portfolio_id="PORT-001"
                )
            ],
            spot_rates={"USD/SGD": 1.34}
        )
        
        assert request.portfolio_id == "PORT-001"
        assert len(request.positions) == 1
    
    def test_optional_vol_surface_version(self):
        """Test that vol_surface_version is optional."""
        request = ComputeRiskRequest(
            portfolio_id="PORT-001",
            positions=[],
            spot_rates={}
        )
        
        assert request.vol_surface_version is None


class TestComputeRiskResponse:
    """Tests for ComputeRiskResponse schema."""
    
    def test_valid_response(self):
        """Test creating a valid risk compute response."""
        response = ComputeRiskResponse(
            portfolio_id="PORT-001",
            timestamp=datetime.now(),
            greeks=Greeks(delta=100, gamma=50, vega=75, theta=-10, rho=25),
            position_greeks={},
            computation_time_ms=45.2
        )
        
        assert response.computation_time_ms == 45.2


class TestHealthCheck:
    """Tests for HealthCheck schema."""
    
    def test_valid_health_check(self):
        """Test creating a valid health check response."""
        health = HealthCheck(
            status="healthy",
            timestamp=datetime.now(),
            components={
                "nn_risk_engine": "healthy",
                "vol_surface_service": "healthy"
            }
        )
        
        assert health.status == "healthy"
        assert len(health.components) == 2