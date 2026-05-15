# nlp_engine.py
"""
Module 2: NLP Processing Engine
Uses FinBERT for financial sentiment analysis to extract structured event vectors from news.
"""
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import re
import hashlib
import pickle
import json

import redis
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from transformers import pipeline

from config import config
from schemas import NewsEvent, EventVector, EventType, Sentiment
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class EntityInfo:
    """Extracted entity information."""
    central_banks: List[str]
    currencies: List[str]
    indicators: List[str]


class NLPEngine:
    """
    NLP Engine using FinBERT for financial sentiment analysis.
    
    Responsibilities:
    1. Sentiment analysis using FinBERT
    2. Event type classification
    3. Entity extraction (central banks, currencies, indicators)
    4. Importance and surprise factor scoring
    5. Caching processed events in Redis
    """
    
    def __init__(
        self,
        model_name: str = "ProsusAI/finbert",
        device: str = "cpu",
        redis_client: Optional[redis.Redis] = None
    ):
        """
        Initialize NLP Engine.
        
        Args:
            model_name: HuggingFace model name for FinBERT
            device: Device for inference ('cpu', 'cuda')
            redis_client: Optional Redis client for caching
        """
        self.logger = get_logger(self.__class__.__name__)
        self.model_name = model_name
        self.device = device
        self.redis = redis_client or self._init_redis()
        
        # NLP pipeline
        self.tokenizer = None
        self.model = None
        self.sentiment_pipeline = None
        
        # Cache settings
        self._cache_ttl = 3600  # 1 hour
        self._entity_cache: Dict[str, EntityInfo] = {}
        
        self._initialize_model()
        self.logger.info(f"NLPEngine initialized with model: {model_name}")
    
    def _init_redis(self) -> Optional[redis.Redis]:
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
            self.logger.info("NLP Redis connection established")
            return r
        except redis.ConnectionError as e:
            self.logger.warning(f"NLP Redis connection failed: {e}. Using memory cache only.")
            return None
    
    def _initialize_model(self) -> None:
        """Initialize FinBERT model and tokenizer."""
        import os
        import shutil
        
        try:
            self.logger.info(f"Loading FinBERT model: {self.model_name}")
            
            # Set a custom cache directory to avoid permission issues
            # Use a project-local cache directory
            project_cache_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                ".model_cache"
            )
            os.makedirs(project_cache_dir, exist_ok=True)
            
            # Set environment variable for HuggingFace cache
            os.environ["HF_HOME"] = project_cache_dir
            os.environ["TRANSFORMERS_CACHE"] = project_cache_dir
            
            self.logger.info(f"Using model cache directory: {project_cache_dir}")
            
            # Load tokenizer and model with explicit cache directory
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                cache_dir=project_cache_dir
            )
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                cache_dir=project_cache_dir
            )
            
            # Create sentiment analysis pipeline
            self.sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=self.model,
                tokenizer=self.tokenizer,
                device=0 if self.device == "cuda" else -1,
                truncation=True,
                max_length=512
            )
            
            self.logger.info("FinBERT model loaded successfully")
            
        except PermissionError as e:
            self.logger.error(
                f"PermissionError loading FinBERT model: {e}. "
                f"Check cache directory permissions at {project_cache_dir}. "
                f"Common causes: 1) another user downloading same model (wait); "
                f"2) previous download was canceled (remove lock files)."
            )
            self.logger.warning("NLP engine will use rule-based fallback")
            self.model = None
            self.sentiment_pipeline = None
        except Exception as e:
            self.logger.error(f"Failed to load FinBERT model: {e}")
            self.logger.warning("NLP engine will use rule-based fallback")
            self.model = None
            self.sentiment_pipeline = None
    
    def process_news_event(self, news_event: NewsEvent) -> EventVector:
        """
        Process a news event into a structured EventVector.
        
        Args:
            news_event: Raw news event from ingestion
            
        Returns:
            EventVector with extracted features
        """
        event_id = self._generate_event_id(news_event)
        
        # Check cache first
        cached = self._get_cached_event(event_id)
        if cached:
            self.logger.debug(f"Cache hit for event: {event_id}")
            return cached
        
        # Extract features
        text = self._prepare_text(news_event)
        
        # Get sentiment
        sentiment, sentiment_score = self._analyze_sentiment(text)
        
        # Classify event type
        event_type = self._classify_event_type(news_event.headline, news_event.content)
        
        # Extract entities
        entities = self._extract_entities(news_event.headline)
        
        # Calculate importance and surprise
        importance = self._calculate_importance(news_event, sentiment_score)
        surprise_factor = self._calculate_surprise(news_event)
        
        event_vector = EventVector(
            event_id=event_id,
            headline=news_event.headline,
            event_type=event_type,
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            importance=importance,
            surprise_factor=surprise_factor,
            entities=entities,
            processed_at=datetime.now(),
            source=news_event.source,
            url=news_event.url
        )
        
        # Cache the result
        self._cache_event(event_id, event_vector)
        
        self.logger.info(
            f"Processed event: {event_vector.event_id[:16]}...",
            extra_fields={
                "event_type": event_vector.event_type.value,
                "sentiment": event_vector.sentiment.value,
                "sentiment_score": round(event_vector.sentiment_score, 3),
                "importance": round(event_vector.importance, 3)
            }
        )
        
        return event_vector
    
    def process_batch(self, news_events: List[NewsEvent]) -> List[EventVector]:
        """
        Process multiple news events in batch.
        
        Args:
            news_events: List of raw news events
            
        Returns:
            List of processed EventVectors
        """
        results = []
        for event in news_events:
            try:
                result = self.process_news_event(event)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Failed to process event: {e}")
                # Create a fallback event vector
                results.append(self._create_fallback_event(event))
        
        return results
    
    def _prepare_text(self, event: NewsEvent) -> str:
        """Prepare text for NLP analysis."""
        parts = [event.headline]
        if event.content:
            # Truncate content to avoid long articles
            content = event.content[:500] if len(event.content) > 500 else event.content
            parts.append(content)
        return " | ".join(parts)
    
    def _analyze_sentiment(self, text: str) -> Tuple[Sentiment, float]:
        """
        Analyze sentiment of text using FinBERT.
        
        Returns:
            Tuple of (Sentiment enum, sentiment_score from -1 to 1)
        """
        if self.sentiment_pipeline is None:
            return self._rule_based_sentiment(text)
        
        try:
            # FinBERT returns: positive, negative, neutral
            result = self.sentiment_pipeline(text[:512])[0]  # Truncate to max length
            
            label = result["label"].lower()
            score = result["score"]
            
            if label == "positive":
                return Sentiment.POSITIVE, score
            elif label == "negative":
                return Sentiment.NEGATIVE, -score
            else:
                return Sentiment.NEUTRAL, 0.0
                
        except Exception as e:
            self.logger.warning(f"Sentiment analysis failed: {e}. Using rule-based fallback.")
            return self._rule_based_sentiment(text)
    
    def _rule_based_sentiment(self, text: str) -> Tuple[Sentiment, float]:
        """
        Rule-based sentiment fallback when FinBERT is unavailable.
        
        Returns:
            Tuple of (Sentiment enum, sentiment_score from -1 to 1)
        """
        text_lower = text.lower()
        
        positive_words = [
            "rise", "rally", "surge", "gain", "grow", "increase", "positive",
            "bullish", "upbeat", "optimistic", "expand", "improve", "strong",
            "higher", "boost", "up", "higher", "boom", "growth"
        ]
        
        negative_words = [
            "fall", "drop", "decline", "lose", "shrink", "decrease", "negative",
            "bearish", "pessimistic", "recession", "weak", "lower", "down",
            "cut", "reduce", "downturn", "contraction", "crisis", "crash"
        ]
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        total = positive_count + negative_count
        if total == 0:
            return Sentiment.NEUTRAL, 0.0
        
        score = (positive_count - negative_count) / total
        
        if score > 0.2:
            return Sentiment.POSITIVE, min(score, 1.0)
        elif score < -0.2:
            return Sentiment.NEGATIVE, max(score, -1.0)
        else:
            return Sentiment.NEUTRAL, score
    
    def _classify_event_type(self, headline: str, content: Optional[str]) -> EventType:
        """
        Classify the type of economic event based on headline and content.
        """
        text = f"{headline} {content or ''}".lower()
        
        # Interest rate patterns
        if any(pattern in text for pattern in [
            "interest rate", "fed rate", "ecb rate", "monetary policy",
            "basis points", "bps", "rate hike", "rate cut", "fomc"
        ]):
            return EventType.INTEREST_RATE
        
        # Inflation patterns
        if any(pattern in text for pattern in [
            "inflation", "cpi", "ppi", "consumer price", "producer price",
            "price index", "hot economy", "soaring prices"
        ]):
            return EventType.INFLATION
        
        # Employment patterns
        if any(pattern in text for pattern in [
            "employment", "jobs", "nfp", "unemployment", "payroll",
            "labor market", "hiring", "workforce"
        ]):
            return EventType.EMPLOYMENT
        
        # Central bank patterns
        if any(pattern in text for pattern in [
            "central bank", "fed", "ecb", "boj", "boe", "mas", "rbi",
            "powell", "lagarde", "kuroda", "bailey"
        ]):
            return EventType.CENTRAL_BANK
        
        # Macro indicators
        if any(pattern in text for pattern in [
            "gdp", "growth", "gdp growth", "economic", "economy",
            "manufacturing", "pmi", "retail sales", "trade balance"
        ]):
            return EventType.MACRO
        
        # Default
        return EventType.UNKNOWN
    
    def _extract_entities(self, headline: str) -> Dict[str, List[str]]:
        """
        Extract financial entities from headline.
        
        Returns:
            Dict with keys: central_banks, currencies, indicators
        """
        entities: Dict[str, List[str]] = {
            "central_banks": [],
            "currencies": [],
            "indicators": []
        }
        
        headline_lower = headline.lower()
        
        # Central banks
        central_bank_patterns = {
            "Federal Reserve": ["fed", "federal reserve", "powell"],
            "ECB": ["ecb", "european central bank", "lagarde"],
            "Bank of Japan": ["boj", "bank of japan", "kuroda", "ueda"],
            "Bank of England": ["boe", "bank of england", "bailey"],
            "MAS": ["mas", "monetary authority"],
            "RBI": ["rbi", "reserve bank of india"]
        }
        
        for bank, patterns in central_bank_patterns.items():
            if any(p in headline_lower for p in patterns):
                if bank not in entities["central_banks"]:
                    entities["central_banks"].append(bank)
        
        # Currencies
        currency_patterns = {
            "USD": ["usd", "dollar", "greenback"],
            "EUR": ["eur", "euro"],
            "JPY": ["jpy", "yen", "japanese yen"],
            "GBP": ["gbp", "pound", "sterling", "cable"],
            "CHF": ["chf", "franc", "swiss"],
            "AUD": ["aud", "australian dollar", "aussie"],
            "CAD": ["cad", "canadian dollar", "loonie"],
            "NZD": ["nzd", "new zealand dollar", "kiwi"]
        }
        
        for currency, patterns in currency_patterns.items():
            if any(p in headline_lower for p in patterns):
                if currency not in entities["currencies"]:
                    entities["currencies"].append(currency)
        
        # Economic indicators
        indicator_patterns = {
            "Interest Rates": ["interest rate", "rate", "basis point"],
            "CPI": ["cpi", "inflation", "consumer price"],
            "PPI": ["ppi", "producer price"],
            "GDP": ["gdp", "growth"],
            "Employment": ["nfp", "payroll", "unemployment", "jobs"],
            "PMI": ["pmi", "purchasing managers"],
            "Retail Sales": ["retail sales"]
        }
        
        for indicator, patterns in indicator_patterns.items():
            if any(p in headline_lower for p in patterns):
                if indicator not in entities["indicators"]:
                    entities["indicators"].append(indicator)
        
        return entities
    
    # Supported currency pairs in the system
    SUPPORTED_PAIRS = [
        "EURUSD", "USDJPY", "GBPUSD", "USDCHF",
        "AUDUSD", "USDCAD", "NZDUSD"
    ]
    
    # Mapping from currency to which pairs contain that currency
    CURRENCY_TO_PAIRS = {
        "USD": ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "NZDUSD"],
        "EUR": ["EURUSD"],
        "JPY": ["USDJPY"],
        "GBP": ["GBPUSD"],
        "CHF": ["USDCHF"],
        "AUD": ["AUDUSD"],
        "CAD": ["USDCAD"],
        "NZD": ["NZDUSD"]
    }
    
    # Mapping from central bank to its currency
    CENTRAL_BANK_TO_CURRENCY = {
        "Federal Reserve": "USD",
        "ECB": "EUR",
        "Bank of Japan": "JPY",
        "Bank of England": "GBP",
        "MAS": "SGD",  # Not in supported pairs but included for completeness
        "RBI": "INR"    # Not in supported pairs but included for completeness
    }
    
    def get_affected_pairs(self, event_vector: EventVector) -> List[str]:
        """
        Determine which currency pairs are affected by a news event.
        
        Uses a multi-step inference process:
        1. Direct currency mentions → map to pairs containing those currencies
        2. Central bank mentions → map to currency of that central bank
        3. Event type inference → boost relevance for specific pairs
        4. Default to all pairs if no specific entities found (global macro event)
        
        Args:
            event_vector: Processed event from NLP engine
            
        Returns:
            List of affected currency pair codes (e.g., ["EURUSD", "GBPUSD"])
        """
        affected_pairs: set = set()
        entities = event_vector.entities
        
        # Step 1: Direct currency mentions
        currencies = entities.get("currencies", [])
        for currency in currencies:
            if currency in self.CURRENCY_TO_PAIRS:
                for pair in self.CURRENCY_TO_PAIRS[currency]:
                    affected_pairs.add(pair)
        
        # Step 2: Central bank mentions
        central_banks = entities.get("central_banks", [])
        for bank in central_banks:
            if bank in self.CENTRAL_BANK_TO_CURRENCY:
                currency = self.CENTRAL_BANK_TO_CURRENCY[bank]
                if currency in self.CURRENCY_TO_PAIRS:
                    for pair in self.CURRENCY_TO_PAIRS[currency]:
                        affected_pairs.add(pair)
        
        # Step 3: Event type inference
        # Certain event types have specific currency implications
        event_type = event_vector.event_type
        headline_lower = event_vector.headline.lower()
        
        if event_type == EventType.INTEREST_RATE or event_type == EventType.CENTRAL_BANK:
            # Interest rate decisions primarily affect the issuing currency
            for bank in central_banks:
                if bank == "Federal Reserve" or bank == "Fed":
                    affected_pairs.update(["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "NZDUSD"])
                elif bank == "ECB":
                    affected_pairs.add("EURUSD")
                elif bank == "Bank of Japan":
                    affected_pairs.add("USDJPY")
                elif bank == "Bank of England":
                    affected_pairs.add("GBPUSD")
        
        elif event_type == EventType.INFLATION:
            # Inflation affects currencies with active central banks fighting inflation
            if any(term in headline_lower for term in ["us inflation", "us cpi", "america inflation"]):
                affected_pairs.update(["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "NZDUSD"])
            elif any(term in headline_lower for term in ["euro zone inflation", "eu inflation", "ecb"]):
                affected_pairs.add("EURUSD")
        
        elif event_type == EventType.EMPLOYMENT:
            # Employment data (NFP) primarily impacts USD
            if any(term in headline_lower for term in ["nfp", "non-farm", "us jobs", "us employment"]):
                affected_pairs.update(["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "NZDUSD"])
        
        elif event_type == EventType.MACRO:
            # GDP and macro data affects the reported currency
            gdp_terms = ["gdp", "growth", "economic activity"]
            if any(term in headline_lower for term in gdp_terms):
                # If US macro mentioned
                if any(term in headline_lower for term in ["us", "united states", "america", "us economy"]):
                    affected_pairs.update(["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "NZDUSD"])
                # If EU macro mentioned
                elif any(term in headline_lower for term in ["euro", "eu", "europe"]):
                    affected_pairs.add("EURUSD")
        
        # Step 4: Fallback - if no specific pairs identified, apply to all
        # This handles global macro events that affect all markets
        if not affected_pairs:
            # Check for truly global events
            global_terms = ["global", "world economy", "trade war", "commodities"]
            if any(term in headline_lower for term in global_terms):
                affected_pairs.update(self.SUPPORTED_PAIRS)
            else:
                # Default: apply to major pairs
                affected_pairs.update(["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"])
        
        return list(affected_pairs)
    
    def _calculate_importance(self, event: NewsEvent, sentiment_score: float) -> float:
        """
        Calculate importance score (0-1) based on multiple factors.
        
        Factors:
        - Source credibility
        - Sentiment extremity
        - Presence of key economic terms
        """
        importance = 0.3  # Base importance
        
        # Source-based importance
        high_priority_sources = ["reuters", "bloomberg", "ap", "fn", "wsj"]
        if any(s in event.source.lower() for s in high_priority_sources):
            importance += 0.2
        
        # Sentiment extremity
        importance += abs(sentiment_score) * 0.2
        
        # Key economic term presence
        key_terms = [
            "fed", "ecb", "interest rate", "inflation", "cpi", "gdp",
            "nfp", "fomc", "central bank", "monetary policy"
        ]
        text = f"{event.headline} {event.content or ''}".lower()
        term_matches = sum(1 for term in key_terms if term in text)
        importance += min(term_matches * 0.05, 0.2)
        
        # URL-based signals (official sources)
        official_domains = [".gov", ".org", "federalreserve", "ecb.europa"]
        if any(domain in event.url.lower() for domain in official_domains):
            importance += 0.1
        
        return min(importance, 1.0)
    
    def _calculate_surprise(self, event: NewsEvent) -> float:
        """
        Calculate surprise factor (0-1) based on market expectations deviation.
        
        This is a simplified implementation. In production, would compare against
        forecast data (e.g., Bloomberg consensus).
        """
        surprise = 0.1  # Base surprise
        
        # Revision indicators (market was expecting different)
        revision_terms = ["revised", "upgraded", "downgraded", "surprise",
                         "unexpected", "missed", "beat", "contrasting"]
        
        text = f"{event.headline} {event.content or ''}".lower()
        revision_matches = sum(1 for term in revision_terms if term in text)
        surprise += revision_matches * 0.15
        
        # Large number indicators
        number_pattern = r'\d+%|\d+\.\d+%|\d+ bps|\d+ basis points'
        if re.search(number_pattern, event.headline):
            surprise += 0.1
        
        return min(surprise, 1.0)
    
    def _generate_event_id(self, event: NewsEvent) -> str:
        """Generate unique event ID."""
        content = f"{event.headline}{event.source}{event.published_at.isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _get_cached_event(self, event_id: str) -> Optional[EventVector]:
        """Get cached event from Redis or memory."""
        cache_key = f"nlp_event:{event_id}"
        
        # Check Redis
        if self.redis:
            try:
                cached_bytes = self.redis.get(cache_key)
                if cached_bytes:
                    data = pickle.loads(cached_bytes)
                    return EventVector(**data)
            except Exception as e:
                self.logger.warning(f"Redis cache get failed: {e}")
        
        return None
    
    def _cache_event(self, event_id: str, event_vector: EventVector) -> None:
        """Cache processed event."""
        cache_key = f"nlp_event:{event_id}"
        
        # Cache in Redis
        if self.redis:
            try:
                self.redis.setex(
                    cache_key,
                    self._cache_ttl,
                    pickle.dumps(event_vector.model_dump())
                )
            except Exception as e:
                self.logger.warning(f"Redis cache set failed: {e}")
    
    def _create_fallback_event(self, news_event: NewsEvent) -> EventVector:
        """Create a fallback EventVector when NLP processing fails."""
        return EventVector(
            event_id=self._generate_event_id(news_event),
            headline=news_event.headline,
            event_type=EventType.UNKNOWN,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.0,
            importance=0.5,
            surprise_factor=0.5,
            entities={"central_banks": [], "currencies": [], "indicators": []},
            processed_at=datetime.now(),
            source=news_event.source,
            url=news_event.url
        )
    
    def health_check(self) -> Dict[str, str]:
        """Health check for NLP engine."""
        health = {
            "nlp_engine": "healthy",
            "model_loaded": str(self.model is not None),
            "model_name": self.model_name,
            "device": self.device
        }
        
        if self.redis:
            try:
                self.redis.ping()
                health["redis"] = "connected"
            except:
                health["redis"] = "disconnected"
        else:
            health["redis"] = "not_configured"
        
        return health


# Utility function for quick sentiment analysis
def quick_sentiment(text: str, model_name: str = "ProsusAI/finbert") -> Tuple[str, float]:
    """
    Quick sentiment analysis for a single text.
    
    Args:
        text: Text to analyze
        model_name: FinBERT model name
        
    Returns:
        Tuple of (sentiment_label, confidence_score)
    """
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        
        pipeline = sentiment_analysis = pipeline(
            "sentiment-analysis",
            model=model,
            tokenizer=tokenizer
        )
        
        result = pipeline(text[:512])[0]
        return result["label"], result["score"]
        
    except Exception as e:
        logger.warning(f"Quick sentiment failed: {e}")
        return "neutral", 0.0
