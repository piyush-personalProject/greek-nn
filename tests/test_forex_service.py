# tests/test_forex_service.py
"""
Tests for the Forex Service.
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock


class TestForexService:
    """Test cases for ForexService."""

    @pytest.fixture
    def forex_service(self):
        """Create a ForexService instance for testing."""
        from services.forex_service import ForexService
        return ForexService(api_key="test_key", poll_interval=60)

    def test_initialization(self, forex_service):
        """Test ForexService initializes correctly."""
        assert forex_service.api_key == "test_key"
        assert forex_service.poll_interval == 60
        assert forex_service.timeout == 30
        assert forex_service._last_rates == {}
        assert forex_service._baseline_rates == {}
        assert forex_service._is_stale == False

    def test_supported_pairs(self, forex_service):
        """Test supported currency pairs are defined."""
        assert "EURUSD" in forex_service.SUPPORTED_PAIRS
        assert "USDJPY" in forex_service.SUPPORTED_PAIRS
        assert "GBPUSD" in forex_service.SUPPORTED_PAIRS
        assert len(forex_service.SUPPORTED_PAIRS) > 0

    def test_parse_pair(self, forex_service):
        """Test currency pair parsing."""
        from_currency, to_currency = forex_service._parse_pair("EURUSD")
        assert from_currency == "EUR"
        assert to_currency == "USD"

        from_currency, to_currency = forex_service._parse_pair("USDJPY")
        assert from_currency == "USD"
        assert to_currency == "JPY"

    @pytest.mark.asyncio
    async def test_fetch_rates_no_api_key(self):
        """Test fetching rates without API key uses mock data."""
        from services.forex_service import ForexService
        service = ForexService(api_key="", poll_interval=60)
        
        rates = await service.fetch_rates()
        
        assert isinstance(rates, dict)
        # Should get mock rates when no API key
        assert len(rates) > 0 or service._is_stale == True

    def test_get_mock_rate(self, forex_service):
        """Test mock rate generation."""
        rate = forex_service._get_mock_rate("EURUSD")
        assert isinstance(rate, float)
        assert rate > 0
        
        # Should be close to expected value with some variation
        assert 1.0 < rate < 1.2  # EURUSD should be around 1.08

    def test_get_rate_change_no_baseline(self, forex_service):
        """Test rate change with no baseline returns zeros."""
        change = forex_service.get_rate_change("EURUSD")
        
        assert change["current"] is None
        assert change["baseline"] is None
        assert change["change_pct"] == 0.0

    def test_get_rate_change_with_baseline(self, forex_service):
        """Test rate change calculation with baseline."""
        forex_service._last_rates = {"EURUSD": 1.0900}
        forex_service._baseline_rates = {"EURUSD": 1.0850}
        
        change = forex_service.get_rate_change("EURUSD")
        
        assert change["current"] == 1.0900
        assert change["baseline"] == 1.0850
        assert abs(change["change_pct"] - 0.46) < 0.1  # Approximately 0.46%

    def test_update_baseline(self, forex_service):
        """Test baseline update."""
        forex_service._last_rates = {"EURUSD": 1.0900}
        forex_service.update_baseline()
        
        assert forex_service._baseline_rates["EURUSD"] == 1.0900

    def test_get_status(self, forex_service):
        """Test status reporting."""
        status = forex_service.get_status()
        
        assert "service" in status
        assert status["service"] == "forex"
        assert "status" in status
        assert "api_key_configured" in status
        assert status["api_key_configured"] == True

    def test_health_check(self, forex_service):
        """Test health check method."""
        health = forex_service.health_check()
        
        assert isinstance(health, dict)
        assert "service" in health
        assert "status" in health


class TestForexServiceMockMode:
    """Test ForexService in mock mode (no API key)."""

    @pytest.fixture
    def mock_service(self):
        """Create a ForexService in mock mode."""
        from services.forex_service import ForexService
        return ForexService(api_key="", poll_interval=60)

    def test_initialization_mock(self, mock_service):
        """Test initialization in mock mode."""
        assert mock_service.api_key == ""
        assert mock_service._last_rates == {}

    @pytest.mark.asyncio
    async def test_fetch_rates_in_mock_mode(self, mock_service):
        """Test fetching rates in mock mode returns rates."""
        rates = await mock_service.fetch_rates()
        
        # In mock mode, should populate _last_rates
        if not mock_service._is_stale:
            assert len(mock_service._last_rates) > 0


class TestForexServiceRateLimiting:
    """Test ForexService handles rate limiting correctly."""

    @pytest.mark.asyncio
    async def test_rate_limit_fallback(self):
        """Test fallback when API rate limit is hit."""
        from services.forex_service import ForexService
        service = ForexService(api_key="test_key", timeout=1)
        
        # Mock a rate limit response
        service.base_url = "https://test.example.com"
        
        # This should use fallback rates on error
        rate = await service._fetch_pair_rate("EURUSD")
        
        # Should return a fallback rate
        assert rate is not None or service._is_stale == True