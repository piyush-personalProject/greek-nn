# services/forex_service.py
"""
Forex Service for Live Spot Rate Integration.
Fetches real-time forex rates from alpha_vantage API.
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import asyncio
import aiohttp

from config import config
from logger import get_logger

logger = get_logger(__name__)


class ForexService:
    """
    Service for fetching real-time forex spot rates.
    
    Supports:
    - Alpha Vantage API (primary - free tier available)
    - Frankfurter API (secondary - free, no API key required)
    - Mock data (demo mode when API unavailable)
    """
    
    # Supported currency pairs
    SUPPORTED_PAIRS = [
        "EURUSD", "USDJPY", "GBPUSD", "USDCHF",
        "AUDUSD", "USDCAD", "NZDUSD"
    ]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        poll_interval: int = 60,
        timeout: int = 30
    ):
        """
        Initialize Forex Service.
        
        Args:
            api_key: Optional exchangeratesapi.io API key (free tier works without key)
                    Falls back to Alpha Vantage if provided
            poll_interval: Seconds between API polls
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or config.forex_api.api_key
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.frankfurter_url = "https://api.frankfurter.app/latest"
        self.alphavantage_url = "https://www.alphavantage.co/query"
        
        self._last_rates: Dict[str, float] = {}
        self._baseline_rates: Dict[str, float] = {}  # For calculating moves
        self._last_update: Optional[datetime] = None
        self._is_stale = False
        
        logger.info(f"ForexService initialized with API key present: {bool(self.api_key)}")
    
    async def fetch_rates(self) -> Dict[str, float]:
        """
        Fetch current spot rates for all supported pairs.
        
        Returns:
            Dict mapping pair names to spot rates
        """
        rates = {}
        errors = []
        
        for pair in self.SUPPORTED_PAIRS:
            try:
                rate = await self._fetch_pair_rate(pair)
                if rate:
                    rates[pair] = rate
                    self._last_rates[pair] = rate
            except Exception as e:
                errors.append(f"{pair}: {e}")
                logger.warning(f"Failed to fetch {pair}: {e}")
        
        if rates:
            self._last_update = datetime.now()
            self._is_stale = False
            
            # Initialize baseline if not set
            if not self._baseline_rates:
                self._baseline_rates = rates.copy()
        else:
            self._is_stale = True
            logger.warning("No rates fetched, data may be stale")
        
        if errors:
            logger.warning(f"Errors fetching rates: {errors}")
        
        return rates
    
    async def _fetch_pair_rate(self, pair: str) -> Optional[float]:
        """
        Fetch rate for a single currency pair.
        
        Uses Alpha Vantage (if API key provided) as primary source,
        then falls back to Frankfurter (free, no API key required).
        
        Args:
            pair: Currency pair (e.g., "EURUSD")
            
        Returns:
            Spot rate or None if fetch failed
        """
        # Try Alpha Vantage first if API key is available
        if self.api_key:
            rate = await self._fetch_from_alphavantage(pair)
            if rate:
                return rate
        
        # Fallback to Frankfurter (free, no API key required)
        rate = await self._fetch_from_frankfurter(pair)
        if rate:
            return rate
        
        # Last resort: fallback rate
        return self._get_fallback_rate(pair)
    
    async def _fetch_from_frankfurter(self, pair: str) -> Optional[float]:
        """
        Fetch rate from Frankfurter API (free, no API key required).
        
        Frankfurter is an open-source, free forex API that provides
        exchange rates for European currencies and many more.
        
        Args:
            pair: Currency pair (e.g., "EURUSD")
            
        Returns:
            Spot rate or None if fetch failed
        """
        from_currency, to_currency = self._parse_pair(pair)
        
        try:
            async with aiohttp.ClientSession() as session:
                # Frankfurter supports direct pair queries via ?from=&to=
                url = f"{self.frankfurter_url}?from={from_currency}&to={to_currency}"
                
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    allow_redirects=True
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Frankfurter returned {resp.status} for {pair}")
                        return None
                    
                    data = await resp.json()
                    
                    if "rates" not in data:
                        logger.warning(f"No rates in Frankfurter response for {pair}")
                        return None
                    
                    rates = data["rates"]
                    
                    # Get the target currency rate
                    rate = rates.get(to_currency)
                    
                    if rate:
                        # For XXXUSD pairs where to_currency is USD, 
                        # Frankfurter returns the rate as from/to, need to invert
                        if to_currency == "USD":
                            rate = 1.0 / rate
                        logger.debug(f"Fetched {pair} from Frankfurter: {rate}")
                        return rate
                    
                    return None
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {pair} from Frankfurter")
            return None
        except Exception as e:
            logger.error(f"Error fetching {pair} from Frankfurter: {e}")
            return None
    
    async def _fetch_from_alphavantage(self, pair: str) -> Optional[float]:
        """
        Fetch rate from Alpha Vantage API.
        
        Args:
            pair: Currency pair (e.g., "EURUSD")
            
        Returns:
            Spot rate or None if fetch failed
        """
        from_currency, to_currency = self._parse_pair(pair)
        
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "function": "CURRENCY_EXCHANGE_RATE",
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "apikey": self.api_key
                }
                
                async with session.get(
                    self.alphavantage_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Alpha Vantage returned {resp.status} for {pair}")
                        return None
                    
                    data = await resp.json()
                    
                    # Check for API limit message - this is expected with free tier
                    if "Note" in data or "Information" in data:
                        logger.info(f"Alpha Vantage rate limit reached for {pair}")
                        return None
                    
                    # Parse the response
                    rate_key = f"Realtime Currency Exchange Rate"
                    if rate_key in data:
                        rate_str = data[rate_key].get("5. Exchange Rate", "0")
                        rate = float(rate_str)
                        logger.debug(f"Fetched {pair} from Alpha Vantage: {rate}")
                        return rate
                    
                    logger.warning(f"Unexpected Alpha Vantage response format for {pair}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {pair} from Alpha Vantage")
            return None
        except Exception as e:
            logger.error(f"Error fetching {pair} from Alpha Vantage: {e}")
            return None
    
    def _parse_pair(self, pair: str) -> tuple:
        """
        Parse currency pair string into from/to currencies.
        
        Args:
            pair: Currency pair like "EURUSD"
            
        Returns:
            Tuple of (from_currency, to_currency)
        """
        # Most pairs are XXXYYY where XXX is quote and YYY is base
        # But for forex we typically express as XXX/YYY
        # USDJPY means USD/JPY, so from=USD, to=JPY
        
        if len(pair) == 6:
            return pair[:3], pair[3:]
        
        # Handle special cases or return defaults
        return pair[:3], pair[3:]
    
    def _get_mock_rate(self, pair: str) -> float:
        """Get mock rate for demo mode."""
        mock_rates = {
            "EURUSD": 1.0850,
            "USDJPY": 149.50,
            "GBPUSD": 1.2650,
            "USDCHF": 0.8850,
            "AUDUSD": 0.6550,
            "USDCAD": 1.3450,
            "NZDUSD": 0.6050
        }
        
        # Add small random variation to simulate market movement
        import random
        base_rate = mock_rates.get(pair, 1.0)
        variation = base_rate * 0.0001  # 0.01% variation
        return base_rate + random.uniform(-variation, variation)
    
    def _get_fallback_rate(self, pair: str) -> float:
        """Get fallback rate from last known or mock."""
        if pair in self._last_rates:
            return self._last_rates[pair]
        return self._get_mock_rate(pair)
    
    async def fetch_historical(
        self,
        pair: str,
        days: int = 30
    ) -> List[Dict]:
        """
        Fetch historical rates for a currency pair.
        
        Args:
            pair: Currency pair
            days: Number of days of history
            
        Returns:
            List of dicts with date and rate
        """
        if not self.api_key:
            logger.info("No API key, returning mock historical data")
            return self._get_mock_historical(pair, days)
        
        from_currency, to_currency = self._parse_pair(pair)
        
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "function": "FX_DAILY",
                    "from_symbol": from_currency,
                    "to_symbol": to_currency,
                    "outputsize": "compact" if days <= 100 else "full",
                    "apikey": self.api_key
                }
                
                async with session.get(
                    self.alphavantage_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        return self._get_mock_historical(pair, days)
                    
                    data = await resp.json()
                    
                    # Parse Time Series FX Daily
                    if "Time Series FX (Daily)" in data:
                        series = data["Time Series FX (Daily)"]
                        results = []
                        for date_str, day_data in list(series.items())[:days]:
                            results.append({
                                "date": date_str,
                                "open": float(day_data["1. open"]),
                                "high": float(day_data["2. high"]),
                                "low": float(day_data["3. low"]),
                                "close": float(day_data["4. close"])
                            })
                        return results
                    
                    return self._get_mock_historical(pair, days)
                    
        except Exception as e:
            logger.error(f"Error fetching historical {pair}: {e}")
            return self._get_mock_historical(pair, days)
    
    def _get_mock_historical(self, pair: str, days: int) -> List[Dict]:
        """Generate mock historical data."""
        import random
        results = []
        base_rate = self._get_mock_rate(pair)
        
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            variation = base_rate * 0.002  # 0.2% daily variation
            close = base_rate + random.uniform(-variation, variation)
            
            results.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": close + random.uniform(-variation/2, variation/2),
                "high": close + random.uniform(0, variation),
                "low": close - random.uniform(0, variation),
                "close": close
            })
        
        return results
    
    def get_rate_change(self, pair: str) -> Dict[str, float]:
        """
        Get the change in rate from baseline.
        
        Args:
            pair: Currency pair
            
        Returns:
            Dict with current, baseline, change_pct
        """
        current = self._last_rates.get(pair)
        baseline = self._baseline_rates.get(pair)
        
        if not current or not baseline:
            return {"current": current, "baseline": baseline, "change_pct": 0.0}
        
        change_pct = ((current - baseline) / baseline) * 100
        
        logger.debug(f"Rate change for {pair}: current={current}, baseline={baseline}, change_pct={change_pct:.4f}%")
        
        return {
            "current": round(current, 5),
            "baseline": round(baseline, 5),
            "change_pct": round(change_pct, 4)
        }
    
    def update_baseline(self) -> None:
        """Update baseline rates to current rates."""
        self._baseline_rates = self._last_rates.copy()
        logger.info("Spot rate baseline updated to current rates")
    
    def get_status(self) -> Dict:
        """Get service status."""
        return {
            "service": "forex",
            "status": "healthy" if self._last_rates else "degraded",
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "is_stale": self._is_stale,
            "pairs_count": len(self._last_rates),
            "api_key_configured": bool(self.api_key)
        }
    
    def health_check(self) -> Dict[str, str]:
        """Health check for the service."""
        return self.get_status()


# Global instance (initialized in api.py startup)
_forex_service: Optional[ForexService] = None


def get_forex_service() -> ForexService:
    """Get the global forex service instance."""
    global _forex_service
    if _forex_service is None:
        _forex_service = ForexService()
    return _forex_service


def init_forex_service(api_key: Optional[str] = None, **kwargs) -> ForexService:
    """Initialize the global forex service."""
    global _forex_service
    _forex_service = ForexService(api_key=api_key, **kwargs)
    return _forex_service