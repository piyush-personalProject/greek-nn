# test_nlp_engine.py
"""
Unit tests for NLP Engine module.
Tests sentiment analysis, event classification, entity extraction,
and the complete processing pipeline.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from nlp_engine import NLPEngine
from schemas import NewsEvent, EventVector, EventType, Sentiment


class TestNLPEngineSentiment:
    """Tests for sentiment analysis."""
    
    def test_rule_based_sentiment_positive(self):
        """Test rule-based sentiment for positive text."""
        engine = NLPEngine()
        engine.model = None  # Force rule-based
        
        text = "Markets rally as Fed signals rate cuts"
        sentiment, score = engine._rule_based_sentiment(text)
        
        assert sentiment == Sentiment.POSITIVE
        assert score > 0
    
    def test_rule_based_sentiment_negative(self):
        """Test rule-based sentiment for negative text."""
        engine = NLPEngine()
        engine.model = None
        
        text = "Markets fall on recession fears and inflation concerns"
        sentiment, score = engine._rule_based_sentiment(text)
        
        assert sentiment == Sentiment.NEGATIVE
        assert score < 0
    
    def test_rule_based_sentiment_neutral(self):
        """Test rule-based sentiment for neutral text."""
        engine = NLPEngine()
        engine.model = None
        
        text = "The meeting concluded without immediate decision"
        sentiment, score = engine._rule_based_sentiment(text)
        
        assert sentiment == Sentiment.NEUTRAL


class TestNLPEngineEventClassification:
    """Tests for event type classification."""
    
    def test_classify_interest_rate_event(self):
        """Test classification of interest rate events."""
        engine = NLPEngine()
        
        headline = "Fed raises interest rates by 25 basis points"
        event_type = engine._classify_event_type(headline, None)
        
        assert event_type == EventType.INTEREST_RATE
    
    def test_classify_inflation_event(self):
        """Test classification of inflation events."""
        engine = NLPEngine()
        
        headline = "CPI rises 3.2% exceeding expectations"
        event_type = engine._classify_event_type(headline, None)
        
        assert event_type == EventType.INFLATION
    
    def test_classify_employment_event(self):
        """Test classification of employment events."""
        engine = NLPEngine()
        
        headline = "NFP report shows 250k jobs added"
        event_type = engine._classify_event_type(headline, None)
        
        assert event_type == EventType.EMPLOYMENT
    
    def test_classify_central_bank_event(self):
        """Test classification of central bank events."""
        engine = NLPEngine()
        
        headline = "ECB President Lagarde speaks on monetary policy"
        event_type = engine._classify_event_type(headline, None)
        
        assert event_type == EventType.CENTRAL_BANK
    
    def test_classify_macro_event(self):
        """Test classification of macro events."""
        engine = NLPEngine()
        
        headline = "GDP growth slows to 1.5% in Q3"
        event_type = engine._classify_event_type(headline, None)
        
        assert event_type == EventType.MACRO
    
    def test_classify_unknown_event(self):
        """Test classification of unknown events."""
        engine = NLPEngine()
        
        headline = "Company announces new CEO"
        event_type = engine._classify_event_type(headline, None)
        
        assert event_type == EventType.UNKNOWN


class TestNLPEngineEntityExtraction:
    """Tests for entity extraction."""
    
    def test_extract_fed_entity(self):
        """Test extraction of Federal Reserve entity."""
        engine = NLPEngine()
        
        headline = "Fed signals potential rate cuts amid economic uncertainty"
        entities = engine._extract_entities(headline)
        
        assert "Federal Reserve" in entities["central_banks"]
        assert "USD" in entities["currencies"]
    
    def test_extract_ecb_entity(self):
        """Test extraction of ECB entity."""
        engine = NLPEngine()
        
        headline = "ECB maintains current interest rates"
        entities = engine._extract_entities(headline)
        
        assert "ECB" in entities["central_banks"]
        assert "EUR" in entities["currencies"]
    
    def test_extract_multiple_currencies(self):
        """Test extraction of multiple currency entities."""
        engine = NLPEngine()
        
        headline = "EUR/USD rises while GBP/USD falls against USD/JPY"
        entities = engine._extract_entities(headline)
        
        assert "EUR" in entities["currencies"]
        assert "USD" in entities["currencies"]
        assert "GBP" in entities["currencies"]
        assert "JPY" in entities["currencies"]
    
    def test_extract_indicators(self):
        """Test extraction of economic indicators."""
        engine = NLPEngine()
        
        headline = "CPI inflation data surprises markets"
        entities = engine._extract_entities(headline)
        
        assert "CPI" in entities["indicators"]
        assert "Inflation" in entities["indicators"]
    
    def test_extract_no_entities(self):
        """Test handling of text with no known entities."""
        engine = NLPEngine()
        
        headline = "Random corporate news"
        entities = engine._extract_entities(headline)
        
        assert len(entities["central_banks"]) == 0
        assert len(entities["currencies"]) == 0


class TestNLPEngineImportance:
    """Tests for importance scoring."""
    
    def test_importance_bloomberg_source(self):
        """Test higher importance for Bloomberg source."""
        engine = NLPEngine()
        
        event = NewsEvent(
            headline="Fed cuts rates",
            source="Bloomberg",
            url="https://bloomberg.com",
            published_at=datetime.now()
        )
        
        importance = engine._calculate_importance(event, 0.5)
        
        assert importance > 0.5  # Base + source boost
    
    def test_importance_official_source(self):
        """Test higher importance for official sources."""
        engine = NLPEngine()
        
        event = NewsEvent(
            headline="Fed statement released",
            source="Federal Reserve",
            url="https://federalreserve.gov",
            published_at=datetime.now()
        )
        
        importance = engine._calculate_importance(event, 0.0)
        
        # Should have official domain boost
        assert importance >= 0.3


class TestNLPEngineSurprise:
    """Tests for surprise factor calculation."""
    
    def test_surprise_revision_terms(self):
        """Test higher surprise for revision-related terms."""
        engine = NLPEngine()
        
        event = NewsEvent(
            headline="NFP revised upward, beats expectations",
            source="Reuters",
            url="https://reuters.com",
            published_at=datetime.now()
        )
        
        surprise = engine._calculate_surprise(event)
        
        assert surprise > 0.1  # Should have revision boost
    
    def test_surprise_number_presence(self):
        """Test surprise for headlines with specific numbers."""
        engine = NLPEngine()
        
        event = NewsEvent(
            headline="Fed cuts rates by 50 bps",
            source="Reuters",
            url="https://reuters.com",
            published_at=datetime.now()
        )
        
        surprise = engine._calculate_surprise(event)
        
        assert surprise >= 0.2  # Should have number boost


class TestNLPEnginePipeline:
    """Tests for the complete NLP pipeline."""
    
    def test_process_news_event_basic(self):
        """Test basic event processing."""
        engine = NLPEngine()
        engine.model = None  # Use rule-based
        
        news_event = NewsEvent(
            headline="Fed raises interest rates by 25 basis points",
            source="Reuters",
            url="https://reuters.com/markets",
            published_at=datetime.now(),
            content="The Federal Reserve announced a rate hike."
        )
        
        result = engine.process_news_event(news_event)
        
        assert isinstance(result, EventVector)
        assert result.event_type == EventType.INTEREST_RATE
        assert result.sentiment in [Sentiment.POSITIVE, Sentiment.NEGATIVE]
        assert result.importance >= 0
        assert result.surprise_factor >= 0
        assert "Federal Reserve" in result.entities.get("central_banks", [])
    
    def test_process_news_event_with_cache(self):
        """Test event processing with caching."""
        engine = NLPEngine()
        engine.model = None
        engine.redis = MagicMock()  # Mock Redis
        engine.redis.get.return_value = None  # Cache miss
        
        news_event = NewsEvent(
            headline="ECB meeting concludes",
            source="ECB",
            url="https://ecb.europa.eu",
            published_at=datetime.now()
        )
        
        result1 = engine.process_news_event(news_event)
        result2 = engine.process_news_event(news_event)
        
        # Both should return same event ID
        assert result1.event_id == result2.event_id
    
    def test_process_batch(self):
        """Test batch processing."""
        engine = NLPEngine()
        engine.model = None
        
        events = [
            NewsEvent(
                headline="Fed rate decision",
                source="Fed",
                url="https://federalreserve.gov",
                published_at=datetime.now()
            ),
            NewsEvent(
                headline="CPI data released",
                source="BLS",
                url="https://bls.gov",
                published_at=datetime.now()
            ),
            NewsEvent(
                headline="Employment report",
                source="DOL",
                url="https://dol.gov",
                published_at=datetime.now()
            )
        ]
        
        results = engine.process_batch(events)
        
        assert len(results) == 3
        assert all(isinstance(r, EventVector) for r in results)


class TestNLPEngineFallback:
    """Tests for fallback behavior."""
    
    def test_fallback_event_creation(self):
        """Test fallback event when processing fails."""
        engine = NLPEngine()
        
        news_event = NewsEvent(
            headline="Test headline",
            source="Test",
            url="https://test.com",
            published_at=datetime.now()
        )
        
        result = engine._create_fallback_event(news_event)
        
        assert isinstance(result, EventVector)
        assert result.event_type == EventType.UNKNOWN
        assert result.sentiment == Sentiment.NEUTRAL
        assert result.sentiment_score == 0.0
    
    def test_rule_based_sentiment_edge_cases(self):
        """Test rule-based sentiment with empty/mixed text."""
        engine = NLPEngine()
        
        # Empty text
        sentiment, score = engine._rule_based_sentiment("")
        assert sentiment == Sentiment.NEUTRAL
        assert score == 0.0
        
        # Mixed text (equal positive and negative)
        mixed = "market rises then falls slightly"
        sentiment, score = engine._rule_based_sentiment(mixed)
        assert isinstance(sentiment, Sentiment)


class TestNLPEngineHealthCheck:
    """Tests for health check functionality."""
    
    def test_health_check_basic(self):
        """Test basic health check."""
        engine = NLPEngine()
        engine.redis = None
        
        health = engine.health_check()
        
        assert "nlp_engine" in health
        assert health["nlp_engine"] == "healthy"
        assert "model_loaded" in health
        assert "redis" in health
    
    def test_health_check_with_redis(self):
        """Test health check with Redis connection."""
        engine = NLPEngine()
        engine.redis = MagicMock()
        engine.redis.ping.return_value = True
        
        health = engine.health_check()
        
        assert health["redis"] == "connected"


class TestNLPEngineAffectedPairs:
    """Tests for get_affected_pairs functionality."""
    
    def test_affected_pairs_direct_currency_usd(self):
        """Test direct USD mention maps to correct pairs."""
        engine = NLPEngine()
        
        event = EventVector(
            event_id="test-1",
            headline="USD strengthens against major currencies",
            event_type=EventType.MACRO,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.0,
            importance=0.5,
            surprise_factor=0.1,
            entities={"central_banks": [], "currencies": ["USD"], "indicators": []},
            processed_at=datetime.now(),
            source="Test"
        )
        
        pairs = engine.get_affected_pairs(event)
        
        assert "EURUSD" in pairs
        assert "GBPUSD" in pairs
        assert "AUDUSD" in pairs
        assert "USDCAD" in pairs
        assert "NZDUSD" in pairs
    
    def test_affected_pairs_direct_currency_eur(self):
        """Test direct EUR mention maps to EURUSD."""
        engine = NLPEngine()
        
        event = EventVector(
            event_id="test-2",
            headline="EUR rallies on ECB decision",
            event_type=EventType.CENTRAL_BANK,
            sentiment=Sentiment.POSITIVE,
            sentiment_score=0.5,
            importance=0.7,
            surprise_factor=0.3,
            entities={"central_banks": [], "currencies": ["EUR"], "indicators": []},
            processed_at=datetime.now(),
            source="Test"
        )
        
        pairs = engine.get_affected_pairs(event)
        
        assert "EURUSD" in pairs
    
    def test_affected_pairs_central_bank_fed(self):
        """Test Fed mention maps to USD pairs."""
        engine = NLPEngine()
        
        event = EventVector(
            event_id="test-3",
            headline="Fed signals rate cuts",
            event_type=EventType.CENTRAL_BANK,
            sentiment=Sentiment.POSITIVE,
            sentiment_score=0.3,
            importance=0.8,
            surprise_factor=0.2,
            entities={"central_banks": ["Federal Reserve"], "currencies": [], "indicators": []},
            processed_at=datetime.now(),
            source="Test"
        )
        
        pairs = engine.get_affected_pairs(event)
        
        assert "EURUSD" in pairs
        assert "GBPUSD" in pairs
        assert "AUDUSD" in pairs
    
    def test_affected_pairs_interest_rate_event(self):
        """Test interest rate event affects multiple pairs."""
        engine = NLPEngine()
        
        event = EventVector(
            event_id="test-4",
            headline="Fed raises interest rates by 25 bps",
            event_type=EventType.INTEREST_RATE,
            sentiment=Sentiment.NEGATIVE,
            sentiment_score=-0.2,
            importance=0.9,
            surprise_factor=0.5,
            entities={"central_banks": ["Federal Reserve"], "currencies": [], "indicators": ["Interest Rates"]},
            processed_at=datetime.now(),
            source="Test"
        )
        
        pairs = engine.get_affected_pairs(event)
        
        # Interest rate events should affect multiple USD pairs
        assert len(pairs) >= 2
    
    def test_affected_pairs_inflation_us(self):
        """Test US inflation affects multiple pairs."""
        engine = NLPEngine()
        
        event = EventVector(
            event_id="test-5",
            headline="US CPI rises more than expected",
            event_type=EventType.INFLATION,
            sentiment=Sentiment.NEGATIVE,
            sentiment_score=-0.3,
            importance=0.8,
            surprise_factor=0.4,
            entities={"central_banks": [], "currencies": ["USD"], "indicators": ["CPI"]},
            processed_at=datetime.now(),
            source="Test"
        )
        
        pairs = engine.get_affected_pairs(event)
        
        assert len(pairs) >= 2
    
    def test_affected_pairs_nfp_employment(self):
        """Test NFP employment data affects USD pairs."""
        engine = NLPEngine()
        
        event = EventVector(
            event_id="test-6",
            headline="NFP beats expectations with 250k jobs added",
            event_type=EventType.EMPLOYMENT,
            sentiment=Sentiment.POSITIVE,
            sentiment_score=0.4,
            importance=0.85,
            surprise_factor=0.5,
            entities={"central_banks": [], "currencies": [], "indicators": ["Employment"]},
            processed_at=datetime.now(),
            source="Test"
        )
        
        pairs = engine.get_affected_pairs(event)
        
        # NFP should affect multiple USD pairs
        assert len(pairs) >= 2
    
    def test_affected_pairs_global_macro_fallback(self):
        """Test global events fallback to major pairs."""
        engine = NLPEngine()
        
        event = EventVector(
            event_id="test-7",
            headline="Global trade tensions ease",
            event_type=EventType.MACRO,
            sentiment=Sentiment.POSITIVE,
            sentiment_score=0.3,
            importance=0.6,
            surprise_factor=0.2,
            entities={"central_banks": [], "currencies": [], "indicators": []},
            processed_at=datetime.now(),
            source="Test"
        )
        
        pairs = engine.get_affected_pairs(event)
        
        # Should return default major pairs
        assert "EURUSD" in pairs
        assert "GBPUSD" in pairs
        assert "USDJPY" in pairs
    
    def test_affected_pairs_jpy_boj(self):
        """Test BOJ/JPY affects USDJPY pair."""
        engine = NLPEngine()
        
        event = EventVector(
            event_id="test-8",
            headline="Bank of Japan maintains ultra-low rates",
            event_type=EventType.CENTRAL_BANK,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.0,
            importance=0.7,
            surprise_factor=0.3,
            entities={"central_banks": ["Bank of Japan"], "currencies": [], "indicators": []},
            processed_at=datetime.now(),
            source="Test"
        )
        
        pairs = engine.get_affected_pairs(event)
        
        assert "USDJPY" in pairs
