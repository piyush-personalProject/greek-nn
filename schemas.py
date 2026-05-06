# models/schemas.py
"""
Pydantic models and data classes for the risk system.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from enum import Enum
import numpy as np


class EventType(str, Enum):
    """Types of economic events."""
    INTEREST_RATE = "interest_rate"
    INFLATION = "inflation"
    EMPLOYMENT = "employment"
    CENTRAL_BANK = "central_bank"
    MACRO = "macro"
    TECHNICAL = "technical"
    UNKNOWN = "unknown"


class Sentiment(str, Enum):
    """Sentiment classification."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class NewsEvent(BaseModel):
    """News event from ingestion module."""
    headline: str
    source: str
    url: str
    published_at: datetime
    content: Optional[str] = None
    importance: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "headline": "Fed raises rates by 25bps",
                "source": "Bloomberg",
                "url": "https://example.com",
                "published_at": "2024-01-15T10:30:00Z"
            }
        }


class EventVector(BaseModel):
    """Structured event representation from NLP module."""
    event_id: str
    headline: str
    event_type: EventType
    sentiment: Sentiment
    sentiment_score: float = Field(ge=-1, le=1)
    importance: float = Field(ge=0, le=1)
    surprise_factor: float = Field(ge=0, le=1)
    entities: Dict[str, List[str]] = Field(default_factory=dict)
    processed_at: datetime
    source: str


class VolShock(BaseModel):
    """Volatility shock from shock model."""
    shock_id: str
    event_vector: EventVector
    affected_pairs: List[str] = Field(default_factory=list, description="Currency pairs affected by this shock")
    delta_1W_ATM: float
    delta_1M_ATM: float
    delta_3M_ATM: float
    delta_6M_ATM: float
    delta_1Y_ATM: float
    delta_1M_25RR: float
    delta_1M_25BF: float
    predicted_at: datetime
    model_version: str


class VolSurface(BaseModel):
    """Volatility surface snapshot."""
    snapshot_id: str
    base_date: datetime
    tenors: List[float]  # in years
    strikes: List[float]  # ATM, RR, BF
    volatilities: List[List[float]]  # shape: (len(tenors), len(strikes))
    source: str
    version: str
    
    model_config = {"arbitrary_types_allowed": True}


class PortfolioPosition(BaseModel):
    """Single position in portfolio."""
    position_id: str
    instrument: str
    spot: float = Field(gt=0)
    strike: float = Field(gt=0)
    tenor: float = Field(gt=0)  # in years
    quantity: float
    option_type: str  # CALL, PUT
    portfolio_id: str


class Portfolio(BaseModel):
    """Portfolio snapshot."""
    portfolio_id: str
    timestamp: datetime
    positions: List[PortfolioPosition]
    base_currency: str = "USD"


class Greeks(BaseModel):
    """Greek risk measures."""
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    vanna: Optional[float] = None
    volga: Optional[float] = None
    
    def __add__(self, other: "Greeks") -> "Greeks":
        """Add two Greeks."""
        return Greeks(
            delta=self.delta + other.delta,
            gamma=self.gamma + other.gamma,
            vega=self.vega + other.vega,
            theta=self.theta + other.theta,
            rho=self.rho + other.rho,
            vanna=self._safe_add(self.vanna, other.vanna),
            volga=self._safe_add(self.volga, other.volga),
        )
    
    @staticmethod
    def _safe_add(a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None or b is None:
            return None
        return a + b
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "delta": self.delta,
            "gamma": self.gamma,
            "vega": self.vega,
            "theta": self.theta,
            "rho": self.rho,
            "vanna": self.vanna,
            "volga": self.volga,
        }


class PortfolioGreeks(BaseModel):
    """Portfolio Greeks."""
    portfolio_id: str
    timestamp: datetime
    vol_surface_version: str
    total_greeks: Greeks
    position_greeks: Dict[str, Greeks]


class RiskAlert(BaseModel):
    """Risk alert when limits breached."""
    alert_id: str
    portfolio_id: str
    timestamp: datetime
    risk_type: str  # vega, gamma, delta, etc.
    current_value: float
    limit_value: float
    exceeded_by: float
    event: EventVector
    action_recommended: str


class RiskLog(BaseModel):
    """Log entry for risk computation."""
    log_id: str
    portfolio_id: str
    timestamp: datetime
    event_vector: Optional[EventVector] = None
    vol_shock: Optional[VolShock] = None
    portfolio_greeks: PortfolioGreeks
    alerts: List[RiskAlert] = Field(default_factory=list)
    computation_time_ms: float
    status: str = "success"
    error_message: Optional[str] = None


