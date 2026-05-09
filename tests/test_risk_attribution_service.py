# tests/test_risk_attribution_service.py
"""
Tests for Risk Attribution Service.

Tests the attribution breakdown of Greek changes into:
- News Headlines attribution
- Historical Vol Drift attribution
- NN Model Adjustment attribution
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from schemas import (
    Greeks, EventVector, VolShock, EventType, Sentiment,
    RiskAttributionFactor, VegaSpikeAttribution, RiskAttributionReport
)
from services.risk_attribution_service import RiskAttributionService, get_attribution_service


class TestRiskAttributionService:
    """Test suite for RiskAttributionService."""
    
    @pytest.fixture
    def attribution_service(self) -> RiskAttributionService:
        """Create attribution service instance."""
        return RiskAttributionService()
    
    @pytest.fixture
    def baseline_greeks(self) -> Greeks:
        """Sample baseline Greeks."""
        return Greeks(
            delta=50000.0,
            gamma=12000.0,
            vega=100000.0,
            theta=-5000.0,
            rho=25000.0
        )
    
    @pytest.fixture
    def current_greeks(self) -> Greeks:
        """Sample current Greeks after a vol spike."""
        return Greeks(
            delta=48000.0,
            gamma=11500.0,
            vega=110000.0,  # $10K increase (vega spike)
            theta=-4800.0,
            rho=23000.0
        )
    
    @pytest.fixture
    def ecb_event_vector(self) -> EventVector:
        """ECB interest rate event vector."""
        return EventVector(
            event_id="evt_ecb_rate",
            headline="ECB announces unexpected rate cut amid cooling inflation",
            event_type=EventType.INTEREST_RATE,
            sentiment=Sentiment.NEGATIVE,
            sentiment_score=-0.73,
            importance=0.82,
            surprise_factor=0.6,
            entities={"central_banks": ["ECB"], "currencies": ["EUR"]},
            processed_at=datetime.now(),
            source="NLP"
        )
    
    @pytest.fixture
    def vol_shock(self, ecb_event_vector) -> VolShock:
        """Vol shock from ECB event."""
        return VolShock(
            shock_id="shock_ecb_001",
            event_vector=ecb_event_vector,
            affected_pairs=["EURUSD"],
            delta_1W_ATM=-0.0042,
            delta_1M_ATM=-0.0045,
            delta_3M_ATM=-0.0038,
            delta_6M_ATM=-0.0028,
            delta_1Y_ATM=-0.0020,
            delta_1M_25RR=-0.0015,
            delta_1M_25BF=-0.0008,
            predicted_at=datetime.now(),
            model_version="rulebased"
        )
    
    def test_compute_attribution_with_news_event(
        self,
        attribution_service,
        baseline_greeks,
        current_greeks,
        ecb_event_vector,
        vol_shock
    ):
        """Test attribution computation with news event."""
        report = attribution_service.compute_attribution(
            baseline_greeks=baseline_greeks,
            current_greeks=current_greeks,
            vol_shock=vol_shock,
            news_event=ecb_event_vector,
            nn_model_mode="blackscholes"
        )
        
        assert report is not None
        assert isinstance(report, RiskAttributionReport)
        assert report.portfolio_id == "FX-PORTFOLIO-01"
        assert report.greeks_delta.vega == 10000.0  # $10K vega spike
        
        # Vega attribution should have 3 factors
        assert len(report.vega_attribution) == 3
        
        # Verify attributions sum to ~100%
        vega_total = sum(f.percentage for f in report.vega_attribution)
        assert 99 <= vega_total <= 101
    
    def test_vega_spike_detection(
        self,
        attribution_service,
        baseline_greeks,
        current_greeks,
        ecb_event_vector,
        vol_shock
    ):
        """Test that $10K+ vega spike triggers special report."""
        report = attribution_service.compute_attribution(
            baseline_greeks=baseline_greeks,
            current_greeks=current_greeks,
            vol_shock=vol_shock,
            news_event=ecb_event_vector,
            nn_model_mode="onnx"
        )
        
        # Vega spike of $10K should trigger special report
        assert report.vega_spike_report is not None
        assert report.vega_spike_report.vega_spike_amount == 10000.0
        assert "ECB" in report.vega_spike_report.headline or "rate" in report.vega_spike_report.headline.lower()
    
    def test_vega_spike_attribution_breakdown(
        self,
        attribution_service,
        baseline_greeks,
        current_greeks,
        ecb_event_vector,
        vol_shock
    ):
        """Test that Vega spike attribution has correct percentages."""
        report = attribution_service.compute_attribution(
            baseline_greeks=baseline_greeks,
            current_greeks=current_greeks,
            vol_shock=vol_shock,
            news_event=ecb_event_vector,
            nn_model_mode="onnx"
        )
        
        vega_spike = report.vega_spike_report
        assert vega_spike is not None
        
        # Should have 3 attribution factors
        assert len(vega_spike.attribution_factors) == 3
        
        # Find ECB headline attribution
        news_factor = next(
            f for f in vega_spike.attribution_factors 
            if f.factor_type == "news_headline"
        )
        assert "ECB" in news_factor.source or "interest rate" in news_factor.source.lower()
        assert news_factor.percentage == 55.0  # INTEREST_RATE uses 55% news weight
        
        # Find vol drift attribution
        drift_factor = next(
            f for f in vega_spike.attribution_factors 
            if f.factor_type == "historical_vol_drift"
        )
        assert drift_factor.percentage == 25.0  # INTEREST_RATE uses 25% vol drift
        
        # Find NN model adjustment
        nn_factor = next(
            f for f in vega_spike.attribution_factors 
            if f.factor_type == "nn_model_adjustment"
        )
        assert nn_factor.percentage == 20.0
        assert "onnx" in nn_factor.source
    
    def test_attribution_without_news_event(
        self,
        attribution_service,
        baseline_greeks,
        current_greeks
    ):
        """Test attribution when no news event is present."""
        # No vol_shock or news_event provided
        report = attribution_service.compute_attribution(
            baseline_greeks=baseline_greeks,
            current_greeks=current_greeks,
            vol_shock=None,
            news_event=None,
            nn_model_mode="blackscholes"
        )
        
        assert report is not None
        # Should have vega spike report since delta is $10K
        assert report.vega_spike_report is not None
        
        # Attribution should be 100% historical vol drift when no news
        drift_factors = [
            f for f in report.vega_spike_report.attribution_factors 
            if f.factor_type == "historical_vol_drift"
        ]
        assert len(drift_factors) == 1
        assert drift_factors[0].percentage == 100.0
    
    def test_attribution_for_small_vega_change(
        self,
        attribution_service
    ):
        """Test attribution when vega change is below spike threshold."""
        baseline = Greeks(delta=50000, gamma=12000, vega=100000, theta=-5000, rho=25000)
        # Small vega change of only $1K
        current = Greeks(delta=50100, gamma=12050, vega=101000, theta=-5050, rho=25100)
        
        report = attribution_service.compute_attribution(
            baseline_greeks=baseline,
            current_greeks=current,
            vol_shock=None,
            news_event=None,
            nn_model_mode="blackscholes"
        )
        
        # $1K change should not trigger vega spike report
        assert report.vega_spike_report is None
    
    def test_primary_driver_determination(
        self,
        attribution_service,
        baseline_greeks,
        current_greeks,
        ecb_event_vector,
        vol_shock
    ):
        """Test that primary driver is correctly identified."""
        report = attribution_service.compute_attribution(
            baseline_greeks=baseline_greeks,
            current_greeks=current_greeks,
            vol_shock=vol_shock,
            news_event=ecb_event_vector,
            nn_model_mode="blackscholes"
        )
        
        assert report.primary_driver is not None
        assert len(report.primary_driver) > 0
        # Primary driver should mention vega since that's the biggest change
        assert "vega" in report.primary_driver.lower() or "news" in report.primary_driver.lower()
    
    def test_confidence_score_calculation(
        self,
        attribution_service,
        baseline_greeks,
        current_greeks,
        ecb_event_vector,
        vol_shock
    ):
        """Test confidence score computation."""
        # With news event + non-rulebased model
        report = attribution_service.compute_attribution(
            baseline_greeks=baseline_greeks,
            current_greeks=current_greeks,
            vol_shock=vol_shock,
            news_event=ecb_event_vector,
            nn_model_mode="onnx"
        )
        
        assert report.confidence_score > 0.5  # Should have higher confidence
        
        # Without news event
        report_no_news = attribution_service.compute_attribution(
            baseline_greeks=baseline_greeks,
            current_greeks=current_greeks,
            vol_shock=None,
            news_event=None,
            nn_model_mode="blackscholes"
        )
        
        # Lower confidence without news
        assert report_no_news.confidence_score <= report.confidence_score
    
    def test_interest_rate_event_uses_correct_weights(
        self,
        attribution_service,
        baseline_greeks
    ):
        """Test INTEREST_RATE event uses 55/25/20 weights."""
        current = Greeks(
            delta=48000, gamma=11500, vega=110000,
            theta=-4800, rho=23000
        )
        
        event = EventVector(
            event_id="test_ir",
            headline="Fed raises rates by 25bps",
            event_type=EventType.INTEREST_RATE,
            sentiment=Sentiment.NEGATIVE,
            sentiment_score=-0.5,
            importance=0.8,
            surprise_factor=0.5,
            entities={"central_banks": ["Federal Reserve"]},
            processed_at=datetime.now(),
            source="test"
        )
        
        shock = VolShock(
            shock_id="test_shock",
            event_vector=event,
            affected_pairs=["EURUSD"],
            delta_1W_ATM=0.01, delta_1M_ATM=0.015,
            delta_3M_ATM=0.012, delta_6M_ATM=0.01,
            delta_1Y_ATM=0.008, delta_1M_25RR=0.005,
            delta_1M_25BF=0.002,
            predicted_at=datetime.now(),
            model_version="onnx"
        )
        
        report = attribution_service.compute_attribution(
            baseline_greeks=baseline_greeks,
            current_greeks=current,
            vol_shock=shock,
            news_event=event,
            nn_model_mode="onnx"
        )
        
        # Verify the weights used
        news_factors = [f for f in report.vega_attribution if f.factor_type == "news_headline"]
        drift_factors = [f for f in report.vega_attribution if f.factor_type == "historical_vol_drift"]
        nn_factors = [f for f in report.vega_attribution if f.factor_type == "nn_model_adjustment"]
        
        if news_factors:
            assert news_factors[0].percentage == 55.0
        if drift_factors:
            assert drift_factors[0].percentage == 25.0
        if nn_factors:
            assert nn_factors[0].percentage == 20.0
    
    def test_singleton_service_instance(self):
        """Test that get_attribution_service returns singleton."""
        service1 = get_attribution_service()
        service2 = get_attribution_service()
        assert service1 is service2
    
    def test_attribution_factors_have_evidence(
        self,
        attribution_service,
        baseline_greeks,
        current_greeks,
        ecb_event_vector,
        vol_shock
    ):
        """Test that attribution factors include supporting evidence."""
        report = attribution_service.compute_attribution(
            baseline_greeks=baseline_greeks,
            current_greeks=current_greeks,
            vol_shock=vol_shock,
            news_event=ecb_event_vector,
            nn_model_mode="onnx"
        )
        
        # Each factor should have evidence dict
        for factor in report.vega_attribution:
            assert isinstance(factor.evidence, dict)
            if factor.factor_type == "news_headline":
                # News factors should have event type, sentiment etc in evidence
                assert "event_type" in factor.evidence or "importance" in factor.evidence


class TestVegaSpikeHumanReadable:
    """Tests for human-readable Vega spike attribution."""
    
    @pytest.fixture
    def service(self) -> RiskAttributionService:
        return RiskAttributionService()
    
    @pytest.fixture
    def large_vega_spike_scenario(self):
        """Scenario with large vega spike from ECB headline."""
        baseline = Greeks(delta=50000, gamma=12000, vega=100000, theta=-5000, rho=25000)
        current = Greeks(delta=48000, gamma=11500, vega=110000, theta=-4800, rho=23000)
        
        event = EventVector(
            event_id="evt_ecb",
            headline="ECB interest rate headline causes market turmoil",
            event_type=EventType.INTEREST_RATE,
            sentiment=Sentiment.NEGATIVE,
            sentiment_score=-0.73,
            importance=0.82,
            surprise_factor=0.6,
            entities={"central_banks": ["ECB"]},
            processed_at=datetime.now(),
            source="test"
        )
        
        shock = VolShock(
            shock_id="shock_ecb",
            event_vector=event,
            affected_pairs=["EURUSD"],
            delta_1W_ATM=-0.0042, delta_1M_ATM=-0.0045,
            delta_3M_ATM=-0.0038, delta_6M_ATM=-0.0028,
            delta_1Y_ATM=-0.0020, delta_1M_25RR=-0.0015,
            delta_1M_25BF=-0.0008,
            predicted_at=datetime.now(),
            model_version="onnx"
        )
        
        return baseline, current, event, shock
    
    def test_attribution_summary_format(
        self,
        service,
        large_vega_spike_scenario
    ):
        """Test that attribution summary has correct format."""
        baseline, current, event, shock = large_vega_spike_scenario
        
        report = service.compute_attribution(
            baseline_greeks=baseline,
            current_greeks=current,
            vol_shock=shock,
            news_event=event,
            nn_model_mode="onnx"
        )
        
        vega_spike = report.vega_spike_report
        assert vega_spike is not None
        
        # Build attribution summary manually (same way API does)
        attribution_parts = []
        for factor in vega_spike.attribution_factors:
            attribution_parts.append(
                f"{factor.percentage}% of this move is attributed to {factor.source}"
            )
        
        summary = ", ".join(attribution_parts)
        
        # Verify the expected format
        assert "50%" in summary or "55%" in summary
        assert "ECB" in summary or "interest rate" in summary.lower()
        assert "historical vol drift" in summary
        assert "NN" in summary or "model" in summary
    
    def test_vega_spike_percentage_calculation(
        self,
        service,
        large_vega_spike_scenario
    ):
        """Test vega spike percentage is calculated correctly."""
        baseline, current, event, shock = large_vega_spike_scenario
        
        report = service.compute_attribution(
            baseline_greeks=baseline,
            current_greeks=current,
            vol_shock=shock,
            news_event=event,
            nn_model_mode="onnx"
        )
        
        vega_spike = report.vega_spike_report
        assert vega_spike is not None
        
        # $10K change on $100K baseline = 10%
        expected_pct = (10000.0 / 100000.0) * 100
        assert vega_spike.vega_spike_percentage == expected_pct
