# test_nn_risk_engine.py
"""
Unit tests for NN Risk Engine module.
Tests the computation of portfolio Greeks using Black-Scholes formulas
and verifies fallback behavior.
"""
import pytest
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock, patch

from nn_risk_engine import NNRiskEngine, BlackScholesGreeksCPU
from schemas import Portfolio, PortfolioPosition, VolSurface, Greeks


class TestBlackScholesGreeksCPU:
    """Tests for Black-Scholes Greeks computation."""
    
    def test_d1_calculation(self):
        """Test d1 calculation with standard inputs."""
        result = BlackScholesGreeksCPU.d1(
            S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20
        )
        # d1 = (ln(S/K) + (r + 0.5*sigma^2)*T) / (sigma*sqrt(T))
        # d1 = (0 + (0.05 + 0.02)*1) / (0.20*1) = 0.07/0.20 = 0.35
        assert abs(result - 0.35) < 0.001
    
    def test_d2_calculation(self):
        """Test d2 calculation."""
        d1 = 0.35
        result = BlackScholesGreeksCPU.d2(d1, T=1.0, sigma=0.20)
        # d2 = d1 - sigma*sqrt(T) = 0.35 - 0.20 = 0.15
        assert abs(result - 0.15) < 0.001
    
    def test_delta_call_option(self):
        """Test delta for call option (should be positive)."""
        delta = BlackScholesGreeksCPU.delta(
            S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20,
            option_type="CALL"
        )
        # Delta for ATM call should be around 0.5
        assert 0.4 < delta < 0.6
    
    def test_delta_put_option(self):
        """Test delta for put option (should be negative)."""
        delta = BlackScholesGreeksCPU.delta(
            S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20,
            option_type="PUT"
        )
        # Delta for ATM put should be around -0.5
        assert -0.6 < delta < -0.4
    
    def test_delta_in_the_money_call(self):
        """Test delta for deep ITM call (should approach 1)."""
        delta = BlackScholesGreeksCPU.delta(
            S=110.0, K=100.0, T=1.0, r=0.05, sigma=0.20,
            option_type="CALL"
        )
        assert delta > 0.9
    
    def test_delta_out_of_the_money_call(self):
        """Test delta for deep OTM call (should approach 0)."""
        delta = BlackScholesGreeksCPU.delta(
            S=90.0, K=100.0, T=1.0, r=0.05, sigma=0.20,
            option_type="CALL"
        )
        assert delta < 0.1
    
    def test_gamma_positive(self):
        """Test gamma is always positive."""
        gamma = BlackScholesGreeksCPU.gamma(
            S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20
        )
        assert gamma > 0
    
    def test_gamma_decreases_with_time(self):
        """Test gamma increases as option approaches expiration."""
        gamma_1m = BlackScholesGreeksCPU.gamma(
            S=100.0, K=100.0, T=1/12, r=0.05, sigma=0.20
        )
        gamma_3m = BlackScholesGreeksCPU.gamma(
            S=100.0, K=100.0, T=3/12, r=0.05, sigma=0.20
        )
        # Gamma should be higher for shorter expiry
        assert gamma_1m > gamma_3m
    
    def test_vega_positive(self):
        """Test vega is always positive."""
        vega = BlackScholesGreeksCPU.vega(
            S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20
        )
        assert vega > 0
    
    def test_vega_decreases_with_time(self):
        """Test vega decreases as expiry approaches."""
        vega_1m = BlackScholesGreeksCPU.vega(
            S=100.0, K=100.0, T=1/12, r=0.05, sigma=0.20
        )
        vega_1y = BlackScholesGreeksCPU.vega(
            S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20
        )
        # Vega should be higher for longer expiry
        assert vega_1y > vega_1m
    
    def test_theta_call_negative(self):
        """Test theta for call is typically negative (time decay)."""
        theta = BlackScholesGreeksCPU.theta(
            S=100.0, K=100.0, T=3/12, r=0.05, sigma=0.20,
            option_type="CALL"
        )
        # Theta should be negative (option loses value with time)
        assert theta < 0
    
    def test_rho_call_positive(self):
        """Test rho for call is positive."""
        rho = BlackScholesGreeksCPU.rho(
            S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20,
            option_type="CALL"
        )
        assert rho > 0
    
    def test_rho_put_negative(self):
        """Test rho for put is negative."""
        rho = BlackScholesGreeksCPU.rho(
            S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20,
            option_type="PUT"
        )
        assert rho < 0
    
    def test_zero_volatility_handling(self):
        """Test that zero volatility returns zero Greeks."""
        gamma = BlackScholesGreeksCPU.gamma(
            S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.0
        )
        assert gamma == 0.0
    
    def test_zero_time_handling(self):
        """Test that zero time to expiry is handled."""
        delta = BlackScholesGreeksCPU.delta(
            S=100.0, K=100.0, T=0.0, r=0.05, sigma=0.20,
            option_type="CALL"
        )
        assert delta == 0.0


