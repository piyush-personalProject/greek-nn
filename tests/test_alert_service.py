# tests/test_alert_service.py
"""
Tests for the Alert Service.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock


class TestAlertService:
    """Test cases for AlertService."""

    @pytest.fixture
    def alert_service(self):
        """Create an AlertService instance for testing."""
        from services.alert_service import AlertService
        return AlertService(
            spot_move_threshold_pct=0.5,
            alert_cooldown_sec=300,
            max_alerts_per_hour=10
        )

    def test_initialization(self, alert_service):
        """Test AlertService initializes correctly."""
        assert alert_service.spot_move_threshold_pct == 0.5
        assert alert_service.alert_cooldown == timedelta(seconds=300)
        assert alert_service.max_alerts_per_hour == 10
        assert len(alert_service._spot_alerts) == 0
        assert len(alert_service._risk_alerts) == 0

    def test_check_spot_rate_alert_below_threshold(self, alert_service):
        """Test alert not triggered when change is below threshold."""
        alert = alert_service.check_spot_rate_alert(
            pair="EURUSD",
            current_rate=1.0855,  # 0.05% change - below 0.5%
            baseline_rate=1.0850
        )
        
        assert alert is None
        assert len(alert_service._spot_alerts) == 0

    def test_check_spot_rate_alert_above_threshold(self, alert_service):
        """Test alert triggered when change exceeds threshold."""
        alert = alert_service.check_spot_rate_alert(
            pair="EURUSD",
            current_rate=1.0900,  # ~0.46% change - above 0.5%
            baseline_rate=1.0850
        )
        
        assert alert is not None
        assert alert.pair == "EURUSD"
        assert alert.alert_type == "move"
        assert len(alert_service._spot_alerts) == 1

    def test_check_spot_rate_alert_spike(self, alert_service):
        """Test spike alert when change is 2x threshold."""
        alert = alert_service.check_spot_rate_alert(
            pair="EURUSD",
            current_rate=1.1000,  # ~1.38% change - above 1.0% (2x threshold)
            baseline_rate=1.0850
        )
        
        assert alert is not None
        assert alert.alert_type == "spike"
        assert alert.change_pct > 1.0

    def test_check_spot_rate_alert_cooldown(self, alert_service):
        """Test alert is suppressed during cooldown period."""
        # First alert should trigger
        alert1 = alert_service.check_spot_rate_alert(
            pair="EURUSD",
            current_rate=1.0900,
            baseline_rate=1.0850
        )
        assert alert1 is not None
        
        # Second alert for same pair should be suppressed (cooldown)
        alert2 = alert_service.check_spot_rate_alert(
            pair="EURUSD",
            current_rate=1.0950,
            baseline_rate=1.0850
        )
        assert alert2 is None
        
        # But different pair should work
        alert3 = alert_service.check_spot_rate_alert(
            pair="USDJPY",
            current_rate=150.50,
            baseline_rate=149.00
        )
        assert alert3 is not None

    def test_check_greek_alert_below_limit(self, alert_service):
        """Test risk alert not triggered when below limit."""
        alert = alert_service.check_greek_alert(
            greek_name="vega",
            current_value=50000,  # Below limit
            limit_value=100000
        )
        
        assert alert is None
        assert len(alert_service._risk_alerts) == 0

    def test_check_greek_alert_above_limit(self, alert_service):
        """Test risk alert triggered when above limit."""
        alert = alert_service.check_greek_alert(
            greek_name="vega",
            current_value=120000,  # Above limit
            limit_value=100000
        )
        
        assert alert is not None
        assert alert.alert_type == "greek_limit"
        assert alert.greek_name == "vega"
        assert alert.severity in ["low", "medium", "high"]
        assert len(alert_service._risk_alerts) == 1

    def test_get_spot_alerts(self, alert_service):
        """Test retrieving spot alerts."""
        # Create some alerts
        alert_service.check_spot_rate_alert("EURUSD", 1.0900, 1.0850)
        alert_service.check_spot_rate_alert("USDJPY", 150.50, 149.50)
        
        alerts = alert_service.get_spot_alerts()
        assert len(alerts) == 2
        
        # Filter by pair
        eur_alerts = alert_service.get_spot_alerts(pair="EURUSD")
        assert len(eur_alerts) == 1
        assert eur_alerts[0].pair == "EURUSD"

    def test_get_spot_alerts_with_time_filter(self, alert_service):
        """Test filtering alerts by time."""
        # Create an alert
        alert_service.check_spot_rate_alert("EURUSD", 1.0900, 1.0850)
        
        # Get alerts since now (should include it)
        alerts = alert_service.get_spot_alerts(since=datetime.now() - timedelta(minutes=5))
        assert len(alerts) == 1
        
        # Get alerts since future (should be empty)
        alerts = alert_service.get_spot_alerts(since=datetime.now() + timedelta(minutes=5))
        assert len(alerts) == 0

    def test_acknowledge_alert(self, alert_service):
        """Test acknowledging an alert."""
        alert_service.check_greek_alert("vega", 120000, 100000)
        
        assert len(alert_service._risk_alerts) == 1
        alert_id = alert_service._risk_alerts[0].alert_id
        
        success = alert_service.acknowledge_alert(alert_id)
        assert success == True
        assert alert_service._risk_alerts[0].acknowledged == True

    def test_acknowledge_alert_not_found(self, alert_service):
        """Test acknowledging non-existent alert."""
        success = alert_service.acknowledge_alert("non-existent-id")
        assert success == False

    def test_get_all_alerts(self, alert_service):
        """Test getting all alerts combined."""
        alert_service.check_spot_rate_alert("EURUSD", 1.0900, 1.0850)
        alert_service.check_greek_alert("vega", 120000, 100000)
        
        result = alert_service.get_all_alerts()
        
        assert "spot_alerts" in result
        assert "risk_alerts" in result
        assert len(result["spot_alerts"]) == 1
        assert len(result["risk_alerts"]) == 1
        assert result["total_count"] == 2

    def test_clear_old_alerts(self, alert_service):
        """Test clearing old alerts."""
        # Create an alert (should have current timestamp)
        alert_service.check_spot_rate_alert("EURUSD", 1.0900, 1.0850)
        
        # Clear with 24 hour threshold (should not remove recent alert)
        cleared = alert_service.clear_old_alerts(older_than_hours=24)
        assert cleared == 0
        assert len(alert_service._spot_alerts) == 1
        
        # Clear with 0 hour threshold (should remove it)
        cleared = alert_service.clear_old_alerts(older_than_hours=0)
        assert cleared == 1
        assert len(alert_service._spot_alerts) == 0

    def test_get_status(self, alert_service):
        """Test status reporting."""
        alert_service.check_spot_rate_alert("EURUSD", 1.0900, 1.0850)
        
        status = alert_service.get_status()
        
        assert status["service"] == "alert"
        assert status["status"] == "healthy"
        assert status["total_spot_alerts"] == 1
        assert status["total_risk_alerts"] == 0

    def test_determine_severity(self, alert_service):
        """Test severity determination."""
        # Low severity - 50-100% over limit
        severity = alert_service._determine_severity(60000, 100000)
        assert severity == "medium"
        
        # High severity - >100% over limit
        severity = alert_service._determine_severity(250000, 100000)
        assert severity == "high"


class TestAlertServiceRateLimiting:
    """Test AlertService rate limiting."""

    def test_max_alerts_per_hour(self):
        """Test max alerts per hour rate limiting."""
        from services.alert_service import AlertService
        service = AlertService(
            spot_move_threshold_pct=0.5,
            alert_cooldown_sec=0,  # No cooldown
            max_alerts_per_hour=3
        )
        
        # Create 3 alerts (at limit)
        for i in range(3):
            service.check_spot_rate_alert("PAIR1", 1.0 + i*0.01, 1.0)
        
        assert len(service._spot_alerts) == 3
        
        # 4th alert should be suppressed due to rate limit
        alert = service.check_spot_rate_alert("PAIR4", 1.05, 1.0)
        assert alert is None
        assert len(service._spot_alerts) == 3  # Still 3, not 4