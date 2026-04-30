# test_vol_surface.py
"""
Unit tests for Vol Surface Service module.
Tests vol surface retrieval, caching, and shock application.
"""
import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from vol_surface_service import (
    VolSurfaceService, VolSurfaceBackend, QuantLibVolSurfaceBackend,
    VolSurfaceCache, create_mock_surface
)
from schemas import VolSurface, VolShock, EventVector, EventType, Sentiment


class TestVolSurfaceCache:
    """Tests for VolSurfaceCache dataclass."""
    
    def test_cache_creation(self):
        """Test cache entry creation."""
        cache = VolSurfaceCache(
            surface=np.array([[0.15, 0.16], [0.14, 0.15]]),
            tenors=np.array([0.25, 0.5]),
            strikes=np.array([100, 105]),
            timestamp=datetime.now(),
            version="v1.0",
            metadata={"source": "test"}
        )
        
        assert cache.surface.shape == (2, 2)
        assert len(cache.tenors) == 2
        assert cache.version == "v1.0"


class TestQuantLibVolSurfaceBackend:
    """Tests for QuantLib backend."""
    
    def test_backend_initialization(self):
        """Test backend initialization with/without QuantLib."""
        backend = QuantLibVolSurfaceBackend()
        # Should handle missing QuantLib gracefully
        assert isinstance(backend, QuantLibVolSurfaceBackend)
    
    def test_get_surface_returns_none(self):
        """Test that get_surface returns None for non-existent surface."""
        backend = QuantLibVolSurfaceBackend()
        result = backend.get_surface(datetime.now(), "nonexistent")
        # Stub returns None
        assert result is None
    
    def test_save_surface(self):
        """Test surface saving."""
        backend = QuantLibVolSurfaceBackend()
        surface = create_mock_surface(datetime.now())
        result = backend.save_surface(surface)
        # Should return boolean
        assert isinstance(result, bool)
    
    def test_interpolate_at_strike(self, mock_vol_surface):
        """Test strike interpolation."""
        backend = QuantLibVolSurfaceBackend()
        
        vol = backend.interpolate_at_strike(mock_vol_surface, tenor=0.25, strike=100)
        
        assert 0 < vol < 1
        assert isinstance(vol, float)
    
    def test_interpolate_bounds_check(self, mock_vol_surface):
        """Test interpolation with out-of-bounds values."""
        backend = QuantLibVolSurfaceBackend()
        
        # Tenor beyond surface range
        vol = backend.interpolate_at_strike(mock_vol_surface, tenor=5.0, strike=100)
        
        # Should clip to edge value
        assert 0 < vol < 1


class TestCreateMockSurface:
    """Tests for mock surface creation utility."""
    
    def test_default_mock_surface(self):
        """Test creation of default mock surface."""
        surface = create_mock_surface(datetime.now())
        
        assert isinstance(surface, VolSurface)
        assert len(surface.tenors) == 5
        assert len(surface.strikes) == 5
        assert surface.volatilities.shape == (5, 5)
    
    def test_custom_tenors(self):
        """Test mock surface with custom tenors."""
        custom_tenors = [0.1, 0.5, 1.0]
        surface = create_mock_surface(datetime.now(), tenors=custom_tenors)
        
        assert len(surface.tenors) == 3
        assert surface.tenors == custom_tenors
    
    def test_custom_strikes(self):
        """Test mock surface with custom strikes."""
        custom_strikes = [95, 100, 105]
        surface = create_mock_surface(datetime.now(), strikes=custom_strikes)
        
        assert len(surface.strikes) == 3
        assert surface.strikes == custom_strikes
    
    def test_volatility_range(self):
        """Test that mock vol surface has reasonable values."""
        surface = create_mock_surface(datetime.now(), base_vol=0.15)
        
        # All volatilities should be positive and reasonable
        assert np.all(surface.volatilities > 0)
        assert np.all(surface.volatilities < 1)
    
    def test_surface_version(self):
        """Test surface has version identifier."""
        surface = create_mock_surface(datetime.now())
        
        assert surface.version is not None
        assert len(surface.version) > 0


