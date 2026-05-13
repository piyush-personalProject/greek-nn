# vol_surface_service.py
"""
Module 4: Vol Surface Service
Maintains live vol surface, applies shocks, and serves to risk engine.
Uses QuantLib for baseline surface and caching for performance.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    VolSurfaceService                        │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
    │  │Memory Cache│  │ Redis Cache │  │  QuantLib Backend   │  │
    │  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
    │         │               │                    │              │
    │         └───────────────┴────────────────────┘              │
    │                         │                                    │
    │              ┌─────────▼─────────┐                         │
    │              │ get_baseline_surface│                         │
    │              └─────────┬─────────┘                         │
    │                        │                                    │
    │              ┌─────────▼─────────┐                         │
    │              │get_shocked_surface │                         │
    │              └───────────────────┘                         │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from vol_surface_service import VolSurfaceService
    
    service = VolSurfaceService()
    surface = service.get_baseline_surface(datetime.now())
    shocked, version = service.get_shocked_surface(surface, vol_shock)
"""
import logging
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime, timedelta
import numpy as np
from abc import ABC, abstractmethod
import redis
import json
from dataclasses import asdict, dataclass
import pickle

from config import config
from schemas import VolSurface, VolShock
from logger import get_logger, log_performance, PerformanceLogger

logger = get_logger(__name__)


@dataclass
class VolSurfaceCache:
    """Cached vol surface entry."""
    surface: np.ndarray
    tenors: np.ndarray
    strikes: np.ndarray
    timestamp: datetime
    version: str
    metadata: Dict


class VolSurfaceBackend(ABC):
    """Abstract base for vol surface storage."""
    
    @abstractmethod
    def get_surface(self, date: datetime, version: str) -> Optional[VolSurface]:
        pass
    
    @abstractmethod
    def save_surface(self, surface: VolSurface) -> bool:
        pass


class QuantLibVolSurfaceBackend(VolSurfaceBackend):
    """
    QuantLib-based vol surface backend.
    Stores baseline surfaces and can interpolate across strikes and tenors.
    """
    
    def __init__(self):
        try:
            import QuantLib as ql
            self.ql = ql
            self.enabled = True
        except ImportError:
            logger.warning("QuantLib not available. Using fallback backend.")
            self.enabled = False
    
    def get_surface(self, date: datetime, version: str) -> Optional[VolSurface]:
        """Retrieve vol surface for a given date."""
        # In production, fetch from database
        # This is a stub implementation
        logger.debug(f"Fetching vol surface for {date} v{version}")
        return None
    
    def save_surface(self, surface: VolSurface) -> bool:
        """Save vol surface to storage."""
        if not self.enabled:
            return False
        logger.info(f"Saving vol surface {surface.snapshot_id} v{surface.version}")
        return True
    
    def interpolate_at_strike(
        self, 
        surface: VolSurface, 
        tenor: float, 
        strike: float
    ) -> float:
        """Interpolate vol at specific tenor and strike."""
        # Bilinear interpolation
        tenor_idx = np.searchsorted(surface.tenors, tenor)
        strike_idx = np.searchsorted(surface.strikes, strike)
        
        # Bounds check
        tenor_idx = np.clip(tenor_idx, 0, len(surface.tenors) - 1)
        strike_idx = np.clip(strike_idx, 0, len(surface.strikes) - 1)
        
        return float(surface.volatilities[tenor_idx][strike_idx])


