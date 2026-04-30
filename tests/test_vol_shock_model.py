# test_vol_shock_model.py
"""
Unit tests for Volatility Shock Model module.
Tests vol shock prediction from event vectors using neural network
and rule-based fallback modes.
"""
import pytest
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock, patch

from vol_shock_model import VolShockModel, VolShockNN, EVENT_TYPE_ENCODING, SENTIMENT_ENCODING
from schemas import EventVector, EventType, Sentiment, VolShock


class TestVolShockNN:
    """Tests for the VolShockNN neural network."""
    
    def test_nn_forward_pass(self):
        """Test forward pass through the network."""
        model = VolShockNN(hidden_size=32)
        
        # Input: 12 features
        x = torch.randn(1, 12)
        output = model(x)
        
        # Output: 7 deltas
        assert output.shape == (1, 7)
    
    def test_nn_output_range(self):
        """Test that NN output is in reasonable range."""
        model = VolShockNN(hidden_size=32)
        model.eval()
        
        # Test with various inputs
        x = torch.randn(10, 12)
        with torch.no_grad():
            output = model(x)
        
        # Outputs should be bounded by tanh * 0.5
        assert output.min() >= -0.5
        assert output.max() <= 0.5


class TestVolShockModelRuleBased:
    """Tests for rule-based shock prediction."""
    
    def test_rule_based_interest_rate_positive(self):
        """Test rule-based prediction for positive interest rate event."""
        model = VolShockModel()
        model.model_mode = "rulebased"
        
        event = EventVector(
            event_id="test-001",
            headline="Fed raises rates",
            event_type=EventType.INTEREST_RATE,
            sentiment=Sentiment.POSITIVE,
            sentiment_score=0.8,
            importance=0.8,
            surprise_factor=0.5,
            entities={"central_banks": ["Federal Reserve"], "currencies": ["USD"], "indicators": []},
            processed_at=datetime.now(),
            source="test"
        )
        
        shock = model.predict_shock(event)
        
        # Positive sentiment should give negative vol shock (rates up = vol up typically)
        assert isinstance(shock, VolShock)
        assert shock.delta_1W_ATM < 0  # Should be negative for positive sentiment
        assert shock.delta_1M_ATM < 0
        assert abs(shock.delta_1W_ATM) <= 0.5  # Bounded
    
    def test_rule_based_interest_rate_negative(self):
        """Test rule-based prediction for negative interest rate event."""
        model = VolShockModel()
        model.model_mode = "rulebased"
        
        event = EventVector(
            event_id="test-002",
            headline="Fed cuts rates",
            event_type=EventType.INTEREST_RATE,
            sentiment=Sentiment.NEGATIVE,
            sentiment_score=-0.8,
            importance=0.8,
            surprise_factor=0.5,
            entities={"central_banks": ["Federal Reserve"], "currencies": ["USD"], "indicators": []},
            processed_at=datetime.now(),
            source="test"
        )
        
        shock = model.predict_shock(event)
        
        # Negative sentiment should give positive vol shock (rates down = vol down typically)
        assert isinstance(shock, VolShock)
        assert shock.delta_1W_ATM > 0
    
    def test_rule_based_event_type_scaling(self):
        """Test that different event types have different impact patterns."""
        model = VolShockModel()
        model.model_mode = "rulebased"
        
        base_event = EventVector(
            event_id="test-scaling",
            headline="Economic news",
            event_type=EventType.UNKNOWN,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.0,
            importance=0.5,
            surprise_factor=0.3,
            entities={"central_banks": [], "currencies": [], "indicators": []},
            processed_at=datetime.now(),
            source="test"
        )
        
        # Interest rate events should have stronger short-term impact
        ir_event = base_event.model_copy()
        ir_event.event_type = EventType.INTEREST_RATE
        
        macro_event = base_event.model_copy()
        macro_event.event_type = EventType.MACRO
        
        ir_shock = model.predict_shock(ir_event)
        macro_shock = model.predict_shock(macro_event)
        
        # IR events should have higher 1W ATM impact
        assert abs(ir_shock.delta_1W_ATM) >= abs(macro_shock.delta_1W_ATM)
    
    def test_rule_based_importance_scaling(self):
        """Test that higher importance = larger shock."""
        model = VolShockModel()
        model.model_mode = "rulebased"
        
        low_importance = EventVector(
            event_id="test-low",
            headline="Minor news",
            event_type=EventType.MACRO,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.5,
            importance=0.1,
            surprise_factor=0.1,
            entities={},
            processed_at=datetime.now(),
            source="test"
        )
        
        high_importance = low_importance.model_copy()
        high_importance.event_id = "test-high"
        high_importance.importance = 0.9
        
        low_shock = model.predict_shock(low_importance)
        high_shock = model.predict_shock(high_importance)
        
        assert abs(high_shock.delta_1M_ATM) > abs(low_shock.delta_1M_ATM)
    
    def test_rule_based_surprise_boost(self):
        """Test that surprise factor amplifies shock."""
        model = VolShockModel()
        model.model_mode = "rulebased"
        
        low_surprise = EventVector(
            event_id="test-low-surprise",
            headline="Expected event",
            event_type=EventType.INTEREST_RATE,
            sentiment=Sentiment.POSITIVE,
            sentiment_score=0.5,
            importance=0.5,
            surprise_factor=0.1,
            entities={},
            processed_at=datetime.now(),
            source="test"
        )
        
        high_surprise = low_surprise.model_copy()
        high_surprise.event_id = "test-high-surprise"
        high_surprise.surprise_factor = 0.9
        
        low_shock = model.predict_shock(low_surprise)
        high_shock = model.predict_shock(high_surprise)
        
        assert abs(high_shock.delta_1M_ATM) > abs(low_shock.delta_1M_ATM)


