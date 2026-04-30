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