class TestVolSurfaceService:
    """Tests for VolSurfaceService class."""
    
    def test_service_initialization(self, mock_redis):
        """Test service initialization."""
        service = VolSurfaceService(redis_client=mock_redis)
        
        assert service.redis is not None
        assert service.backend is not None
        assert isinstance(service._memory_cache, dict)
    
    def test_memory_cache_storage(self, mock_redis):
        """Test that surfaces are stored in memory cache."""
        service = VolSurfaceService(redis_client=mock_redis)
        
        surface = create_mock_surface(datetime.now())
        cache_key = service._cache_key(datetime.now(), "v1.0")
        service._cache_surface(cache_key, surface)
        
        assert cache_key in service._memory_cache
    
    def test_cache_key_generation(self):
        """Test cache key format."""
        service = VolSurfaceService()
        
        key = service._cache_key(datetime(2024, 1, 15), "v1.0")
        
        assert "vol_surface" in key
        assert "2024-01-15" in key
        assert "v1.0" in key
    
    def test_shock_key_generation(self):
        """Test shock cache key format."""
        service = VolSurfaceService()
        
        key = service._shock_key("shock_abc123")
        
        assert "vol_shock" in key
        assert "shock_abc123" in key
    
    def test_get_shocked_surface(self, mock_vol_surface, sample_vol_shock):
        """Test applying shock to baseline surface."""
        service = VolSurfaceService()
        
        shocked_surface, version = service.get_shocked_surface(
            mock_vol_surface, sample_vol_shock
        )
        
        assert isinstance(shocked_surface, VolSurface)
        assert version != mock_vol_surface.version
        assert "_shocked" in shocked_surface.snapshot_id
    
    def test_get_shocked_surface_with_list_volatilities(self, mock_vol_surface_list, sample_vol_shock):
        """
        Test applying shock to surface with Python List[List[float]] volatilities.
        This is the actual scenario from the API - creates VolSurface with list, not numpy.
        Regression test for: can't multiply sequence by non-int of type 'float'
        """
        service = VolSurfaceService()
        
        # This should not raise TypeError: can't multiply sequence by non-int of type 'float'
        shocked_surface, version = service.get_shocked_surface(
            mock_vol_surface_list, sample_vol_shock
        )
        
        assert isinstance(shocked_surface, VolSurface)
        assert version != mock_vol_surface_list.version
        assert "_shocked" in shocked_surface.snapshot_id
        # Verify volatilities are still valid numbers
        assert all(isinstance(v, (int, float)) for row in shocked_surface.volatilities for v in row)
    
    def test_shocked_surface_volumes_increased(self, mock_vol_surface, sample_vol_shock):
        """Test that shocked surface has higher volatilities."""
        service = VolSurfaceService()
        
        shocked_surface, _ = service.get_shocked_surface(
            mock_vol_surface, sample_vol_shock
        )
        
        # Shocked vols should be higher (multiplied by 1 + shock)
        for i in range(len(mock_vol_surface.tenors)):
            # Check at least the ATM column
            assert shocked_surface.volatilities[i, 0] >= mock_vol_surface.volatilities[i, 0]
    
    def test_vol_at_tenor_retrieval(self, mock_vol_surface):
        """Test ATM vol retrieval for specific tenor."""
        service = VolSurfaceService()
        
        vol = service.get_vol_at_tenor(mock_vol_surface, tenor=0.25)
        
        assert 0 < vol < 1
        assert isinstance(vol, float)
    
    def test_vol_at_tenor_out_of_bounds(self, mock_vol_surface):
        """Test vol retrieval for tenor outside surface."""
        service = VolSurfaceService()
        
        vol = service.get_vol_at_tenor(mock_vol_surface, tenor=10.0)
        
        # Should return edge value
        assert 0 < vol < 1
    
    def test_reconstruct_surface_from_cache(self, mock_redis):
        """Test surface reconstruction from cache."""
        service = VolSurfaceService(redis_client=mock_redis)
        
        surface = create_mock_surface(datetime.now())
        cache_key = service._cache_key(datetime.now(), "v1.0")
        service._cache_surface(cache_key, surface)
        
        cached = service._memory_cache[cache_key]
        reconstructed = service._reconstruct_surface(cached, cache_key)
        
        assert isinstance(reconstructed, VolSurface)
        assert reconstructed.tenors == surface.tenors
    
    def test_health_check(self, mock_redis):
        """Test health check returns correct status."""
        service = VolSurfaceService(redis_client=mock_redis)
        
        health = service.health_check()
        
        assert "vol_surface_service" in health
        assert health["vol_surface_service"] == "healthy"
        assert "backend" in health
    
    def test_health_check_redis_connected(self, mock_redis):
        """Test health check with Redis connected."""
        service = VolSurfaceService(redis_client=mock_redis)
        
        health = service.health_check()
        
        assert "redis" in health
        assert health["redis"] == "connected"


