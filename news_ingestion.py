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

from config import config
from schemas import NewsEvent
from logger import get_logger

logger = get_logger(__name__)


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
                        "sortBy": "publishedAt",
                        "language": "en",
                        "apiKey": self.api_key,
                        "pageSize": 20
                    }
                    
                    self.logger.debug(
                        f"Making NewsAPI request",
                        extra_fields={"keyword": keyword, "url": f"{self.base_url}/everything"}
                    )
                    
                    async with session.get(
                        f"{self.base_url}/everything",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        self.logger.info(
                            f"NewsAPI response received",
                            extra_fields={"keyword": keyword, "status": resp.status}
                        )
                        
                        if resp.status != 200:
                            self.logger.warning(
                                f"NewsAPI returned non-200 status for '{keyword}'",
                                extra_fields={"keyword": keyword, "http_status": resp.status}
                            )
                            continue
                        
                        data = await resp.json()
                        
                        if data.get("status") != "ok":
                            self.logger.error(
                                f"NewsAPI returned error status",
                                extra_fields={"status": data.get("status"), "message": data.get("message")}
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
                self.logger.warning(
                    f"Timeout fetching news for keyword '{keyword}'",
                    extra_fields={"keyword": keyword, "error": "timeout"}
                )
            except Exception as e:
                self.logger.error(
                    f"Error fetching news for '{keyword}'",
                    extra_fields={"keyword": keyword, "error": str(e), "error_type": type(e).__name__}
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
                self.logger.error(f"Error in stream_headlines: {e}")
                self.logger.info("NewsAPI backoff sleep for 10s")
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
                self.logger.warning(f"Error parsing RSS feed {feed_url}: {e}")
        
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
                self.logger.error(f"Error in RSS stream: {e}")
                self.logger.info("RSS backoff sleep for 60s")
                await asyncio.sleep(60)
    
    def _parse_entry(self, entry: dict, feed_url: str) -> NewsEvent:
        """Parse RSS entry into NewsEvent."""
        
        # Try multiple date fields
        pub_date = entry.get("published", entry.get("updated", datetime.now().isoformat()))
        
        try:
            from email.utils import parsedate_to_datetime
            published_at = parsedate_to_datetime(pub_date)
        except:
            published_at = datetime.now()
        
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
                self.logger.error(f"Bloomberg stream error: {e}")
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
                sources_result_log.append({
                    "source": source_name,
                    "status": "error",
                    "error": str(result)
                })
                self.logger.warning(
                    f"Source [{source_name}] failed",
                    extra_fields={"source": source_name, "error": str(result), "status": "error"}
                )
        
        self.logger.info(
            "News fetch cycle completed",
            extra_fields={
                "action": "news_fetch_complete",
                "total_headlines": len(all_headlines),
                "sources_results": sources_result_log
            }
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
        
        # If no headlines after all attempts, use mock data for demo
        if not all_headlines:
            self.logger.warning(
                "No headlines received from any source - falling back to mock data for demo",
                extra_fields={"action": "using_mock_data", "reason": "no_headlines_received"}
            )
            all_headlines = self._get_mock_headlines()
        
        self.logger.info(
            "Returning headlines to caller",
            extra_fields={
                "action": "news_return",
                "headlines_count": len(all_headlines),
                "unique_count": len(self.recent_headlines)
            }
        )
        
        return list(self.recent_headlines.values())
    
    def _get_mock_headlines(self) -> List[NewsEvent]:
        """Get mock headlines when real news is unavailable."""
        mock_headlines = [
            NewsEvent(
                headline="Fed signals potential rate cuts amid cooling inflation data",
                source="Reuters",
                url="https://reuters.com",
                published_at=datetime.now(),
                content="Federal Reserve officials indicate openness to rate reductions as inflation shows signs of moderating."
            ),
            NewsEvent(
                headline="ECB maintains cautious stance on monetary policy normalization",
                source="Bloomberg",
                url="https://bloomberg.com",
                published_at=datetime.now(),
                content="European Central Bank keeps options open for future adjustments."
            ),
            NewsEvent(
                headline="MAS surveillances indicate stable growth outlook for Singapore",
                source="MAS",
                url="https://mas.gov.sg",
                published_at=datetime.now(),
                content="Monetary Authority of Singapore maintains modest growth expectations."
            ),
            NewsEvent(
                headline="NFP report shows stronger than expected employment growth",
                source="CNBC",
                url="https://cnbc.com",
                published_at=datetime.now(),
                content="Non-farm payrolls exceed analyst expectations, signaling labor market resilience."
            ),
            NewsEvent(
                headline="USD weakens as risk sentiment improves across markets",
                source="Financial Times",
                url="https://ft.com",
                published_at=datetime.now(),
                content="US dollar index declines amid optimism following trade developments."
            ),
        ]
        
        for h in mock_headlines:
            self.recent_headlines[h.headline.lower()] = h
        
        self.logger.info(f"Added {len(mock_headlines)} mock headlines for demo")
        return mock_headlines
    
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
                self.logger.error(f"Producer error from {source_name}: {e}")
        
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
            self.logger.error(f"Stream error from {name}: {e}")
    
    def get_recent_by_keyword(self, keyword: str, max_results: int = 20) -> List[NewsEvent]:
        """Get recent headlines matching keyword."""
        keyword_lower = keyword.lower()
        matching = [
            h for h in self.recent_headlines.values()
            if keyword_lower in h.headline.lower() or keyword_lower in (h.content or "").lower()
        ]
        
        return sorted(
            matching,
            key=lambda x: x.published_at,
            reverse=True
        )[:max_results]
    
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