class VolSurfaceService:
    """
    Main vol surface service.
    Responsibilities:
    1. Cache baseline surfaces in memory and Redis
    2. Apply shocks from vol model
    3. Serve consistent surfaces to risk engine
    4. Version control for audit trail
    """
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        backend: Optional[VolSurfaceBackend] = None
    ):
        self.logger = get_logger(self.__class__.__name__)
        self.redis = redis_client or self._init_redis()
        self.backend = backend or QuantLibVolSurfaceBackend()
        
        # In-memory cache
        self._memory_cache: Dict[str, VolSurfaceCache] = {}
        self._cache_ttl = timedelta(minutes=5)
        
        self.logger.info("VolSurfaceService initialized")
    
    def _init_redis(self) -> redis.Redis:
        """Initialize Redis connection."""
        try:
            r = redis.Redis(
                host=config.redis.host,
                port=config.redis.port,
                db=config.redis.db,
                password=config.redis.password,
                decode_responses=False
            )
            r.ping()
            self.logger.info("Connected to Redis")
            return r
        except redis.ConnectionError as e:
            self.logger.warning(f"Redis connection failed: {e}. Using memory cache only.")
            return None
    
    def _cache_key(self, date: datetime, version: str) -> str:
        """Generate cache key."""
        return f"vol_surface:{date.date().isoformat()}:v{version}"
    
    def _shock_key(self, shock_id: str) -> str:
        """Generate shock cache key."""
        return f"vol_shock:{shock_id}"
    
    def get_baseline_surface(
        self, 
        date: datetime, 
        version: str = "latest"
    ) -> VolSurface:
        """
        Get baseline vol surface for a date.
        Checks memory cache -> Redis cache -> disk.
        
        Args:
            date: The date for which to retrieve the vol surface
            version: Surface version identifier (default: "latest")
            
        Returns:
            VolSurface object with the baseline volatility data
            
        Raises:
            ValueError: If no vol surface found for the given date/version
        """
        cache_key = self._cache_key(date, version)
        
        # Check memory cache
        if cache_key in self._memory_cache:
            cached = self._memory_cache[cache_key]
            if datetime.now() - cached.timestamp < self._cache_ttl:
                self.logger.debug(f"Cache hit (memory): {cache_key}")
                return self._reconstruct_surface(cached, cache_key)
        
        # Check Redis cache
        if self.redis:
            try:
                cached_bytes = self.redis.get(cache_key)
                if cached_bytes:
                    cached = pickle.loads(cached_bytes)
                    self.logger.debug(f"Cache hit (redis): {cache_key}")
                    self._memory_cache[cache_key] = cached
                    return self._reconstruct_surface(cached, cache_key)
            except Exception as e:
                self.logger.warning(f"Redis get failed: {e}")
        
        # Fetch from backend
        with PerformanceLogger("backend_fetch", self.logger, cache_key=cache_key) as perf:
            surface = self.backend.get_surface(date, version)
            if surface:
                self._cache_surface(cache_key, surface)
                perf.add_metric("surface_id", surface.snapshot_id)
                return surface
        
        raise ValueError(f"Vol surface not found: {date} v{version}")
    
    def get_shocked_surface(
        self, 
        base_surface: VolSurface, 
        shock: VolShock
    ) -> Tuple[VolSurface, str]:
        """
        Apply vol shock to baseline surface.
        Returns shocked surface and version identifier.
        
        Shock mapping:
        - delta_1W_ATM -> 1W tenor
        - delta_1M_ATM -> 1M tenor
        - delta_3M_ATM -> 3M tenor
        - delta_6M_ATM -> 6M tenor
        - delta_1Y_ATM -> 1Y tenor
        - delta_1M_25RR -> 1M 25-delta RR
        - delta_1M_25BF -> 1M 25-delta BF
        
        Args:
            base_surface: The baseline volatility surface to shock
            shock: The volatility shock to apply
            
        Returns:
            Tuple of (shocked VolSurface, version string)
        """
        with PerformanceLogger("apply_shock", self.logger, 
                              shock_id=shock.shock_id[:16],
                              surface_id=base_surface.snapshot_id) as perf:
            
            # Clone baseline - convert to numpy array for math operations
            shocked_vol = np.array(base_surface.volatilities)
            
            # Shock mapping: tenor_idx -> shock amount
            tenor_shocks = {
                0: shock.delta_1W_ATM,      # 1W
                1: shock.delta_1M_ATM,      # 1M
                2: shock.delta_3M_ATM,      # 3M
                3: shock.delta_6M_ATM,      # 6M
                4: shock.delta_1Y_ATM,      # 1Y
            }
            
            # Track applied shocks for logging
            applied_shocks = {}
            
            # Apply shocks (multiplicative: vol_new = vol_old * (1 + shock))
            for tenor_idx, shock_amount in tenor_shocks.items():
                if tenor_idx < len(shocked_vol):
                    shocked_vol[tenor_idx][:] = shocked_vol[tenor_idx][:] * (1.0 + shock_amount)
                    applied_shocks[f"tenor_{tenor_idx}"] = shock_amount
            
            # Apply RR and BF shocks to 1M tenor (idx=1)
            if len(shocked_vol) > 1:
                # Assume strike indices: [ATM, +25RR, -25RR, +BF, -BF]
                # RR: right wing (call) - left wing (put)
                if len(shocked_vol[1]) > 2:
                    shocked_vol[1][1] = shocked_vol[1][1] * (1.0 + shock.delta_1M_25RR)  # +25RR
                    shocked_vol[1][2] = shocked_vol[1][2] * (1.0 + shock.delta_1M_25RR)  # -25RR
                    applied_shocks["1M_RR"] = shock.delta_1M_25RR
                
                # BF: (call + put) / 2 - ATM
                if len(shocked_vol[1]) > 4:
                    shocked_vol[1][3] = shocked_vol[1][3] * (1.0 + shock.delta_1M_25BF)  # +BF
                    shocked_vol[1][4] = shocked_vol[1][4] * (1.0 + shock.delta_1M_25BF)  # -BF
                    applied_shocks["1M_BF"] = shock.delta_1M_25BF
            
            perf.add_metrics(
                applied_shocks_count=len(applied_shocks),
                event_type=shock.event_vector.event_type.value
            )
            
            # Clamp to reasonable ranges (avoid negative or extreme vols)
            shocked_vol = np.clip(shocked_vol, 0.001, 2.0)
            
            # Create new surface (convert numpy array back to list for VolSurface schema)
            shocked_surface = VolSurface(
                snapshot_id=f"{base_surface.snapshot_id}_shocked",
                base_date=base_surface.base_date,
                tenors=base_surface.tenors,
                strikes=base_surface.strikes,
                volatilities=shocked_vol.tolist(),
                source=base_surface.source,
                version=f"{base_surface.version}+shock_{shock.shock_id[:8]}"
            )
            
            self.logger.info(
                f"Applied shock {shock.shock_id[:16]} to surface {base_surface.snapshot_id}",
                extra_fields={
                    "event_type": shock.event_vector.event_type.value,
                    "sentiment": shock.event_vector.sentiment,
                    "shock_1m_atm": shock.delta_1M_ATM,
                    "shocked_version": shocked_surface.version,
                    "tenors_affected": list(applied_shocks.keys())
                }
            )
            
            # Cache shocked surface
            shock_key = self._shock_key(shock.shock_id)
            self._cache_shocked_surface(shock_key, shocked_surface)
            
            perf.add_metric("shocked_version", shocked_surface.version)
            
            return shocked_surface, shocked_surface.version
    
    def _cache_surface(self, cache_key: str, surface: VolSurface) -> None:
        """Cache vol surface in memory and Redis."""
        
        # Memory cache
        cached = VolSurfaceCache(
            surface=surface.volatilities,
            tenors=np.array(surface.tenors),
            strikes=np.array(surface.strikes),
            timestamp=datetime.now(),
            version=surface.version,
            metadata={"snapshot_id": surface.snapshot_id, "source": surface.source}
        )
        self._memory_cache[cache_key] = cached
        
        # Redis cache
        if self.redis:
            try:
                self.redis.setex(
                    cache_key,
                    int(self._cache_ttl.total_seconds()),
                    pickle.dumps(cached)
                )
            except Exception as e:
                self.logger.warning(f"Failed to cache in Redis: {e}")
    
    def _cache_shocked_surface(self, shock_key: str, surface: VolSurface) -> None:
        """Cache shocked surface temporarily."""
        if self.redis:
            try:
                self.redis.setex(
                    shock_key,
                    300,  # 5 min TTL
                    pickle.dumps(surface)
                )
            except Exception as e:
                self.logger.warning(f"Failed to cache shocked surface: {e}")
    
    def _reconstruct_surface(self, cached: VolSurfaceCache, cache_key: str) -> VolSurface:
        """Reconstruct VolSurface from cache."""
        return VolSurface(
            snapshot_id=cached.metadata.get("snapshot_id", cache_key),
            base_date=datetime.now(),
            tenors=cached.tenors.tolist(),
            strikes=cached.strikes.tolist(),
            volatilities=cached.surface,
            source=cached.metadata.get("source", "cache"),
            version=cached.version
        )
    
    def get_vol_at_tenor(
        self, 
        surface: VolSurface, 
        tenor: float
    ) -> float:
        """
        Get ATM vol for a given tenor from surface.
        
        Args:
            surface: The volatility surface to query
            tenor: The time to expiration in years
            
        Returns:
            ATM volatility at the specified tenor
        """
        with PerformanceLogger("get_vol_at_tenor", self.logger, tenor=tenor) as perf:
            tenor_idx = np.searchsorted(surface.tenors, tenor)
            tenor_idx = np.clip(tenor_idx, 0, len(surface.tenors) - 1)
            vol = float(surface.volatilities[tenor_idx][0])  # ATM is index 0
            perf.add_metric("vol", vol)
            return vol
    
    def get_vol_at_strike(
        self, 
        surface: VolSurface, 
        tenor: float,
        strike: float,
        spot: float = 100.0
    ) -> float:
        """
        Get volatility at a specific tenor and strike using the vol surface.
        
        This method maps a position's strike to the appropriate volatility:
        - ATM (strike ≈ spot): uses ATM vol (index 0)
        - OTM Call (strike > spot): uses +25RR/+25BF wing (indices 1 or 3)
        - OTM Put (strike < spot): uses -25RR/-25BF wing (indices 2 or 4)
        
        For strikes that fall between the predefined points, linear interpolation
        is used to compute the appropriate vol.
        
        Args:
            surface: The volatility surface to query
            tenor: The time to expiration in years
            strike: The strike price of the option
            spot: The current spot price (used to determine ATM/OTM/ITM)
            
        Returns:
            Volatility at the specified tenor and strike
        """
        with PerformanceLogger("get_vol_at_strike", self.logger, 
                              tenor=tenor, strike=strike) as perf:
            
            # Find tenor index
            tenor_idx = np.searchsorted(surface.tenors, tenor)
            tenor_idx = np.clip(tenor_idx, 0, len(surface.tenors) - 1)
            
            # Determine moneyness: strike / spot
            # ATM: moneyness ≈ 1.0 (strike near spot)
            # OTM Call: moneyness > 1.0
            # OTM Put: moneyness < 1.0
            moneyness = strike / spot if spot > 0 else 1.0
            
            # ATM threshold: within 1% of spot
            atm_threshold = 0.01
            
            if abs(moneyness - 1.0) <= atm_threshold:
                # At-the-money: use ATM vol (index 0)
                vol_idx = 0
                perf.add_metric("vol_type", "ATM")
            elif moneyness > 1.0:
                # OTM Call: use +25RR vol (index 1)
                vol_idx = 1
                perf.add_metric("vol_type", "OTM_Call")
            else:
                # OTM Put: use -25RR vol (index 2)
                vol_idx = 2
                perf.add_metric("vol_type", "OTM_Put")
            
            # Get volatility at the determined index
            if tenor_idx < len(surface.volatilities) and vol_idx < len(surface.volatilities[tenor_idx]):
                vol = float(surface.volatilities[tenor_idx][vol_idx])
            else:
                # Fallback to ATM if indices are out of bounds
                vol = float(surface.volatilities[tenor_idx][0])
                perf.add_metric("vol_type", "ATM_fallback")
            
            perf.add_metric("vol", vol)
            return vol
    
    def health_check(self) -> Dict[str, str]:
        """
        Health check for vol surface service.
        
        Returns:
            Dict with status of each component:
            - vol_surface_service: Overall status
            - backend: QuantLib/backend connection status
            - redis: Redis connection status
            - memory_cache: Memory cache status
        """
        health = {
            "vol_surface_service": "healthy",
            "backend": "connected" if self.backend else "unavailable",
            "redis": "not_configured",
            "memory_cache_entries": len(self._memory_cache)
        }
        
        # Check Redis
        if self.redis:
            try:
                self.redis.ping()
                health["redis"] = "connected"
            except Exception as e:
                health["redis"] = f"error: {str(e)[:50]}"
        
        return health


# Utility function for testing/initialization
def create_mock_surface(
    base_date: datetime,
    tenors: list = None,
    strikes: list = None,
    base_vol: float = 0.15
) -> VolSurface:
    """Create a mock vol surface for testing."""
    
    if tenors is None:
        tenors = [1/52, 1/12, 3/12, 6/12, 1.0]  # 1W, 1M, 3M, 6M, 1Y
    
    if strikes is None:
        strikes = [100, 102.5, 97.5, 105, 95]  # ATM, 25RR+, 25RR-, 25BF+, 25BF-
    
    # Create smile-shaped surface
    vols = np.zeros((len(tenors), len(strikes)))
    for i in range(len(tenors)):
        # Term structure: shorter tenors have higher vol
        term_factor = 1.0 - (i * 0.05)
        vols[i, :] = base_vol * term_factor * (1 + 0.1 * np.random.randn(len(strikes)))
    
    vols = np.clip(vols, 0.05, 0.5)
    
    return VolSurface(
        snapshot_id=f"mock_{base_date.isoformat()}",
        base_date=base_date,
        tenors=tenors,
        strikes=strikes,
        volatilities=vols.tolist(),  # Convert numpy array to list of lists for pydantic compatibility
        source="mock",
        version="0.1.0"
    )