class TestVolShockModelRRBF:
    """Tests for Risk Reversal and Butterfly predictions."""
    
    def test_rr_and_bf_present(self):
        """Test that RR and BF values are populated."""
        model = VolShockModel()
        model.model_mode = "rulebased"
        
        event = EventVector(
            event_id="test-rrbf",
            headline="Fed announcement",
            event_type=EventType.CENTRAL_BANK,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.0,
            importance=0.7,
            surprise_factor=0.5,
            entities={},
            processed_at=datetime.now(),
            source="test"
        )
        
        shock = model.predict_shock(event)
        
        assert hasattr(shock, 'delta_1M_25RR')
        assert hasattr(shock, 'delta_1M_25BF')
        # Central bank events should affect RR
        assert shock.delta_1M_25RR != 0 or shock.delta_1M_25BF != 0
    
    def test_rr_sign_correlation(self):
        """Test that RR sign correlates with sentiment direction."""
        model = VolShockModel()
        model.model_mode = "rulebased"
        
        positive_event = EventVector(
            event_id="test-pos",
            headline=" hawkish Fed",
            event_type=EventType.CENTRAL_BANK,
            sentiment=Sentiment.POSITIVE,
            sentiment_score=0.8,
            importance=0.7,
            surprise_factor=0.5,
            entities={},
            processed_at=datetime.now(),
            source="test"
        )
        
        negative_event = positive_event.model_copy()
        negative_event.event_id = "test-neg"
        negative_event.sentiment = Sentiment.NEGATIVE
        negative_event.sentiment_score = -0.8
        
        positive_shock = model.predict_shock(positive_event)
        negative_shock = model.predict_shock(negative_event)
        
        # RR should have opposite signs for opposite sentiments
        assert positive_shock.delta_1M_25RR * negative_shock.delta_1M_25RR < 0


class TestVolShockModelFeatures:
    """Tests for feature preparation."""
    
    def test_prepare_features_shape(self):
        """Test that feature preparation returns correct shape."""
        model = VolShockModel()
        
        event = EventVector(
            event_id="test-feat",
            headline="Test",
            event_type=EventType.INTEREST_RATE,
            sentiment=Sentiment.POSITIVE,
            sentiment_score=0.5,
            importance=0.7,
            surprise_factor=0.3,
            entities={},
            processed_at=datetime.now(),
            source="test"
        )
        
        features = model._prepare_features(event)
        
        assert features.shape == (1, 12)
    
    def test_prepare_features_event_type_encoding(self):
        """Test that event type is properly one-hot encoded."""
        model = VolShockModel()
        
        for event_type in EventType:
            event = EventVector(
                event_id="test",
                headline="Test",
                event_type=event_type,
                sentiment=Sentiment.NEUTRAL,
                sentiment_score=0.0,
                importance=0.5,
                surprise_factor=0.5,
                entities={},
                processed_at=datetime.now(),
                source="test"
            )
            
            features = model._prepare_features(event)
            
            # Find the event type portion (indices 3-9)
            event_type_slice = features[0, 3:9]
            expected = EVENT_TYPE_ENCODING.get(event_type, [0, 0, 0, 0, 0, 1])
            
            np.testing.assert_array_almost_equal(event_type_slice, expected)


