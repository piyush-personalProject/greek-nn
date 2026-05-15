# modules/news_ingestion.py
"""
Module 1: News Ingestion
Streams headlines from NewsAPI, Bloomberg, RSS feeds in real-time.
Target: <500ms latency from headline published to system.
"""
import logging
from typing import List, Optional, Dict, AsyncIterator
from datetime import datetime, timedelta
import asyncio
import aiohttp
import feedparser
from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import os

from config import config
from schemas import NewsEvent
from logger import get_logger

logger = get_logger(__name__)


def get_mock_news_events() -> List[NewsEvent]:
    """
    Generate mock news events for testing.
    Each headline is prefixed with '-mock' to indicate it's test data.
    """
    now = datetime.now()
    return [
        NewsEvent(
            headline="-mock Fed signals potential rate cuts amid cooling inflation",
            source="Mock Reuters",
            url="https://mock.reuters.com/fed-rate-cuts",
            published_at=now - timedelta(minutes=15),
            content="Federal Reserve officials indicate openness to rate reductions as inflation shows signs of cooling."
        ),
        NewsEvent(
            headline="-mock ECB holds rates steady at 4.5% in surprise decision",
            source="Mock Bloomberg",
            url="https://mock.bloomberg.com/ecb-rates",
            published_at=now - timedelta(minutes=30),
            content="European Central Bank maintains interest rates, surprising markets expecting a cut."
        ),
        NewsEvent(
            headline="-mock US employment data beats expectations with 250K jobs added",
            source="Mock CNBC",
            url="https://mock.cnbc.com/jobs-report",
            published_at=now - timedelta(minutes=45),
            content="Non-farm payrolls significantly exceed forecasts, suggesting labor market resilience."
        ),
        NewsEvent(
            headline="-mock Japan intervenes in currency markets to support yen",
            source="Mock Nikkei",
            url="https://mock.nikkei.com/forex-intervention",
            published_at=now - timedelta(hours=1),
            content="Bank of Japan conducts unexpected currency intervention as yen weakens past 155 per dollar."
        ),
        NewsEvent(
            headline="-mock China manufacturing PMI contracts for third consecutive month",
            source="Mock SCMP",
            url="https://mock.scmp.com/china-pmi",
            published_at=now - timedelta(hours=2),
            content="Chinese industrial activity continues to decline, raising concerns about global demand."
        ),
        NewsEvent(
            headline="-mock Oil prices surge 5% on OPEC+ production cut announcement",
            source="Mock WSJ",
            url="https://mock.wsj.com/oil-prices",
            published_at=now - timedelta(hours=3),
            content="OPEC+ agrees to deeper production cuts, sending crude futures higher."
        ),
        NewsEvent(
            headline="-mock Swiss National Bank unexpectedly cuts rates by 25bps",
            source="Mock SF",
            url="https://mock.srf.ch/snb-rate-cut",
            published_at=now - timedelta(hours=4),
            content="SNB takes preemptive action against franc strength as inflation moderates."
        ),
        NewsEvent(
            headline="-mock UK inflation falls to 3.2%, boosting rate cut expectations",
            source="Mock FT",
            url="https://mock.ft.com/uk-inflation",
            published_at=now - timedelta(hours=5),
            content="British consumer prices drop more than anticipated, increasing pressure on BoE."
        ),
    ]