# API Request/Response schemas

class ComputeRiskRequest(BaseModel):
    """Request to compute portfolio risk."""
    portfolio_id: str
    positions: List[PortfolioPosition]
    spot_rates: Dict[str, float]
    vol_surface_version: Optional[str] = None


class ComputeRiskResponse(BaseModel):
    """Response from risk computation."""
    portfolio_id: str
    timestamp: datetime
    greeks: Greeks
    position_greeks: Dict[str, Greeks]
    alerts: List[RiskAlert] = Field(default_factory=list)
    computation_time_ms: float


class HealthCheck(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    components: Dict[str, str]


class TradeCreate(BaseModel):
    """Request to create a new trade."""
    instrument: str
    strike: float = Field(gt=0)
    tenor: float = Field(gt=0)
    quantity: float
    option_type: str
    portfolio_id: str = "FX-PORTFOLIO-01"


class GreeksImpactWeights(BaseModel):
    """
    Weighting parameters for calculating impacted Greeks.
    
    Allows blending between:
    - Base state (spot_rate_weight=1, vol_shock_weight=0)
    - Full shock state (spot_rate_weight=0, vol_shock_weight=1)  
    - Blended state (any combination that sums to 1)
    
    Example:
        spot_rate_weight=0.7, vol_shock_weight=0.3 means:
        70% weight to live spot rate, 30% weight to shocked vol surface
    """
    spot_rate_weight: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Weight for live spot rate (0=no weight, 1=full weight)"
    )
    vol_shock_weight: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Weight for vol shock impact (0=no weight, 1=full weight)"
    )
    spot_shock_weight: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Weight for spot shock impact (0=no weight, 1=full weight)"
    )
    
    @validator("vol_shock_weight")
    def validate_weights(cls, v, values):
        """Ensure weights are non-negative."""
        return max(0.0, min(1.0, v))
    
    def to_blend_factors(self) -> Tuple[float, float, float]:
        """
        Get normalized blend factors for Greeks calculation.
        
        Returns:
            Tuple of (spot_factor, vol_shock_factor, spot_shock_factor)
            These factors are used to blend: base_greeks * spot_factor + shocked_greeks * vol_shock_factor + spot_shocked_greeks * spot_shock_factor
        """
        # Normalize so they represent proportions
        total = self.spot_rate_weight + self.vol_shock_weight + self.spot_shock_weight
        if total == 0:
            return (0.0, 0.0, 0.0)
        
        # For now, treat spot_rate_weight as inverse of vol_shock_weight
        # i.e. if spot_rate_weight=0.7 and vol_shock_weight=0.3, we blend 30% shocked vol
        # But the spot_rate_weight is more about which spot to use (live vs shocked)
        spot_factor = self.spot_rate_weight
        vol_shock_factor = self.vol_shock_weight
        spot_shock_factor = self.spot_shock_weight
        
        return (spot_factor, vol_shock_factor, spot_shock_factor)
    
    @classmethod
    def compute_dynamic_weights(
        cls,
        news_importance: float = 0.5,
        news_sentiment_score: float = 0.0,
        spot_rate_change_pct: float = 0.0,
        base_spot_rate: float = 1.0
    ) -> "GreeksImpactWeights":
        """
        Compute dynamic weights based on news characteristics and spot rate movement.
        
        This method calculates optimal blending weights by considering:
        1. News importance (higher importance → more weight to vol shock)
        2. News sentiment (strong sentiment → more weight to vol shock)
        3. Spot rate movement (larger move → more weight to spot shock)
        
        The formula balances:
        - Vol shock impact from news events (importance-driven)
        - Spot rate impact from market movement
        
        Args:
            news_importance: News importance score (0-1)
            news_sentiment_score: News sentiment score (-1 to 1)
            spot_rate_change_pct: Spot rate change percentage (e.g., 0.5 for 0.5% move)
            base_spot_rate: Base spot rate for normalization
            
        Returns:
            GreeksImpactWeights with computed dynamic weights
        """
        # Normalize spot change to a 0-1 scale
        # A 1% move is considered significant, so we cap at 1%
        normalized_spot_change = min(abs(spot_rate_change_pct) / 1.0, 1.0)
        
        # Calculate vol shock weight based on news importance and sentiment strength
        # Strong sentiment amplifies the importance effect
        sentiment_strength = abs(news_sentiment_score)
        vol_shock_factor = news_importance * (0.5 + 0.5 * sentiment_strength)
        
        # Calculate spot shock weight based on rate movement
        spot_shock_factor = normalized_spot_change * 0.8  # Scale down to avoid over-weighting
        
        # Spot rate weight is the remainder
        spot_rate_weight = max(0.0, 1.0 - vol_shock_factor - spot_shock_factor)
        
        # Ensure all weights are valid and normalize if needed
        total = spot_rate_weight + vol_shock_factor + spot_shock_factor
        if total > 1.0:
            # Normalize to ensure weights sum to 1
            scale = 1.0 / total
            spot_rate_weight *= scale
            vol_shock_factor *= scale
            spot_shock_factor *= scale
        
        return cls(
            spot_rate_weight=round(spot_rate_weight, 4),
            vol_shock_weight=round(vol_shock_factor, 4),
            spot_shock_weight=round(spot_shock_factor, 4)
        )
    
    @classmethod
    def from_news_and_spot(
        cls,
        event_vector_importance: float,
        event_vector_sentiment_score: float,
        pair_spot_change_pct: float,
        pair_baseline_rate: float = 1.0
    ) -> "GreeksImpactWeights":
        """
        Convenience method to create weights from an event vector and spot rate change.
        
        Args:
            event_vector_importance: EventVector.importance (0-1)
            event_vector_sentiment_score: EventVector.sentiment_score (-1 to 1)
            pair_spot_change_pct: Spot rate change percentage for the pair
            pair_baseline_rate: Baseline spot rate
        """
        return cls.compute_dynamic_weights(
            news_importance=event_vector_importance,
            news_sentiment_score=event_vector_sentiment_score,
            spot_rate_change_pct=pair_spot_change_pct,
            base_spot_rate=pair_baseline_rate
        )


