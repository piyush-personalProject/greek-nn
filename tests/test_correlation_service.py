# tests/test_correlation_service.py
"""
Tests for Correlation Service

Tests cross-asset correlation handling for FX portfolios.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from schemas import (
    Greeks, CorrelationMatrix, CorrelationAdjustedGreeks,
    CorrelationStressTest, CorrelationStressResult, CorrelationRiskReport,
    Portfolio, PortfolioPosition, RiskAttributionFactor
)
from services.correlation_service import (
    CorrelationService, get_correlation_service,
    CRISIS_CORRELATION_SCENARIOS, DEFAULT_FX_CORRELATIONS
)


class TestCorrelationMatrix:
    """Test correlation matrix creation and operations."""
    
    def test_create_identity_matrix(self):
        """Test creating identity matrix for uncorrelated assets."""
        pairs = ["EURUSD", "GBPUSD", "USDJPY"]
        matrix = CorrelationMatrix.create_identity(pairs, "test-identity")
        
        assert matrix.matrix_id == "test-identity"
        assert matrix.pairs == pairs
        assert len(matrix.correlations) == 3
        
        # Self-correlations should be 1.0
        for pair in pairs:
            assert matrix.get_correlation(pair, pair) == 1.0
    
    def test_get_correlation(self):
        """Test getting correlation between pairs."""
        pairs = ["EURUSD", "GBPUSD"]
        correlations = {
            ("EURUSD", "GBPUSD"): 0.85,
            ("EURUSD", "EURUSD"): 1.0,
            ("GBPUSD", "GBPUSD"): 1.0
        }
        matrix = CorrelationMatrix.create_from_dict(pairs, correlations, "test-corr")
        
        assert matrix.get_correlation("EURUSD", "GBPUSD") == 0.85
        assert matrix.get_correlation("GBPUSD", "EURUSD") == 0.85  # Symmetric
        assert matrix.get_correlation("EURUSD", "EURUSD") == 1.0
        assert matrix.get_correlation("UNKNOWN", "EURUSD") == 0.0  # Unknown = 0
    
    def test_is_positive_negative_correlated(self):
        """Test correlation classification methods."""
        pairs = ["EURUSD", "GBPUSD", "USDJPY"]
        correlations = {
            ("EURUSD", "GBPUSD"): 0.85,
            ("EURUSD", "USDJPY"): -0.65
        }
        matrix = CorrelationMatrix.create_from_dict(pairs, correlations, "test-classify")
        
        assert matrix.is_positive_correlated("EURUSD", "GBPUSD") is True
        assert matrix.is_negative_correlated("EURUSD", "USDJPY") is True
        assert matrix.is_positive_correlated("EURUSD", "USDJPY") is False
        assert matrix.is_negative_correlated("EURUSD", "GBPUSD") is False


class TestCorrelationService:
    """Test CorrelationService functionality."""
    
    def test_default_matrix_created(self):
        """Test that default FX correlation matrix is created."""
        service = CorrelationService()
        
        assert service.correlation_matrix is not None
        assert len(service.correlation_matrix.pairs) > 0
        assert "EURUSD" in service.correlation_matrix.pairs
        assert "GBPUSD" in service.correlation_matrix.pairs
    
    def test_get_correlation_matrix(self):
        """Test getting correlation matrix from service."""
        service = CorrelationService()
        matrix = service.get_correlation_matrix()
        
        assert matrix is not None
        assert isinstance(matrix, CorrelationMatrix)
    
    def test_update_correlation(self):
        """Test updating a single correlation value."""
        service = CorrelationService()
        
        # Update EURUSD/GBPUSD correlation
        original_corr = service.correlation_matrix.get_correlation("EURUSD", "GBPUSD")
        service.update_correlation("EURUSD", "GBPUSD", 0.95)
        
        updated_corr = service.correlation_matrix.get_correlation("EURUSD", "GBPUSD")
        assert updated_corr == 0.95
        assert updated_corr != original_corr
    
    def test_update_correlation_clamped(self):
        """Test that correlation is clamped to valid range."""
        service = CorrelationService()
        
        # Try to set correlation > 1.0 (should be clamped to 1.0)
        service.update_correlation("EURUSD", "GBPUSD", 1.5)
        assert service.correlation_matrix.get_correlation("EURUSD", "GBPUSD") == 1.0
        
        # Try to set correlation < -1.0 (should be clamped to -1.0)
        service.update_correlation("EURUSD", "USDJPY", -1.5)
        assert service.correlation_matrix.get_correlation("EURUSD", "USDJPY") == -1.0
    
    def test_get_pairs_from_portfolio(self):
        """Test extracting unique pairs from portfolio positions."""
        service = CorrelationService()
        
        positions = [
            PortfolioPosition(
                position_id="1", instrument="EURUSD", spot=1.0850,
                strike=1.0900, tenor=0.1, quantity=1000000,
                option_type="CALL", portfolio_id="TEST"
            ),
            PortfolioPosition(
                position_id="2", instrument="EURUSD", spot=1.0850,
                strike=1.0800, tenor=0.25, quantity=-500000,
                option_type="PUT", portfolio_id="TEST"
            ),
            PortfolioPosition(
                position_id="3", instrument="GBPUSD", spot=1.2650,
                strike=1.2600, tenor=0.5, quantity=750000,
                option_type="PUT", portfolio_id="TEST"
            ),
        ]
        
        pairs = service.get_pairs_from_portfolio(positions)
        assert len(pairs) == 2
        assert "EURUSD" in pairs
        assert "GBPUSD" in pairs
    
    def test_compute_correlation_matrix_for_portfolio(self):
        """Test computing correlation matrix for portfolio pairs."""
        service = CorrelationService()
        
        positions = [
            PortfolioPosition(
                position_id="1", instrument="EURUSD", spot=1.0850,
                strike=1.0900, tenor=0.1, quantity=1000000,
                option_type="CALL", portfolio_id="TEST"
            ),
            PortfolioPosition(
                position_id="2", instrument="GBPUSD", spot=1.2650,
                strike=1.2600, tenor=0.5, quantity=750000,
                option_type="PUT", portfolio_id="TEST"
            ),
        ]
        
        corr_matrix = service.compute_correlation_matrix_for_portfolio(positions)
        
        # Should be 2x2 matrix
        assert corr_matrix.shape == (2, 2)
        
        # Diagonal should be 1.0
        assert corr_matrix[0, 0] == 1.0
        assert corr_matrix[1, 1] == 1.0
        
        # Off-diagonal should be EURUSD-GBPUSD correlation
        import numpy as np
        assert np.isclose(corr_matrix[0, 1], 0.85, atol=0.01)
        assert np.isclose(corr_matrix[1, 0], 0.85, atol=0.01)


class TestCorrelationAdjustedGreeks:
    """Test correlation-adjusted Greeks computation."""
    
    def test_single_pair_no_adjustment(self):
        """Test that single-pair portfolio has no correlation adjustment."""
        service = CorrelationService()
        
        positions = [
            PortfolioPosition(
                position_id="1", instrument="EURUSD", spot=1.0850,
                strike=1.0900, tenor=0.1, quantity=1000000,
                option_type="CALL", portfolio_id="TEST"
            )
        ]
        
        position_greeks = {
            "1": Greeks(delta=10000, gamma=500, vega=50000, theta=-100, rho=200)
        }
        total_greeks = Greeks(delta=10000, gamma=500, vega=50000, theta=-100, rho=200)
        
        result = service.compute_correlation_adjusted_greeks(
            positions=positions,
            position_greeks=position_greeks,
            total_greeks=total_greeks
        )
        
        # Single pair - no correlation adjustment needed
        assert result.raw_greeks == result.adjusted_greeks
    
    def test_diversification_ratio_calculation(self):
        """Test diversification ratio calculation."""
        service = CorrelationService()
        
        raw_greeks = Greeks(delta=100000, gamma=10000, vega=100000, theta=0, rho=0)
        adjusted_greeks = Greeks(delta=80000, gamma=8000, vega=80000, theta=0, rho=0)
        
        ratio = service.compute_diversification_ratio(raw_greeks, adjusted_greeks)
        
        assert ratio == 0.8  # 20% diversification benefit


class TestCorrelationStressTesting:
    """Test correlation stress testing functionality."""
    
    def test_available_scenarios(self):
        """Test that predefined scenarios are available."""
        service = CorrelationService()
        scenarios = service.get_available_scenarios()
        
        assert len(scenarios) > 0
        assert any(s["id"] == "2008_lehman" for s in scenarios)
        assert any(s["id"] == "covid_march_2020" for s in scenarios)
    
    def test_stress_test_execution(self):
        """Test running a correlation stress test."""
        service = CorrelationService()
        
        positions = [
            PortfolioPosition(
                position_id="1", instrument="EURUSD", spot=1.0850,
                strike=1.0900, tenor=0.1, quantity=1000000,
                option_type="CALL", portfolio_id="TEST"
            ),
            PortfolioPosition(
                position_id="2", instrument="GBPUSD", spot=1.2650,
                strike=1.2600, tenor=0.5, quantity=750000,
                option_type="PUT", portfolio_id="TEST"
            )
        ]
        
        position_greeks = {
            "1": Greeks(delta=10000, gamma=500, vega=50000, theta=-100, rho=200),
            "2": Greeks(delta=8000, gamma=400, vega=40000, theta=-80, rho=160)
        }
        
        raw_greeks = Greeks(delta=18000, gamma=900, vega=90000, theta=-180, rho=360)
        
        # Create a test scenario
        scenario = CorrelationStressTest(
            scenario_id="test_scenario",
            name="Test Crisis",
            description="Test description",
            correlation_multipliers={("*", "*"): 2.0}  # Double all correlations
        )
        
        result = service.run_stress_test(
            raw_greeks=raw_greeks,
            positions=positions,
            position_greeks=position_greeks,
            scenario=scenario
        )
        
        assert result is not None
        assert result.scenario.scenario_id == "test_scenario"
        assert isinstance(result.baseline_greeks, Greeks)
        assert isinstance(result.stressed_greeks, Greeks)


class TestCorrelationRiskReport:
    """Test correlation risk report generation."""
    
    def test_report_generation(self):
        """Test generating full correlation risk report."""
        service = CorrelationService()
        
        positions = [
            PortfolioPosition(
                position_id="1", instrument="EURUSD", spot=1.0850,
                strike=1.0900, tenor=0.1, quantity=1000000,
                option_type="CALL", portfolio_id="TEST"
            ),
            PortfolioPosition(
                position_id="2", instrument="GBPUSD", spot=1.2650,
                strike=1.2600, tenor=0.5, quantity=750000,
                option_type="PUT", portfolio_id="TEST"
            ),
            PortfolioPosition(
                position_id="3", instrument="USDJPY", spot=149.50,
                strike=150.00, tenor=0.04, quantity=2000000,
                option_type="CALL", portfolio_id="TEST"
            )
        ]
        
        position_greeks = {
            "1": Greeks(delta=10000, gamma=500, vega=50000, theta=-100, rho=200),
            "2": Greeks(delta=8000, gamma=400, vega=40000, theta=-80, rho=160),
            "3": Greeks(delta=15000, gamma=600, vega=60000, theta=-120, rho=240)
        }
        
        total_greeks = Greeks(delta=33000, gamma=1500, vega=150000, theta=-300, rho=600)
        
        report = service.generate_correlation_risk_report(
            portfolio_id="TEST-PORTFOLIO",
            positions=positions,
            position_greeks=position_greeks,
            total_greeks=total_greeks
        )
        
        assert report is not None
        assert report.portfolio_id == "TEST-PORTFOLIO"
        assert isinstance(report.raw_total_greeks, Greeks)
        assert isinstance(report.adjusted_total_greeks, Greeks)
        assert report.diversification_ratio > 0
        assert len(report.stress_tests) > 0


class TestCrisisCorrelationScenarios:
    """Test predefined crisis correlation scenarios."""
    
    def test_lehman_scenario(self):
        """Test 2008 Lehman crisis scenario multipliers."""
        scenario = CRISIS_CORRELATION_SCENARIOS["2008_lehman"]
        
        assert scenario["name"] == "2008 Lehman Crisis"
        assert ("*", "*") in scenario["multipliers"]
        assert scenario["multipliers"][("*", "*")] == 2.0
    
    def test_covid_scenario(self):
        """Test COVID March 2020 scenario."""
        scenario = CRISIS_CORRELATION_SCENARIOS["covid_march_2020"]
        
        assert scenario["name"] == "COVID March 2020"
        assert ("EURUSD", "GBPUSD") in scenario["multipliers"]
    
    def test_all_scenarios_have_multipliers(self):
        """Test that all scenarios have correlation multipliers."""
        for scenario_id, scenario_data in CRISIS_CORRELATION_SCENARIOS.items():
            assert "name" in scenario_data
            assert "description" in scenario_data
            assert "multipliers" in scenario_data
            assert len(scenario_data["multipliers"]) > 0


class TestSingletonService:
    """Test the singleton service accessor."""
    
    def test_get_correlation_service(self):
        """Test getting singleton correlation service instance."""
        service = get_correlation_service()
        
        assert service is not None
        assert isinstance(service, CorrelationService)
        
        # Should return same instance on subsequent calls
        service2 = get_correlation_service()
        assert service is service2