class TestVolShockModelCaching:
    """Tests for caching functionality."""
    
    def test_cache_miss_returns_none(self):
        """Test that cache miss returns None."""
        model = VolShockModel()
        model.redis = MagicMock()
        model.redis.get.return_value = None
        
        result = model._get_cached_shock("test-id")
        
        assert result is None
    
    def test_cache_hit_returns_shock(self):
        """Test that cache hit returns VolShock."""
        model = VolShockModel()
        model.redis = MagicMock()
        
        # Create a mock cached shock
        import pickle
        mock_shock = VolShock(
            shock_id="test-id",
            event_vector=EventVector(
                event_id="test-event",
                headline="Test",
                event_type=EventType.UNKNOWN,
                sentiment=Sentiment.NEUTRAL,
                sentiment_score=0.0,
                importance=0.5,
                surprise_factor=0.5,
                entities={},
                processed_at=datetime.now(),
                source="test"
            ),
            delta_1W_ATM=0.1,
            delta_1M_ATM=0.1,
            delta_3M_ATM=0.1,
            delta_6M_ATM=0.1,
            delta_1Y_ATM=0.1,
            delta_1M_25RR=0.05,
            delta_1M_25BF=0.05,
            predicted_at=datetime.now(),
            model_version="test"
        )
        
        model.redis.get.return_value = pickle.dumps(mock_shock.model_dump())
        
        result = model._get_cached_shock("test-id")
        
        assert result is not None
        assert result.shock_id == "test-id"


class TestVolShockModelBatch:
    """Tests for batch prediction."""
    
    def test_batch_prediction(self):
        """Test batch prediction of vol shocks."""
        model = VolShockModel()
        model.model_mode = "rulebased"
        
        events = [
            EventVector(
                event_id=f"batch-{i}",
                headline=f"Event {i}",
                event_type=EventType.INTEREST_RATE,
                sentiment=Sentiment.NEUTRAL,
                sentiment_score=0.0,
                importance=0.5,
                surprise_factor=0.3,
                entities={},
                processed_at=datetime.now(),
                source="test"
            )
            for i in range(5)
        ]
        
        shocks = model.predict_batch(events)
        
        assert len(shocks) == 5
        assert all(isinstance(s, VolShock) for s in shocks)


class TestVolShockModelTraining:
    """Tests for model training functionality."""
    
    def test_training_creates_pytorch_model(self):
        """Test that training creates a PyTorch model."""
        model = VolShockModel()
        model.pytorch_model = None
        
        # Create simple training data
        training_data = []
        for i in range(10):
            event = EventVector(
                event_id=f"train-{i}",
                headline="Training event",
                event_type=EventType.INTEREST_RATE,
                sentiment=Sentiment.NEUTRAL,
                sentiment_score=0.0,
                importance=0.5,
                surprise_factor=0.3,
                entities={},
                processed_at=datetime.now(),
                source="test"
            )
            deltas = [0.1, 0.15, 0.12, 0.1, 0.08, 0.05, 0.03]
            training_data.append((event, deltas))
        
        history = model.train(training_data, epochs=5, batch_size=4)
        
        assert model.pytorch_model is not None
        assert model.model_mode == "pytorch"
        assert "loss" in history
        assert len(history["loss"]) == 5


class TestVolShockModelHealthCheck:
    """Tests for health check functionality."""
    
    def test_health_check_basic(self):
        """Test basic health check."""
        model = VolShockModel()
        model.redis = None
        
        health = model.health_check()
        
        assert "vol_shock_model" in health
        assert health["vol_shock_model"] == "healthy"
        assert "model_mode" in health
        assert "redis" in health


class TestVolShockModelEdgeCases:
    """Edge case tests."""
    
    def test_unknown_event_type(self):
        """Test handling of unknown event type."""
        model = VolShockModel()
        model.model_mode = "rulebased"
        
        event = EventVector(
            event_id="unknown-test",
            headline="Random corporate news",
            event_type=EventType.UNKNOWN,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.0,
            importance=0.3,
            surprise_factor=0.1,
            entities={},
            processed_at=datetime.now(),
            source="test"
        )
        
        shock = model.predict_shock(event)
        
        # Unknown events should still produce valid shocks
        assert isinstance(shock, VolShock)
        assert shock.delta_1W_ATM != 0 or shock.delta_1M_ATM != 0
    
    def test_zero_importance(self):
        """Test handling of zero importance."""
        model = VolShockModel()
        model.model_mode = "rulebased"
        
        event = EventVector(
            event_id="zero-importance",
            headline="Very minor news",
            event_type=EventType.MACRO,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.5,
            importance=0.0,
            surprise_factor=0.0,
            entities={},
            processed_at=datetime.now(),
            source="test"
        )
        
        shock = model.predict_shock(event)
        
        # Zero importance should give near-zero shocks
        assert abs(shock.delta_1M_ATM) < 0.1