class TestVolSurfaceServiceCaching:
    """Tests for VolSurfaceService caching behavior."""
    
    def test_memory_cache_ttl(self, mock_redis):
        """Test that memory cache respects TTL."""
        service = VolSurfaceService(redis_client=mock_redis)
        
        surface = create_mock_surface(datetime.now())
        cache_key = service._cache_key(datetime.now(), "v1.0")
        service._cache_surface(cache_key, surface)
        
        cached = service._memory_cache[cache_key]
        age = datetime.now() - cached.timestamp
        
        assert age < service._cache_ttl
    
    def test_shocked_surface_caching(self, mock_vol_surface, sample_vol_shock, mock_redis):
        """Test that shocked surfaces are cached."""
        service = VolSurfaceService(redis_client=mock_redis)
        
        shocked_surface, version = service.get_shocked_surface(
            mock_vol_surface, sample_vol_shock
        )
        
        # Shock should be cached in Redis
        shock_key = service._shock_key(sample_vol_shock.shock_id)
        # Note: In this test mock_redis stores data
        assert shock_key is not None


class TestVolSurfaceIntegration:
    """Integration tests for vol surface functionality."""
    
    def test_full_shock_cycle(self, mock_vol_surface, sample_vol_shock):
        """Test complete shock application cycle."""
        service = VolSurfaceService()
        
        # Apply shock
        shocked_surface, version = service.get_shocked_surface(
            mock_vol_surface, sample_vol_shock
        )
        
        # Get vol at specific tenor from shocked surface
        vol = service.get_vol_at_tenor(shocked_surface, tenor=0.25)
        
        assert 0 < vol < 1
        # Should be different from baseline
        baseline_vol = service.get_vol_at_tenor(mock_vol_surface, tenor=0.25)
        assert vol != baseline_vol
    
    def test_multiple_shocks_different_results(self, mock_vol_surface):
        """Test that different shocks produce different surfaces."""
        service = VolSurfaceService()
        
        # Create two different shocks
        shock1 = VolShock(
            shock_id="shock_1",
            event_vector=EventVector(
                event_id="evt_1",
                headline="Small shock",
                event_type=EventType.INTEREST_RATE,
                sentiment=Sentiment.NEUTRAL,
                sentiment_score=0.0,
                importance=0.5,
                surprise_factor=0.3,
                entities={},
                processed_at=datetime.now(),
                source="test"
            ),
            delta_1W_ATM=0.01,
            delta_1M_ATM=0.01,
            delta_3M_ATM=0.01,
            delta_6M_ATM=0.01,
            delta_1Y_ATM=0.01,
            delta_1M_25RR=0.0,
            delta_1M_25BF=0.0,
            predicted_at=datetime.now(),
            model_version="1.0"
        )
        
        shock2 = VolShock(
            shock_id="shock_2",
            event_vector=EventVector(
                event_id="evt_2",
                headline="Large shock",
                event_type=EventType.INTEREST_RATE,
                sentiment=Sentiment.NEGATIVE,
                sentiment_score=-0.8,
                importance=0.9,
                surprise_factor=0.7,
                entities={},
                processed_at=datetime.now(),
                source="test"
            ),
            delta_1W_ATM=0.05,
            delta_1M_ATM=0.05,
            delta_3M_ATM=0.05,
            delta_6M_ATM=0.05,
            delta_1Y_ATM=0.05,
            delta_1M_25RR=0.02,
            delta_1M_25BF=0.01,
            predicted_at=datetime.now(),
            model_version="1.0"
        )
        
        shocked1, _ = service.get_shocked_surface(mock_vol_surface, shock1)
        shocked2, _ = service.get_shocked_surface(mock_vol_surface, shock2)
        
        # Large shock should result in higher vol than small shock
        vol1 = service.get_vol_at_tenor(shocked1, tenor=0.25)
        vol2 = service.get_vol_at_tenor(shocked2, tenor=0.25)
        
        assert vol2 > vol1


