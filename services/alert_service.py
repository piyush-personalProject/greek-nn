# services/alert_service.py
"""
Alert Service for Spot Rate and Risk Alerts.
Monitors spot rate movements and generates alerts when thresholds are exceeded.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque

from config import config
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class SpotRateAlert:
    """Alert for spot rate movement."""
    alert_id: str
    pair: str
    alert_type: str  # "move", "spike", "trend"
    current_rate: float
    baseline_rate: float
    change_pct: float
    threshold_pct: float
    timestamp: datetime
    message: str


@dataclass
class RiskAlert:
    """Risk limit breach alert."""
    alert_id: str
    alert_type: str  # "greek_limit", "spot_alert", etc.
    greek_name: str  # Name of the greek that breached (delta, vega, gamma, rho)
    severity: str  # "low", "medium", "high"
    title: str
    message: str
    current_value: float
    threshold_value: float
    timestamp: datetime
    acknowledged: bool = False


class AlertService:
    """
    Service for managing alerts from various sources:
    - Spot rate movements
    - Risk limit breaches
    - Vol surface anomalies
    """
    
    def __init__(
        self,
        spot_move_threshold_pct: float = 0.5,
        alert_cooldown_sec: int = 300,
        max_alerts_per_hour: int = 10
    ):
        """
        Initialize Alert Service.
        
        Args:
            spot_move_threshold_pct: Percentage change to trigger alert
            alert_cooldown_sec: Minimum seconds between alerts for same pair
            max_alerts_per_hour: Rate limit for alerts
        """
        self.spot_move_threshold_pct = spot_move_threshold_pct
        self.alert_cooldown = timedelta(seconds=alert_cooldown_sec)
        self.max_alerts_per_hour = max_alerts_per_hour
        
        # Store recent alerts (max 1000)
        self._spot_alerts: deque = deque(maxlen=1000)
        self._risk_alerts: deque = deque(maxlen=1000)
        
        # Track last alert time per pair
        self._last_alert_times: Dict[str, datetime] = {}
        
        # Track alert counts for rate limiting
        self._alert_timestamps: deque = deque(maxlen=max_alerts_per_hour * 2)
        
        logger.info(
            f"AlertService initialized with threshold={spot_move_threshold_pct}%, "
            f"cooldown={alert_cooldown_sec}s"
        )
    
    def check_spot_rate_alert(
        self,
        pair: str,
        current_rate: float,
        baseline_rate: float
    ) -> Optional[SpotRateAlert]:
        """
        Check if a spot rate movement warrants an alert.
        
        Args:
            pair: Currency pair
            current_rate: Current spot rate
            baseline_rate: Baseline/reference rate
            
        Returns:
            SpotRateAlert if threshold exceeded, None otherwise
        """
        if not baseline_rate or baseline_rate == 0:
            return None
        
        # Calculate percentage change
        change_pct = abs(((current_rate - baseline_rate) / baseline_rate) * 100)
        
        # Check if change exceeds threshold
        if change_pct < self.spot_move_threshold_pct:
            logger.debug(f"Alert check: {pair} change_pct={change_pct:.4f}% < threshold={self.spot_move_threshold_pct}%, no alert")
            return None
        
        logger.info(f"Alert check: {pair} change_pct={change_pct:.4f}% >= threshold={self.spot_move_threshold_pct}%, checking cooldown/rate limit")
        
        # Check cooldown period
        last_alert = self._last_alert_times.get(pair)
        if last_alert and (datetime.now() - last_alert) < self.alert_cooldown:
            logger.debug(f"Alert suppressed for {pair} due to cooldown")
            return None
        
        # Check rate limiting
        cutoff = datetime.now() - timedelta(hours=1)
        recent_alerts = [t for t in self._alert_timestamps if t > cutoff]
        if len(recent_alerts) >= self.max_alerts_per_hour:
            logger.warning("Alert rate limit reached, suppressing alert")
            return None
        
        logger.info(f"Alert check: {pair} passed cooldown/rate limit checks, creating alert")
        
        # Determine alert type and message
        direction = "up" if current_rate > baseline_rate else "down"
        alert_type = "spike" if change_pct > self.spot_move_threshold_pct * 2 else "move"
        
        message = (
            f"{pair} moved {direction} {change_pct:.2f}% "
            f"({baseline_rate:.5f} → {current_rate:.5f})"
        )
        
        # Create alert
        alert = SpotRateAlert(
            alert_id=f"spot-{pair}-{int(datetime.now().timestamp())}",
            pair=pair,
            alert_type=alert_type,
            current_rate=current_rate,
            baseline_rate=baseline_rate,
            change_pct=change_pct,
            threshold_pct=self.spot_move_threshold_pct,
            timestamp=datetime.now(),
            message=message
        )
        
        # Store and track
        self._spot_alerts.append(alert)
        self._last_alert_times[pair] = datetime.now()
        self._alert_timestamps.append(datetime.now())
        
        logger.info(f"Spot rate alert created: {message}")
        
        return alert
    
    def check_greek_alert(
        self,
        greek_name: str,
        current_value: float,
        limit_value: float,
        portfolio_id: str = "FX-PORTFOLIO-01"
    ) -> Optional[RiskAlert]:
        """
        Check if a Greek risk limit has been breached.
        
        Args:
            greek_name: Name of Greek (delta, vega, gamma, etc.)
            current_value: Current Greek value
            limit_value: Limit threshold
            portfolio_id: Portfolio identifier
            
        Returns:
            RiskAlert if limit exceeded, None otherwise
        """
        # Check if exceeded (using absolute value)
        if abs(current_value) <= abs(limit_value):
            return None
        
        exceeded_by = current_value - limit_value
        severity = self._determine_severity(abs(exceeded_by), abs(limit_value))
        
        alert = RiskAlert(
            alert_id=f"risk-{greek_name}-{int(datetime.now().timestamp())}",
            alert_type="greek_limit",
            greek_name=greek_name,
            severity=severity,
            title=f"{greek_name.upper()} Limit Breached",
            message=(
                f"Portfolio {portfolio_id}: {greek_name.upper()} is {abs(exceeded_by):.2f} "
                f"({'above' if exceeded_by > 0 else 'below'}) limit of {limit_value:.2f}"
            ),
            current_value=current_value,
            threshold_value=limit_value,
            timestamp=datetime.now()
        )
        
        self._risk_alerts.append(alert)
        logger.warning(f"Risk alert: {alert.message}")
        
        return alert
    
    def _determine_severity(self, exceeded_by: float, limit: float) -> str:
        """Determine alert severity based on how much limit is exceeded."""
        ratio = exceeded_by / limit if limit != 0 else 0
        
        if ratio > 1.0:  # More than 100% over limit
            return "high"
        elif ratio > 0.5:  # More than 50% over limit
            return "medium"
        else:
            return "low"
    
    def get_spot_alerts(
        self,
        pair: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 50
    ) -> List[SpotRateAlert]:
        """
        Get recent spot rate alerts.
        
        Args:
            pair: Filter by specific pair
            since: Only alerts after this time
            limit: Maximum number of alerts
            
        Returns:
            List of SpotRateAlert
        """
        alerts = list(self._spot_alerts)
        
        if pair:
            alerts = [a for a in alerts if a.pair == pair]
        
        if since:
            alerts = [a for a in alerts if a.timestamp > since]
        
        return sorted(alerts, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    def get_risk_alerts(
        self,
        alert_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 50
    ) -> List[RiskAlert]:
        """
        Get recent risk alerts.
        
        Args:
            alert_type: Filter by alert type
            since: Only alerts after this time
            limit: Maximum number of alerts
            
        Returns:
            List of RiskAlert
        """
        alerts = list(self._risk_alerts)
        
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
        
        if since:
            alerts = [a for a in alerts if a.timestamp > since]
        
        return sorted(alerts, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    def get_all_alerts(
        self,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> Dict[str, List]:
        """
        Get all alerts combined.
        
        Returns:
            Dict with 'spot_alerts' and 'risk_alerts' keys
        """
        spot = self.get_spot_alerts(since=since, limit=limit)
        risk = self.get_risk_alerts(since=since, limit=limit)
        return {
            "spot_alerts": spot,
            "risk_alerts": risk,
            "total_count": len(spot) + len(risk),
            "timestamp": datetime.now().isoformat()
        }
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge an alert.
        
        Args:
            alert_id: ID of alert to acknowledge
            
        Returns:
            True if acknowledged, False if not found
        """
        for alert in self._risk_alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def clear_old_alerts(self, older_than_hours: int = 24) -> int:
        """
        Clear alerts older than specified hours.
        
        Args:
            older_than_hours: Remove alerts older than this
            
        Returns:
            Number of alerts cleared
        """
        cutoff = datetime.now() - timedelta(hours=older_than_hours)
        
        initial_count = len(self._spot_alerts) + len(self._risk_alerts)
        
        # Filter out old alerts
        self._spot_alerts = deque(
            [a for a in self._spot_alerts if a.timestamp > cutoff],
            maxlen=1000
        )
        self._risk_alerts = deque(
            [a for a in self._risk_alerts if a.timestamp > cutoff],
            maxlen=1000
        )
        
        cleared = initial_count - (len(self._spot_alerts) + len(self._risk_alerts))
        logger.info(f"Cleared {cleared} old alerts")
        
        return cleared
    
    def get_status(self) -> Dict:
        """Get service status."""
        cutoff = datetime.now() - timedelta(hours=1)
        recent_alerts = [t for t in self._alert_timestamps if t > cutoff]
        
        return {
            "service": "alert",
            "status": "healthy",
            "total_spot_alerts": len(self._spot_alerts),
            "total_risk_alerts": len(self._risk_alerts),
            "alerts_last_hour": len(recent_alerts),
            "max_alerts_per_hour": self.max_alerts_per_hour
        }
    
    def health_check(self) -> Dict[str, str]:
        """Health check for the service."""
        return self.get_status()


# Global instance
_alert_service: Optional[AlertService] = None


def get_alert_service() -> AlertService:
    """Get the global alert service instance."""
    global _alert_service
    if _alert_service is None:
        _alert_service = AlertService(
            spot_move_threshold_pct=config.spot_alert.move_threshold_pct,
            alert_cooldown_sec=config.spot_alert.alert_interval_sec,
            max_alerts_per_hour=config.spot_alert.max_alerts_per_hour
        )
    return _alert_service


def init_alert_service(**kwargs) -> AlertService:
    """Initialize the global alert service."""
    global _alert_service
    _alert_service = AlertService(**kwargs)
    return _alert_service