class TestNNRiskEngine:
    """Tests for NNRiskEngine class."""
    
    def test_engine_initialization_blackscholes(self):
        """Test engine initializes in Black-Scholes fallback mode."""
        engine = NNRiskEngine(model_mode="blackscholes")
        assert engine.model_mode == "blackscholes"
    
    def test_engine_initialization_auto_fallback(self):
        """Test engine falls back to Black-Scholes when models unavailable."""
        engine = NNRiskEngine(model_mode="auto")
        # Should fall back to blackscholes when no ONNX/PyTorch available
        assert engine.model_mode == "blackscholes"
    
    def test_compute_greeks_with_blackscholes(
        self, sample_portfolio, mock_vol_surface, spot_rates
    ):
        """Test portfolio Greeks computation with Black-Scholes."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        result = engine.compute_portfolio_greeks(
            sample_portfolio,
            mock_vol_surface,
            spot_rates,
            risk_free_rate=0.05
        )
        
        assert result.portfolio_id == sample_portfolio.portfolio_id
        assert isinstance(result.total_greeks, Greeks)
        assert len(result.position_greeks) == 2
        assert result.computation_time_ms > 0
    
    def test_compute_greeks_single_position(
        self, single_position_portfolio, mock_vol_surface, spot_rates
    ):
        """Test Greeks computation for single position portfolio."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        result = engine.compute_portfolio_greeks(
            single_position_portfolio,
            mock_vol_surface,
            spot_rates,
            risk_free_rate=0.05
        )
        
        assert len(result.position_greeks) == 1
        # Greeks should be scaled by quantity
        assert result.position_greeks["POS-SINGLE"].delta != 0
    
    def test_greeks_addition(self, mock_vol_surface, spot_rates):
        """Test that Greeks are correctly aggregated across positions."""
        portfolio1 = Portfolio(
            portfolio_id="TEST-AGG",
            timestamp=datetime.now(),
            positions=[
                PortfolioPosition(
                    position_id="POS-1",
                    instrument="EUR/USD",
                    spot=1.08,
                    strike=1.08,
                    tenor=0.25,
                    quantity=1000000,
                    option_type="CALL",
                    portfolio_id="TEST-AGG"
                )
            ]
        )
        
        engine = NNRiskEngine(model_mode="blackscholes")
        result = engine.compute_portfolio_greeks(
            portfolio1, mock_vol_surface, spot_rates, risk_free_rate=0.05
        )
        
        # Total should equal single position value
        assert result.total_greeks.delta == result.position_greeks["POS-1"].delta
    
    def test_get_vol_for_position(self, sample_portfolio, mock_vol_surface):
        """Test volatility extraction from vol surface."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        vol = engine._get_vol_for_position(
            sample_portfolio.positions[0],
            mock_vol_surface
        )
        
        assert 0 < vol < 1  # Volatility should be reasonable
        assert isinstance(vol, float)
    
    def test_bucketed_vega(self, sample_portfolio, mock_vol_surface, spot_rates):
        """Test bucketed vega computation by tenor."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        bucketed = engine.compute_bucketed_vega(
            sample_portfolio,
            mock_vol_surface,
            spot_rates,
            risk_free_rate=0.05
        )
        
        assert isinstance(bucketed, dict)
        # Should have entries for each unique tenor
        for key, value in bucketed.items():
            assert "Y" in key  # Tenor labels like "0.25Y"
            assert isinstance(value, float)
    
    def test_health_check(self):
        """Test health check returns correct status."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        health = engine.health_check()
        
        assert "nn_risk_engine" in health
        assert health["nn_risk_engine"] == "healthy"
        assert "model_mode" in health
        assert health["model_mode"] == "blackscholes"
    
    def test_computation_time_recorded(self, sample_portfolio, mock_vol_surface, spot_rates):
        """Test that computation time is recorded."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        result = engine.compute_portfolio_greeks(
            sample_portfolio, mock_vol_surface, spot_rates
        )
        
        assert result.timestamp is not None
    
    def test_invalid_position_handling(self, sample_portfolio, mock_vol_surface, spot_rates):
        """Test handling of invalid position data."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        # Create portfolio with one invalid position
        bad_portfolio = Portfolio(
            portfolio_id="BAD-PORT",
            timestamp=datetime.now(),
            positions=[
                PortfolioPosition(
                    position_id="BAD-POS",
                    instrument="INVALID",
                    spot=-100.0,  # Invalid: negative spot
                    strike=100.0,
                    tenor=0.25,
                    quantity=1000000,
                    option_type="CALL",
                    portfolio_id="BAD-PORT"
                )
            ]
        )
        
        result = engine.compute_portfolio_greeks(
            bad_portfolio, mock_vol_surface, spot_rates
        )
        
        # Should still return result (possibly with zero Greeks)
        assert result.portfolio_id == "BAD-PORT"


class TestNNRiskEngineEdgeCases:
    """Edge case tests for NNRiskEngine."""
    
    def test_empty_portfolio(self, mock_vol_surface, spot_rates):
        """Test handling of empty portfolio."""
        empty_portfolio = Portfolio(
            portfolio_id="EMPTY",
            timestamp=datetime.now(),
            positions=[]
        )
        
        engine = NNRiskEngine(model_mode="blackscholes")
        result = engine.compute_portfolio_greeks(
            empty_portfolio, mock_vol_surface, spot_rates
        )
        
        # Should return zero Greeks for empty portfolio
        assert result.total_greeks.delta == 0
        assert result.total_greeks.gamma == 0
    
    def test_very_small_tenor(self, mock_vol_surface, spot_rates):
        """Test handling of very small tenor (near expiry)."""
        near_expiry = Portfolio(
            portfolio_id="NEAR-EXPIRY",
            timestamp=datetime.now(),
            positions=[
                PortfolioPosition(
                    position_id="POS-EX",
                    instrument="EUR/USD",
                    spot=1.08,
                    strike=1.08,
                    tenor=0.001,  # Very small tenor
                    quantity=1000000,
                    option_type="CALL",
                    portfolio_id="NEAR-EXPIRY"
                )
            ]
        )
        
        engine = NNRiskEngine(model_mode="blackscholes")
        result = engine.compute_portfolio_greeks(
            near_expiry, mock_vol_surface, spot_rates
        )
        
        # Should handle without crashing (Greeks may be near zero)
        assert isinstance(result.total_greeks.delta, float)
    
    def test_very_large_volatility(self, mock_vol_surface, spot_rates):
        """Test handling of very high volatility."""
        high_vol_surface = VolSurface(
            snapshot_id="high_vol",
            base_date=datetime.now(),
            tenors=[0.25],
            strikes=[100],
            volatilities=np.array([[2.0]]),  # 200% vol
            source="test",
            version="v1"
        )
        
        portfolio = Portfolio(
            portfolio_id="HIGH-VOL",
            timestamp=datetime.now(),
            positions=[
                PortfolioPosition(
                    position_id="POS-HV",
                    instrument="EUR/USD",
                    spot=1.08,
                    strike=1.08,
                    tenor=0.25,
                    quantity=1000000,
                    option_type="CALL",
                    portfolio_id="HIGH-VOL"
                )
            ]
        )
        
        engine = NNRiskEngine(model_mode="blackscholes")
        result = engine.compute_portfolio_greeks(
            portfolio, high_vol_surface, spot_rates
        )
        
        # Should handle without crashing
        assert isinstance(result.total_greeks.gamma, float)
    
    def test_greeks_dict_conversion(self):
        """Test Greeks to_dict method."""
        greeks = Greeks(
            delta=100.0,
            gamma=50.0,
            vega=75.0,
            theta=-10.0,
            rho=25.0
        )
        
        greeks_dict = greeks.to_dict()
        
        assert isinstance(greeks_dict, dict)
        assert greeks_dict["delta"] == 100.0
        assert greeks_dict["gamma"] == 50.0
        assert greeks_dict["vega"] == 75.0
        assert greeks_dict["theta"] == -10.0
        assert greeks_dict["rho"] == 25.0
        assert greeks_dict["vanna"] is None
        assert greeks_dict["volga"] is None


class TestImpactedGreeks:
    """Tests for impacted Greeks with weighting between spot rate and news shock."""
    
    def test_impacted_greeks_full_shock(
        self, sample_portfolio, mock_vol_surface, spot_rates
    ):
        """Test impacted Greeks with full vol shock (vol_shock_weight=1)."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        from schemas import GreeksImpactWeights, VolShock, EventVector, EventType, Sentiment
        from vol_surface_service import create_mock_surface
        
        # Create shocked surface
        shocked_surface = create_mock_surface(datetime.now(), base_vol=0.15)
        
        weights = GreeksImpactWeights(
            spot_rate_weight=0.0,
            vol_shock_weight=1.0,
            spot_shock_weight=0.0
        )
        
        result = engine.compute_impacted_greeks(
            portfolio=sample_portfolio,
            base_vol_surface=mock_vol_surface,
            shocked_vol_surface=shocked_surface,
            base_spot_rates=spot_rates,
            weights=weights,
            risk_free_rate=0.05
        )
        
        assert result.portfolio_id == sample_portfolio.portfolio_id
        assert isinstance(result.total_greeks, Greeks)
        # With full shock, should get Greeks from shocked surface
        assert result.total_greeks.vega != 0
    
    def test_impacted_greeks_no_shock(
        self, sample_portfolio, mock_vol_surface, spot_rates
    ):
        """Test impacted Greeks with no shock (spot_rate_weight=1)."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        from schemas import GreeksImpactWeights
        from vol_surface_service import create_mock_surface
        
        shocked_surface = create_mock_surface(datetime.now(), base_vol=0.15)
        
        weights = GreeksImpactWeights(
            spot_rate_weight=1.0,
            vol_shock_weight=0.0,
            spot_shock_weight=0.0
        )
        
        result = engine.compute_impacted_greeks(
            portfolio=sample_portfolio,
            base_vol_surface=mock_vol_surface,
            shocked_vol_surface=shocked_surface,
            base_spot_rates=spot_rates,
            weights=weights,
            risk_free_rate=0.05
        )
        
        # With no shock, should get base Greeks
        base_result = engine.compute_portfolio_greeks(
            sample_portfolio, mock_vol_surface, spot_rates, risk_free_rate=0.05
        )
        
        assert abs(result.total_greeks.vega - base_result.total_greeks.vega) < 0.01
    
    def test_impacted_greeks_blended(
        self, sample_portfolio, mock_vol_surface, spot_rates
    ):
        """Test impacted Greeks with blended weights (50/50)."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        from schemas import GreeksImpactWeights
        from vol_surface_service import create_mock_surface
        
        shocked_surface = create_mock_surface(datetime.now(), base_vol=0.15)
        
        weights = GreeksImpactWeights(
            spot_rate_weight=0.5,
            vol_shock_weight=0.5,
            spot_shock_weight=0.0
        )
        
        result = engine.compute_impacted_greeks(
            portfolio=sample_portfolio,
            base_vol_surface=mock_vol_surface,
            shocked_vol_surface=shocked_surface,
            base_spot_rates=spot_rates,
            weights=weights,
            risk_free_rate=0.05
        )
        
        # Get base and full shock Greeks for comparison
        base_result = engine.compute_portfolio_greeks(
            sample_portfolio, mock_vol_surface, spot_rates, risk_free_rate=0.05
        )
        shocked_result = engine.compute_portfolio_greeks(
            sample_portfolio, shocked_surface, spot_rates, risk_free_rate=0.05
        )
        
        expected_vega = (base_result.total_greeks.vega + shocked_result.total_greeks.vega) / 2
        
        # Blended should be between base and shocked
        assert min(base_result.total_greeks.vega, shocked_result.total_greeks.vega) <= result.total_greeks.vega
        assert result.total_greeks.vega <= max(base_result.total_greeks.vega, shocked_result.total_greeks.vega)
    
    def test_impacted_greeks_position_level(
        self, sample_portfolio, mock_vol_surface, spot_rates
    ):
        """Test that impacted Greeks are computed at position level."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        from schemas import GreeksImpactWeights
        from vol_surface_service import create_mock_surface
        
        shocked_surface = create_mock_surface(datetime.now(), base_vol=0.15)
        
        weights = GreeksImpactWeights(
            spot_rate_weight=0.3,
            vol_shock_weight=0.7,
            spot_shock_weight=0.0
        )
        
        result = engine.compute_impacted_greeks(
            portfolio=sample_portfolio,
            base_vol_surface=mock_vol_surface,
            shocked_vol_surface=shocked_surface,
            base_spot_rates=spot_rates,
            weights=weights,
            risk_free_rate=0.05
        )
        
        # Should have position-level Greeks
        assert len(result.position_greeks) == len(sample_portfolio.positions)
        for pos_id, greeks in result.position_greeks.items():
            assert isinstance(greeks, Greeks)
    
    def test_weights_to_blend_factors(self):
        """Test GreeksImpactWeights to_blend_factors method."""
        from schemas import GreeksImpactWeights
        
        weights = GreeksImpactWeights(
            spot_rate_weight=0.3,
            vol_shock_weight=0.7,
            spot_shock_weight=0.0
        )
        
        spot_factor, vol_shock_factor, spot_shock_factor = weights.to_blend_factors()
        
        assert spot_factor == 0.3
        assert vol_shock_factor == 0.7
        assert spot_shock_factor == 0.0
    
    def test_blend_optional_greeks(self):
        """Test blending of optional Greeks (vanna, volga)."""
        engine = NNRiskEngine(model_mode="blackscholes")
        
        # Both None
        result = engine._blend_optional(None, None, 0.5, 0.5)
        assert result is None
        
        # One None
        result = engine._blend_optional(10.0, None, 0.5, 0.5)
        assert result == 5.0
        
        result = engine._blend_optional(None, 20.0, 0.5, 0.5)
        assert result == 10.0
        
        # Both present
        result = engine._blend_optional(10.0, 20.0, 0.5, 0.5)
        assert result == 15.0