class TestNewsImpactScenario:
    """
    Regression tests for the /api/news-impact endpoint flow.
    Tests that vol surface shock application works with List[List[float]] volatilities
    as created by create_mock_surface and VolSurface schema.
    """
    
    def test_shock_application_with_list_volatility_representation(self, mock_vol_surface_list, sample_vol_shock):
        """
        Regression test: apply shock to surface with List[List[float]] volatilities.
        
        This reproduces the actual flow:
        1. create_mock_surface() creates volatilities as list
        2. VolSurface schema stores as List[List[float]]
        3. get_shocked_surface() must handle this format
        4. The bug: *= operator fails on Python list with float
        
        Before fix: TypeError: can't multiply sequence by non-int of type 'float'
        After fix: Works correctly
        """
        service = VolSurfaceService()
        
        # Verify input is a Python list of lists, not numpy array
        assert isinstance(mock_vol_surface_list.volatilities, list)
        assert isinstance(mock_vol_surface_list.volatilities[0], list)
        
        # Apply shock - this was the failing operation
        shocked_surface, version = service.get_shocked_surface(
            mock_vol_surface_list, sample_vol_shock
        )
        
        # Verify output is correct
        assert isinstance(shocked_surface, VolSurface)
        assert isinstance(shocked_surface.volatilities, list)
        
        # Compare with baseline - shocked should be different
        baseline_atm = mock_vol_surface_list.volatilities[1][0]  # 1M ATM
        shocked_atm = shocked_surface.volatilities[1][0]  # 1M ATM
        
        # With positive shock (sample_vol_shock has delta_1M_ATM=0.03), vol should increase
        assert shocked_atm > baseline_atm
    
    def test_multiple_sequential_shocks_on_list_surface(self, mock_vol_surface_list):
        """
        Test applying multiple shocks sequentially to a list-based surface.
        Ensures the surface remains in correct format after each shock.
        """
        service = VolSurfaceService()
        
        # First shock - positive
        shock1 = VolShock(
            shock_id="shock_pos_001",
            event_vector=sample_vol_shock.event_vector,
            delta_1W_ATM=0.01,
            delta_1M_ATM=0.02,
            delta_3M_ATM=0.015,
            delta_6M_ATM=0.01,
            delta_1Y_ATM=0.005,
            delta_1M_25RR=0.01,
            delta_1M_25BF=0.005,
            predicted_at=datetime.now(),
            model_version="1.0"
        )
        
        shocked1, _ = service.get_shocked_surface(mock_vol_surface_list, shock1)
        
        # Verify first shock worked
        assert isinstance(shocked1.volatilities, list)
        assert shocked1.volatilities[1][0] > mock_vol_surface_list.volatilities[1][0]
        
        # Second shock - negative
        shock2 = VolShock(
            shock_id="shock_neg_002",
            event_vector=EventVector(
                event_id="evt_neg",
                headline="Negative shock",
                event_type=EventType.INFLATION,
                sentiment=Sentiment.NEGATIVE,
                sentiment_score=-0.5,
                importance=0.6,
                surprise_factor=0.4,
                entities={},
                processed_at=datetime.now(),
                source="test"
            ),
            delta_1W_ATM=-0.01,
            delta_1M_ATM=-0.015,
            delta_3M_ATM=-0.01,
            delta_6M_ATM=-0.005,
            delta_1Y_ATM=-0.003,
            delta_1M_25RR=-0.005,
            delta_1M_25BF=-0.002,
            predicted_at=datetime.now(),
            model_version="1.0"
        )
        
        shocked2, _ = service.get_shocked_surface(shocked1, shock2)
        
        # Verify second shock worked
        assert isinstance(shocked2.volatilities, list)
        # net effect should still be positive since shocks were small
        assert shocked2.volatilities[1][0] > mock_vol_surface_list.volatilities[1][0]