# ==================== Spot Rate Schemas ====================

class SpotRate(BaseModel):
    """Single spot rate for a currency pair."""
    pair: str = Field(..., description="Currency pair (e.g., EURUSD)")
    rate: float = Field(..., description="Current spot rate")
    timestamp: datetime = Field(default_factory=datetime.now, description="When rate was fetched")
    source: str = Field(default="forex_api", description="Data source")


class SpotRateResponse(BaseModel):
    """Response for spot rate queries."""
    timestamp: datetime
    rates: Dict[str, float]
    is_stale: bool = False
    source: str = "mock"


class SpotRateChange(BaseModel):
    """Change in spot rate from baseline."""
    pair: str
    current: float
    baseline: float
    change_pct: float
    direction: str  # "up", "down", "unchanged"


class SpotRateHistoryItem(BaseModel):
    """Historical spot rate data point."""
    date: str
    open: float
    high: float
    low: float
    close: float


# ==================== Alert Schemas ====================

class SpotRateAlertData(BaseModel):
    """Spot rate alert data."""
    alert_id: str
    pair: str
    alert_type: str  # "move", "spike", "trend"
    current_rate: float
    baseline_rate: float
    change_pct: float
    threshold_pct: float
    timestamp: datetime
    message: str


class RiskAlertData(BaseModel):
    """Risk limit breach alert."""
    alert_id: str
    alert_type: str  # "greek_limit", "spot_alert", etc.
    severity: str  # "low", "medium", "high"
    title: str
    message: str
    current_value: float
    threshold_value: float
    timestamp: datetime
    acknowledged: bool = False


class AlertsResponse(BaseModel):
    """Response containing all alerts."""
    timestamp: datetime
    spot_alerts: List[SpotRateAlertData] = Field(default_factory=list)
    risk_alerts: List[RiskAlertData] = Field(default_factory=list)
    total_count: int = 0


# ==================== Combined Impact Schemas ====================

class CombinedImpactRequest(BaseModel):
    """Request for combined spot + vol shock impact."""
    portfolio_id: str = "FX-PORTFOLIO-01"
    weights: Optional[GreeksImpactWeights] = Field(
        default=None,
        description="Blending weights (defaults to vol_shock_weight=1.0)"
    )
    include_history: bool = Field(
        default=False,
        description="Include spot rate history in response"
    )


class SpotImpactData(BaseModel):
    """Spot rate impact on Greeks."""
    pair: str
    rate_change_pct: float
    estimated_delta_impact: float
    estimated_gamma_impact: float


class CombinedImpactResponse(BaseModel):
    """Response with combined spot and vol shock impact."""
    timestamp: datetime
    portfolio_id: str
    weights: GreeksImpactWeights
    baseline_greeks: Greeks
    current_greeks: Greeks
    greeks_delta: Greeks
    spot_impacts: List[SpotImpactData] = Field(default_factory=list)
    vol_shock_impacts: List[Dict] = Field(default_factory=list)
    combined_impact: Greeks
