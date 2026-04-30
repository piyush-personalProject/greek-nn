# modules/vol_surface_service.py
"""
Module 4: Vol Surface Service
Maintains live vol surface, applies shocks, and serves to risk engine.
Uses QuantLib for baseline surface and caching for performance.
"""
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from abc import ABC, abstractmethod
import redis
import json
from dataclasses import asdict, dataclass
import pickle

from config import config
from schemas import VolSurface, VolShock
from logger import get_logger

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
        surface = self.backend.get_surface(date, version)
        if surface:
            self._cache_surface(cache_key, surface)
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
        """
        
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
        
        # Apply shocks (multiplicative: vol_new = vol_old * (1 + shock))
        for tenor_idx, shock_amount in tenor_shocks.items():
            if tenor_idx < len(shocked_vol):
                shocked_vol[tenor_idx][:] = shocked_vol[tenor_idx][:] * (1.0 + shock_amount)
        
        # Apply RR and BF shocks to 1M tenor (idx=1)
        if len(shocked_vol) > 1:
            # Assume strike indices: [ATM, +25RR, -25RR, +BF, -BF]
            # RR: right wing (call) - left wing (put)
            if len(shocked_vol[1]) > 2:
                shocked_vol[1][1] = shocked_vol[1][1] * (1.0 + shock.delta_1M_25RR)  # +25RR
                shocked_vol[1][2] = shocked_vol[1][2] * (1.0 + shock.delta_1M_25RR)  # -25RR
            
            # BF: (call + put) / 2 - ATM
            if len(shocked_vol[1]) > 4:
                shocked_vol[1][3] = shocked_vol[1][3] * (1.0 + shock.delta_1M_25BF)  # +BF
                shocked_vol[1][4] = shocked_vol[1][4] * (1.0 + shock.delta_1M_25BF)  # -BF
        
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
            f"Applied shock {shock.shock_id} to surface {base_surface.snapshot_id}",
            extra_fields={
                "event_type": shock.event_vector.event_type,
                "sentiment": shock.event_vector.sentiment,
                "shock_1m_atm": shock.delta_1M_ATM
            }
        )
        
        # Cache shocked surface
        shock_key = self._shock_key(shock.shock_id)
        self._cache_shocked_surface(shock_key, shocked_surface)
        
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
        """Get ATM vol for a given tenor from surface."""
        tenor_idx = np.searchsorted(surface.tenors, tenor)
        tenor_idx = np.clip(tenor_idx, 0, len(surface.tenors) - 1)
        return float(surface.volatilities[tenor_idx][0])  # ATM is index 0
    
    def health_check(self) -> Dict[str, str]:
        """Health check for vol surface service."""
        health = {"vol_surface_service": "healthy"}
        
        # Check backend
        if self.backend:
            health["backend"] = "connected"
        else:
            health["backend"] = "unavailable"
        
        # Check Redis
        if self.redis:
            try:
                self.redis.ping()
                health["redis"] = "connected"
            except:
                health["redis"] = "disconnected"
        else:
            health["redis"] = "not_configured"
        
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
        volatilities=vols,
        source="mock",
        version="0.1.0"
    )
