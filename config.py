# config.py
"""
Configuration management for the risk system.
Supports both environment variables and .env files.
"""
import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Database configuration."""
    user: str = field(default_factory=lambda: os.getenv("DB_USER", "postgres"))
    password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", "postgres"))
    host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    database: str = field(default_factory=lambda: os.getenv("DB_NAME", "risk_system"))
    
    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class RedisConfig:
    """Redis configuration."""
    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    password: Optional[str] = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))


@dataclass
class NewsAPIConfig:
    """NewsAPI configuration."""
    api_key: str = field(default_factory=lambda: os.getenv("NEWSAPI_KEY", "9e5ef2fc98ce47deb0a86fbecb3f24f8"))
    base_url: str = "https://newsapi.org/v2"
    timeout: int = 30
    # Keywords to monitor
    keywords: list = field(default_factory=lambda: [
        "MAS", "central bank", "interest rate", "inflation", "CPI",
        "NFP", "employment", "Fed", "ECB", "FOMC", "USD", "currency"
    ])
    sources: list = field(default_factory=lambda: [
        "bloomberg", "reuters", "cnbc", "financial-times", "wall-street-journal"
    ])


@dataclass
class MLConfig:
    """Machine Learning configuration."""
    # NLP
    nlp_model: str = "ProsusAI/finbert"
    nlp_device: str = field(default_factory=lambda: os.getenv("NLP_DEVICE", "cpu"))
    
    # Vol Shock Model (Module 3)
    vol_model_path: str = field(default_factory=lambda: os.getenv("VOL_MODEL_PATH", "./models/vol_shock.pkl"))
    
    # NN Risk Engine (Module 5)
    risk_nn_model_path: str = field(default_factory=lambda: os.getenv("RISK_NN_PATH", "./models/risk_nn.onnx"))
    risk_nn_device: str = field(default_factory=lambda: os.getenv("RISK_NN_DEVICE", "cpu"))


@dataclass
class RiskLimits:
    """Risk limits for alerts."""
    vega_limit: float = field(default_factory=lambda: float(os.getenv("VEGA_LIMIT", "100000")))
    gamma_limit: float = field(default_factory=lambda: float(os.getenv("GAMMA_LIMIT", "50000")))
    delta_limit: float = field(default_factory=lambda: float(os.getenv("DELTA_LIMIT", "500000")))
    rho_limit: float = field(default_factory=lambda: float(os.getenv("RHO_LIMIT", "100000")))
    shock_threshold: float = field(default_factory=lambda: float(os.getenv("SHOCK_THRESHOLD", "0.01")))


@dataclass
class ForexConfig:
    """Forex API configuration for live spot rates."""
    api_key: str = field(default_factory=lambda: os.getenv("FOREX_API_KEY", ""))
    provider: str = field(default_factory=lambda: os.getenv("FOREX_PROVIDER", "alpha_vantage"))
    poll_interval: int = field(default_factory=lambda: int(os.getenv("FOREX_POLL_INTERVAL", "60")))
    timeout: int = 30


@dataclass
class SpotAlertConfig:
    """Spot rate alert configuration."""
    move_threshold_pct: float = field(default_factory=lambda: float(os.getenv("SPOT_MOVE_THRESHOLD", "0.1")))
    alert_interval_sec: int = field(default_factory=lambda: int(os.getenv("SPOT_ALERT_INTERVAL", "60")))
    max_alerts_per_hour: int = field(default_factory=lambda: int(os.getenv("SPOT_MAX_ALERTS_PER_HOUR", "10")))


@dataclass
class AppConfig:
    """Master configuration."""
    # Environment
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    
    # API
    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))
    
    # Components
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    news_api: NewsAPIConfig = field(default_factory=NewsAPIConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    forex_api: ForexConfig = field(default_factory=ForexConfig)
    spot_alert: SpotAlertConfig = field(default_factory=SpotAlertConfig)
    
    # Feature flags
    enable_news_ingestion: bool = field(default_factory=lambda: os.getenv("ENABLE_NEWS", "true").lower() == "true")
    enable_nlp_engine: bool = field(default_factory=lambda: os.getenv("ENABLE_NLP", "true").lower() == "true")
    enable_vol_shock: bool = field(default_factory=lambda: os.getenv("ENABLE_VOL_SHOCK", "true").lower() == "true")
    enable_alerts: bool = field(default_factory=lambda: os.getenv("ENABLE_ALERTS", "true").lower() == "true")
    enable_live_spot_rates: bool = field(default_factory=lambda: os.getenv("ENABLE_LIVE_SPOT", "true").lower() == "true")
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.news_api.api_key:
            logger.warning("NEWSAPI_KEY not set. News ingestion will be disabled.")
        
        if self.environment not in ["development", "staging", "production"]:
            raise ValueError(f"Invalid environment: {self.environment}")


# Singleton instance
config = AppConfig()