class NewsCache:
    """
    Singleton cache for news headlines with persistent file storage.
    Fetches from NewsAPI only on-demand (explicit refresh).
    Shared across all consumers to avoid duplicate API calls.
    
    On successful API fetch, data is persisted to a JSON file.
    On subsequent API failures, persisted data is used as fallback only if it was real (non-mock) data.
    Mock data is never persisted as it should only be used when no real data exists.
    """
    
    _instance: Optional["NewsCache"] = None
    _cache_file: str = "news_cache.json"
    
    def __init__(self):
        self._headlines: List[NewsEvent] = []
        self._last_refresh: Optional[datetime] = None
        self._is_fetching: bool = False
        self._fetch_error: Optional[str] = None
        self._max_age_seconds: int = 300  # 5 minutes max cache age
        self._is_mock_data: bool = False  # Track if current cache is mock data
        # Load persisted cache on initialization
        self._load_from_file()
    
    @classmethod
    def get_instance(cls) -> "NewsCache":
        """Get the singleton NewsCache instance."""
        if cls._instance is None:
            cls._instance = NewsCache()
        return cls._instance
    
    @property
    def headlines(self) -> List[NewsEvent]:
        """Get cached headlines."""
        return self._headlines
    
    @property
    def last_refresh(self) -> Optional[datetime]:
        """Get last refresh timestamp."""
        return self._last_refresh
    
    @property
    def is_fetching(self) -> bool:
        """Check if a fetch is in progress."""
        return self._is_fetching
    
    @property
    def fetch_error(self) -> Optional[str]:
        """Get last fetch error."""
        return self._fetch_error
    
    @property
    def is_mock_data(self) -> bool:
        """Check if current cache contains mock data."""
        return self._is_mock_data
    
    def is_fresh(self) -> bool:
        """Check if cache is still fresh (not expired) and contains real data."""
        if self._last_refresh is None or not self._headlines or self._is_mock_data:
            return False
        age = (datetime.now() - self._last_refresh).total_seconds()
        return age < self._max_age_seconds
    
    def set_headlines(self, headlines: List[NewsEvent], is_mock: bool = False) -> None:
        """Set cached headlines after a successful fetch.
        
        Args:
            headlines: List of news headlines to cache
            is_mock: If True, this is mock data (should not be persisted)
        """
        self._headlines = headlines
        self._last_refresh = datetime.now()
        self._fetch_error = None
        self._is_mock_data = is_mock
        logger.info(
            f"NewsCache updated with {len(headlines)} headlines (mock={is_mock})",
            extra_fields={"action": "cache_updated", "count": len(headlines), "is_mock": is_mock}
        )
        # Only persist to file if this is real data, not mock data
        if not is_mock:
            self._save_to_file()
        else:
            logger.debug("Skipping persist for mock data")
    
    def set_error(self, error: str) -> None:
        """Set fetch error."""
        self._fetch_error = error
        logger.warning(f"NewsCache fetch error: {error}")
    
    def clear(self) -> None:
        """Clear the cache."""
        self._headlines = []
        self._last_refresh = None
        self._fetch_error = None
        self._is_mock_data = False
    
    def _load_from_file(self) -> bool:
        """
        Load cached headlines from JSON file.
        Returns True if successfully loaded, False otherwise.
        Loaded data is marked as real (non-mock) since it came from API.
        """
        try:
            if os.path.exists(self._cache_file):
                with open(self._cache_file, 'r') as f:
                    data = json.load(f)
                    headlines_data = data.get("headlines", [])
                    self._headlines = [
                        NewsEvent(
                            headline=h["headline"],
                            source=h["source"],
                            url=h.get("url", ""),
                            published_at=datetime.fromisoformat(h["published_at"]) if h.get("published_at") else datetime.now(),
                            content=h.get("content", "")
                        )
                        for h in headlines_data
                    ]
                    self._last_refresh = datetime.fromisoformat(data["last_refresh"]) if data.get("last_refresh") else None
                    # Loaded from file is real API data, not mock
                    self._is_mock_data = False
                    logger.info(
                        f"Loaded {len(self._headlines)} headlines from cache file (real data)",
                        extra_fields={"action": "cache_file_load", "count": len(self._headlines), "is_mock": False}
                    )
                    return True
        except Exception as e:
            logger.warning(f"Failed to load cache from file: {e}")
        return False
    
    def _save_to_file(self) -> bool:
        """
        Persist current headlines to JSON file.
        Returns True if successfully saved, False otherwise.
        """
        try:
            data = {
                "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
                "headlines": [
                    {
                        "headline": h.headline,
                        "source": h.source,
                        "url": h.url,
                        "published_at": h.published_at.isoformat() if h.published_at else None,
                        "content": h.content
                    }
                    for h in self._headlines
                ]
            }
            with open(self._cache_file, 'w') as f:
                json.dump(data, f)
            logger.info(
                f"Saved {len(self._headlines)} headlines to cache file",
                extra_fields={"action": "cache_file_save", "count": len(self._headlines)}
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to save cache to file: {e}")
        return False
    
    def has_persisted_data(self) -> bool:
        """Check if there is persisted real (non-mock) data available from file."""
        return len(self._headlines) > 0 and self._last_refresh is not None and not self._is_mock_data


def get_news_cache() -> NewsCache:
    """Get the global NewsCache instance."""
    return NewsCache.get_instance()


@dataclass
class FeedSource:
    """Configuration for a news source."""
    name: str
    url: str
    source_type: str  # "api", "rss", "websocket"
    priority: int = 1  # Higher = higher priority
    enabled: bool = True


class NewsSourceBase(ABC):
    """Abstract base for news sources."""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = get_logger(f"NewsSource.{name}")
    
    @abstractmethod
    async def fetch_headlines(self) -> List[NewsEvent]:
        """Fetch latest headlines from source."""
        pass
    
    @abstractmethod
    async def stream_headlines(self) -> AsyncIterator[NewsEvent]:
        """Stream headlines in real-time."""
        pass


class NewsAPISource(NewsSourceBase):
    """
    NewsAPI.org source.
    Free tier: 100 requests/day, 5 min update lag.
    Pro tier: <1 min lag.
    """
    
    def __init__(self, api_key: str, keywords: List[str] = None):
        super().__init__("NewsAPI")
        self.api_key = api_key
        self.base_url = "https://newsapi.org/v2"
        self.keywords = keywords or config.news_api.keywords
        self.last_fetch = datetime.min
        self.min_poll_interval = timedelta(minutes=5)  # Free tier limit
    
    async def fetch_headlines(self) -> List[NewsEvent]:
        """Fetch latest headlines for monitored keywords."""
        headlines = []
        self.logger.info(
            f"NewsAPI fetch starting",
            extra_fields={"keywords": self.keywords, "action": "newsapi_fetch_start"}
        )
        
        # Search for each keyword
        for keyword in self.keywords:
            self.logger.info(
                f"Fetching NewsAPI for keyword: '{keyword}'",
                extra_fields={"keyword": keyword, "action": "keyword_fetch"}
            )
            try:
                await asyncio.sleep(0.5)  # Rate limit: 100 requests/day = 1 per 15s
                
                async with aiohttp.ClientSession() as session:
                    params = {
                        "q": keyword,
                        "from": (datetime.now() - timedelta(hours=24)).isoformat(),
                        "sortBy": "publishedAt",
                        "language": "en",
                        "apiKey": self.api_key,
                        "pageSize": 20
                    }
                    
                    self.logger.debug(
                        f"Making NewsAPI request",
                        extra_fields={"keyword": keyword, "url": f"{self.base_url}/everything"}
                    )
                    
                    # Use top-headlines (free tier compatible) instead of everything (requires paid)
                    async with session.get(
                        f"{self.base_url}/top-headlines",
                        params={
                            "q": keyword,
                            "country": "us",
                            "pageSize": 20,
                            "apiKey": self.api_key
                        },
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        self.logger.info(
                            f"NewsAPI response received",
                            extra_fields={"keyword": keyword, "status": resp.status}
                        )
                        
                        if resp.status != 200:
                            error_body = await resp.text()
                            self.logger.error(
                                f"NewsAPI failed to receive news for keyword '{keyword}': HTTP status {resp.status}",
                                extra_fields={
                                    "keyword": keyword,
                                    "http_status": resp.status,
                                    "reason": f"HTTP error: received status {resp.status}",
                                    "response_body": error_body[:500] if error_body else "empty",
                                    "action": "news_source_failure"
                                }
                            )
                            continue
                        
                        data = await resp.json()
                        
                        if data.get("status") != "ok":
                            error_msg = data.get("message", "Unknown API error")
                            self.logger.error(
                                f"NewsAPI failed to receive news for keyword '{keyword}': {error_msg}",
                                extra_fields={
                                    "keyword": keyword,
                                    "api_status": data.get("status"),
                                    "reason": error_msg,
                                    "action": "news_source_failure"
                                }
                            )
                            continue
                        
                        articles = data.get("articles", [])
                        self.logger.info(
                            f"NewsAPI parsed articles for '{keyword}'",
                            extra_fields={"keyword": keyword, "articles_count": len(articles)}
                        )
                        
                        for article in articles:
                            event = self._parse_article(article)
                            headlines.append(event)
                            
                            self.logger.debug(
                                f"Headline parsed",
                                extra_fields={"headline": event.headline[:60], "source": event.source}
                            )
                        
                        self.logger.info(
                            f"Keyword '{keyword}' processed successfully",
                            extra_fields={"keyword": keyword, "headlines_added": len(articles)}
                        )
            
            except asyncio.TimeoutError:
                self.logger.error(
                    f"NewsAPI failed to receive news for keyword '{keyword}': Request timeout after 10 seconds",
                    extra_fields={
                        "keyword": keyword,
                        "error": "timeout",
                        "reason": "Request timed out while fetching from NewsAPI (timeout=10s)",
                        "action": "news_source_failure"
                    }
                )
            except aiohttp.ClientError as e:
                self.logger.error(
                    f"NewsAPI failed to receive news for keyword '{keyword}': Client error - {type(e).__name__}",
                    extra_fields={
                        "keyword": keyword,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "reason": f"aiohttp client error: {str(e)}",
                        "action": "news_source_failure"
                    }
                )
            except Exception as e:
                self.logger.error(
                    f"NewsAPI failed to receive news for keyword '{keyword}': {type(e).__name__} - {str(e)}",
                    extra_fields={
                        "keyword": keyword,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
                        "action": "news_source_failure"
                    }
                )
        
        self.logger.info(
            f"NewsAPI fetch completed",
            extra_fields={"total_headlines": len(headlines), "keywords_processed": len(self.keywords)}
        )
        
        return headlines
    
    async def stream_headlines(self) -> AsyncIterator[NewsEvent]:
        """
        Stream headlines continuously.
        In production, would use WebSocket or Server-Sent Events.
        """
        while True:
            try:
                self.logger.info(f"NewsAPI starting poll cycle for {len(self.keywords)} keywords")
                headlines = await self.fetch_headlines()
                for headline in headlines:
                    yield headline
                
                # Wait before next poll
                poll_interval = self.min_poll_interval.total_seconds()
                self.logger.info(f"NewsAPI polling sleep for {poll_interval}s (next poll)")
                await asyncio.sleep(poll_interval)
            
            except Exception as e:
                self.logger.error(
                    f"NewsAPI stream failed to receive news: {type(e).__name__} - {str(e)}",
                    extra_fields={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "reason": f"Stream error in NewsAPI: {type(e).__name__}: {str(e)}",
                        "action": "news_source_failure"
                    }
                )
                self.logger.info("NewsAPI backing off for 10s before retry")
                await asyncio.sleep(10)  # Backoff on error
    
    def _parse_article(self, article: dict) -> NewsEvent:
        """Parse NewsAPI article into NewsEvent."""
        return NewsEvent(
            headline=article.get("title", ""),
            source=article.get("source", {}).get("name", "NewsAPI"),
            url=article.get("url", ""),
            published_at=datetime.fromisoformat(
                article.get("publishedAt", datetime.now().isoformat()).replace("Z", "+00:00")
            ),
            content=article.get("content", article.get("description", ""))
        )


class RSSFeedSource(NewsSourceBase):
    """
    RSS feed source.
    Examples: MAS, Fed, ECB, BLS RSS feeds.
    """
    
    def __init__(self, name: str, feeds: List[str]):
        super().__init__(name)
        self.feeds = feeds
        self.last_fetch = {}
    
    async def fetch_headlines(self) -> List[NewsEvent]:
        """Fetch latest from RSS feeds."""
        headlines = []
        self.logger.info(f"Fetching RSS feeds: {self.feeds}")
        
        for feed_url in self.feeds:
            try:
                # RSS parsing is synchronous, run in executor
                loop = asyncio.get_event_loop()
                parsed = await loop.run_in_executor(None, feedparser.parse, feed_url)
                
                for entry in parsed.get("entries", [])[:10]:  # Last 10 entries
                    event = self._parse_entry(entry, feed_url)
                    headlines.append(event)
                    
                    self.logger.debug(f"Fetched RSS headline: {event.headline[:60]}...")
            
            except Exception as e:
                self.logger.error(
                    f"RSS feed failed to receive news from '{feed_url}': {type(e).__name__} - {str(e)}",
                    extra_fields={
                        "feed_url": feed_url,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "reason": f"RSS parsing failed: {type(e).__name__}: {str(e)}",
                        "action": "news_source_failure"
                    }
                )
        
        return headlines
    
    async def stream_headlines(self) -> AsyncIterator[NewsEvent]:
        """Stream RSS headlines (polling every hour)."""
        while True:
            try:
                self.logger.info(f"RSS starting poll cycle for {len(self.feeds)} feeds")
                headlines = await self.fetch_headlines()
                for headline in headlines:
                    yield headline
                
                await asyncio.sleep(3600)  # Poll every hour for RSS
                self.logger.info("RSS polling sleep for 3600s (next poll)")
            
            except Exception as e:
                self.logger.error(
                    f"RSS stream failed to receive news: {type(e).__name__} - {str(e)}",
                    extra_fields={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "reason": f"Stream error in RSS: {type(e).__name__}: {str(e)}",
                        "action": "news_source_failure"
                    }
                )
                self.logger.info("RSS backing off for 60s before retry")
                await asyncio.sleep(60)
    
    def _parse_entry(self, entry: dict, feed_url: str) -> NewsEvent:
        """Parse RSS entry into NewsEvent."""
        
        # Try multiple date fields
        pub_date = entry.get("published", entry.get("updated", datetime.now().isoformat()))
        
        try:
            from email.utils import parsedate_to_datetime
            published_at = parsedate_to_datetime(pub_date)
        except:
            published_at = datetime.now().astimezone()
        
        return NewsEvent(
            headline=entry.get("title", ""),
            source=entry.get("author", self.name),
            url=entry.get("link", ""),
            published_at=published_at,
            content=entry.get("summary", entry.get("description", ""))
        )


class BloombergSource(NewsSourceBase):
    """
    Bloomberg feed source.
    Requires Bloomberg Terminal access (BLPAPI).
    Falls back to mock in test environment.
    """
    
    def __init__(self, timeout: int = 10):
        super().__init__("Bloomberg")
        self.timeout = timeout
        self._mock_mode = True  # Set to False when BLPAPI available
    
    async def fetch_headlines(self) -> List[NewsEvent]:
        """Fetch from Bloomberg (stub - requires BLPAPI)."""
        if self._mock_mode:
            self.logger.debug("Bloomberg in mock mode")
            return []  # In production, would use blpapi
        
        # Real implementation would use blpapi
        return []
    
    async def stream_headlines(self) -> AsyncIterator[NewsEvent]:
        """Stream from Bloomberg."""
        while True:
            try:
                self.logger.info("Bloomberg starting poll cycle")
                headlines = await self.fetch_headlines()
                for headline in headlines:
                    yield headline
                
                await asyncio.sleep(60)
                self.logger.info("Bloomberg polling sleep for 60s (next poll)")
            except Exception as e:
                self.logger.error(
                    f"Bloomberg stream failed to receive news: {type(e).__name__} - {str(e)}",
                    extra_fields={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "reason": f"Stream error in Bloomberg: {type(e).__name__}: {str(e)}",
                        "action": "news_source_failure"
                    }
                )
                await asyncio.sleep(10)


class NewsIngestionService:
    """
    Main news ingestion service.
    Aggregates headlines from multiple sources.
    Deduplicates and orders by importance/recency.
    """
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.sources: Dict[str, NewsSourceBase] = {}
        self.recent_headlines: Dict[str, NewsEvent] = {}  # Dedup by headline text
        self.max_recent = 1000
        
        self._initialize_sources()
    
    def _initialize_sources(self) -> None:
        """Initialize configured news sources."""
        
        # NewsAPI
        if config.enable_news_ingestion and config.news_api.api_key:
            self.sources["newsapi"] = NewsAPISource(
                config.news_api.api_key,
                config.news_api.keywords
            )
            self.logger.info("Initialized NewsAPI source")
        else:
            self.logger.warning("NewsAPI not configured. Skipping.")
        
        # RSS Feeds
        mas_feeds = [
            "https://www.mas.gov.sg/news-and-publications/media-releases/rss",
        ]
        fed_feeds = [
            "https://www.federalreserve.gov/feeds/press.xml",
        ]
        
        self.sources["mas_rss"] = RSSFeedSource("MAS", mas_feeds)
        self.sources["fed_rss"] = RSSFeedSource("FED", fed_feeds)
        
        self.logger.info("Initialized RSS sources")
    
    async def fetch_all_headlines(self) -> List[NewsEvent]:
        """Fetch headlines from all sources concurrently."""
        self.logger.info(
            "Starting news fetch cycle",
            extra_fields={
                "sources_count": len(self.sources),
                "sources": list(self.sources.keys()),
                "action": "news_fetch_start"
            }
        )
        
        tasks = [
            source.fetch_headlines()
            for source in self.sources.values()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_headlines = []
        sources_result_log = []
        
        for i, result in enumerate(results):
            source_name = list(self.sources.keys())[i] if i < len(self.sources) else f"source_{i}"
            if isinstance(result, list):
                sources_result_log.append({
                    "source": source_name,
                    "status": "success",
                    "headlines_count": len(result)
                })
                all_headlines.extend(result)
                self.logger.info(
                    f"Source [{source_name}] returned {len(result)} headlines",
                    extra_fields={"source": source_name, "count": len(result), "status": "success"}
                )
            elif isinstance(result, Exception):
                error_detail = f"{type(result).__name__}: {str(result)}"
                sources_result_log.append({
                    "source": source_name,
                    "status": "error",
                    "error": error_detail,
                    "reason": f"News source '{source_name}' failed to fetch: {error_detail}"
                })
                self.logger.error(
                    f"Source [{source_name}] failed to receive news: {error_detail}",
                    extra_fields={
                        "source": source_name,
                        "error": str(result),
                        "error_type": type(result).__name__,
                        "reason": f"Source '{source_name}' error: {error_detail}",
                        "status": "error",
                        "action": "news_source_failure"
                    }
                )
        
        self.logger.info(
            "News fetch cycle completed",
            extra_fields={
                "action": "news_fetch_complete",
                "total_headlines": len(all_headlines),
                "sources_results": sources_result_log
            }
        )
        
        # Fallback to mock news if all sources returned empty
        if not all_headlines:
            self.logger.warning(
                "All news sources returned empty. Using mock news events as fallback.",
                extra_fields={"action": "using_mock_fallback"}
            )
            all_headlines = get_mock_news_events()
        else:
            self.logger.info(
                f"Fetched {len(all_headlines)} real headlines from news sources",
                extra_fields={"action": "real_headlines_fetched", "count": len(all_headlines)}
            )
        
        # Deduplicate and update recent
        for headline in all_headlines:
            headline_key = headline.headline.lower()
            if headline_key not in self.recent_headlines:
                self.recent_headlines[headline_key] = headline
        
        # Keep only recent
        if len(self.recent_headlines) > self.max_recent:
            sorted_headlines = sorted(
                self.recent_headlines.values(),
                key=lambda x: x.published_at,
                reverse=True
            )
            self.recent_headlines = {
                h.headline.lower(): h for h in sorted_headlines[:self.max_recent]
            }
        
        return list(self.recent_headlines.values())
    
    async def stream_all_headlines(self) -> AsyncIterator[NewsEvent]:
        """Stream headlines from all sources."""
        
        # Create tasks for each source
        tasks = [
            self._stream_from_source(name, source)
            for name, source in self.sources.items()
        ]
        
        # Use async queue for aggregation
        queue: asyncio.Queue[NewsEvent] = asyncio.Queue()
        
        async def producer(source_name: str, source: NewsSourceBase):
            """Produce headlines to queue."""
            try:
                async for headline in source.stream_headlines():
                    await queue.put(headline)
            except Exception as e:
                self.logger.error(
                    f"News producer failed to receive from '{source_name}': {type(e).__name__} - {str(e)}",
                    extra_fields={
                        "source_name": source_name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "reason": f"Producer error from '{source_name}': {type(e).__name__}: {str(e)}",
                        "action": "news_source_failure"
                    }
                )
        
        # Start producers
        producer_tasks = [
            asyncio.create_task(producer(name, source))
            for name, source in self.sources.items()
        ]
        
        # Consume and deduplicate
        seen = set()
        try:
            while True:
                try:
                    headline = await asyncio.wait_for(queue.get(), timeout=1.0)
                    
                    headline_key = headline.headline.lower()
                    if headline_key not in seen:
                        seen.add(headline_key)
                        
                        # Keep window of recent
                        if len(seen) > self.max_recent:
                            seen.pop()
                        
                        yield headline
                
                except asyncio.TimeoutError:
                    continue
        
        except asyncio.CancelledError:
            for task in producer_tasks:
                task.cancel()
            raise
    
    async def _stream_from_source(self, name: str, source: NewsSourceBase) -> None:
        """Internal: stream from single source."""
        try:
            async for headline in source.stream_headlines():
                # Log receipt
                self.logger.debug(
                    f"Received headline from {name}",
                    extra_fields={"source": name}
                )
                yield headline
        except Exception as e:
            self.logger.error(
                f"Stream from '{name}' failed to receive news: {type(e).__name__} - {str(e)}",
                extra_fields={
                    "source_name": name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "reason": f"Stream error from '{name}': {type(e).__name__}: {str(e)}",
                    "action": "news_source_failure"
                }
            )
    
    def get_recent_by_keyword(self, keyword: str, max_results: int = 20) -> List[NewsEvent]:
        """Get recent headlines matching keyword (uses cache)."""
        cache = get_news_cache()
        headlines = cache.headlines
        keyword_lower = keyword.lower()
        matching = [
            h for h in headlines
            if keyword_lower in h.headline.lower() or keyword_lower in (h.content or "").lower()
        ]
        
        return sorted(
            matching,
            key=lambda x: x.published_at,
            reverse=True
        )[:max_results]
    
    def get_cached_headlines(self) -> List[NewsEvent]:
        """Get headlines from cache without fetching."""
        cache = get_news_cache()
        return cache.headlines
    
    async def refresh_cache(self, force: bool = False) -> List[NewsEvent]:
        """
        Refresh the news cache by fetching fresh headlines.
        Only fetches if cache is stale or force=True.
        
        Priority order:
        1. If cache has fresh real (non-mock) data, use it
        2. Fetch from API
        3. If API fails and persisted real data exists, use persisted
        4. If no real data available, use mock data as final fallback
        
        Mock data is never persisted to ensure it doesn't overwrite real cached data.
        
        Args:
            force: If True, bypass freshness check and fetch regardless
        
        Returns:
            List of headlines (from cache after refresh)
        """
        cache = get_news_cache()
        
        # Check if cache has fresh real data (not mock)
        if not force and cache.is_fresh():
            cache_headlines = cache.headlines
            self.logger.debug(
                f"Using cached real headlines (fresh, {len(cache_headlines)} headlines)",
                extra_fields={"action": "cache_hit", "count": len(cache_headlines)}
            )
            return cache_headlines
        
        if cache.is_fetching:
            self.logger.info("Fetch already in progress, waiting for result")
            # Wait for ongoing fetch to complete
            import time
            for _ in range(20):  # Wait up to 2 seconds
                time.sleep(0.1)
                if not cache.is_fetching:
                    break
            return cache.headlines
        
        # Perform fresh fetch
        cache._is_fetching = True
        try:
            headlines = await self.fetch_all_headlines()
            # Check if headlines are mock (prefixed with "-mock")
            is_mock = any(h.headline.startswith("-mock") for h in headlines) if headlines else False
            cache.set_headlines(headlines, is_mock=is_mock)
            return headlines
        except Exception as e:
            cache.set_error(str(e))
            self.logger.error(
                f"Failed to fetch news from API: {e}",
                extra_fields={"action": "api_fetch_failed", "error": str(e)}
            )
            # Fall back to persisted cache data (only if it's real non-mock data)
            if cache.has_persisted_data():
                self.logger.warning(
                    f"Using persisted cache data ({len(cache.headlines)} headlines) as fallback",
                    extra_fields={"action": "using_persisted_fallback", "count": len(cache.headlines)}
                )
                return cache.headlines
            # If no persisted real data, try mock news as final fallback
            self.logger.warning(
                "No persisted real data available. Using mock news as final fallback.",
                extra_fields={"action": "using_mock_fallback"}
            )
            mock_headlines = get_mock_news_events()
            # Mark as mock so it won't be persisted
            cache.set_headlines(mock_headlines, is_mock=True)
            return mock_headlines
        finally:
            cache._is_fetching = False
    
    def health_check(self) -> Dict[str, str]:
        """Health check for news ingestion."""
        health = {
            "news_ingestion": "healthy",
            "sources_configured": str(len(self.sources)),
            "recent_headlines": str(len(self.recent_headlines))
        }
        
        for name, source in self.sources.items():
            health[f"source_{name}"] = "active"
        
        return health
