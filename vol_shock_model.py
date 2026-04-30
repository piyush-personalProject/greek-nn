# vol_shock_model.py
"""
Module 3: Volatility Shock Model
Neural network model to predict volatility surface changes from economic events.
"""
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import hashlib
import pickle
import json

import redis
import torch
import torch.nn as nn
import onnxruntime as ort

from config import config
from schemas import EventVector, VolShock, EventType, Sentiment
from logger import get_logger

logger = get_logger(__name__)


# Event type encoding
EVENT_TYPE_ENCODING = {
    EventType.INTEREST_RATE: [1, 0, 0, 0, 0, 0],
    EventType.INFLATION: [0, 1, 0, 0, 0, 0],
    EventType.EMPLOYMENT: [0, 0, 1, 0, 0, 0],
    EventType.CENTRAL_BANK: [0, 0, 0, 1, 0, 0],
    EventType.MACRO: [0, 0, 0, 0, 1, 0],
    EventType.UNKNOWN: [0, 0, 0, 0, 0, 1],
}

# Sentiment encoding
SENTIMENT_ENCODING = {
    Sentiment.POSITIVE: [1, 0, 0],
    Sentiment.NEUTRAL: [0, 1, 0],
    Sentiment.NEGATIVE: [0, 0, 1],
}


class VolShockNN(nn.Module):
    """
    Neural network for volatility shock prediction.
    
    Input features (12 dimensions):
    - sentiment_score: float (-1 to 1)
    - importance: float (0 to 1)
    - surprise_factor: float (0 to 1)
    - event_type: one-hot encoding (6 dims)
    - sentiment: one-hot encoding (3 dims) - derived from sentiment_score
    
    Output (7 dimensions):
    - delta_1W_ATM: float
    - delta_1M_ATM: float
    - delta_3M_ATM: float
    - delta_6M_ATM: float
    - delta_1Y_ATM: float
    - delta_1M_25RR: float
    - delta_1M_25BF: float
    """
    
    def __init__(self, hidden_size: int = 32):
        super().__init__()
        
        # Input: 12 features (sentiment_score, importance, surprise, 6 event type, 3 sentiment one-hot)
        self.fc1 = nn.Linear(12, hidden_size)
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.fc3 = nn.Linear(hidden_size, hidden_size)
        self.fc4 = nn.Linear(hidden_size, 7)  # 7 output shocks
        
        self.relu = nn.ReLU()
        self.tanh = nn.Tanh()
        self.dropout = nn.Dropout(0.1)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.relu(self.fc2(x))
        x = self.dropout(x)
        x = self.tanh(self.fc3(x))
        x = self.fc4(x)
        
        # Scale output to reasonable vol shock range (-0.5 to 0.5)
        return torch.tanh(x) * 0.5


class VolShockModel:
    """
    Volatility Shock Model.
    
    Predicts volatility surface changes from economic events using:
    1. PyTorch neural network (training mode)
    2. ONNX model (production inference)
    3. Rule-based fallback (when models unavailable)
    
    The model outputs vol shocks per tenor bucket:
    - ATM deltas for: 1W, 1M, 3M, 6M, 1Y
    - 25-delta Risk Reversal (RR) for 1M
    - 25-delta Butterfly (BF) for 1M
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "cpu"
    ):
        """
        Initialize Vol Shock Model.
        
        Args:
            model_path: Path to ONNX model file
            device: Device for inference ('cpu', 'cuda')
        """
        self.logger = get_logger(self.__class__.__name__)
        self.model_path = model_path or config.ml.vol_model_path
        self.device = device
        
        # Model instances
        self.onnx_session: Optional[ort.InferenceSession] = None
        self.pytorch_model: Optional[VolShockNN] = None
        self.model_mode: str = "rulebased"  # 'onnx', 'pytorch', 'rulebased'
        
        # Redis for caching predictions
        self.redis: Optional[redis.Redis] = self._init_redis()
        self._cache_ttl = 300  # 5 min
        
        self._initialize_model()
        self.logger.info(f"VolShockModel initialized in {self.model_mode} mode")
    
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
            self.logger.info("VolShock Redis connection established")
            return r
        except redis.ConnectionError as e:
            self.logger.warning(f"VolShock Redis connection failed: {e}")
            return None
    
    def _initialize_model(self) -> None:
        """Initialize the appropriate model backend."""
        
        # Try ONNX first
        if self._try_load_onnx():
            self.model_mode = "onnx"
            self.logger.info(f"ONNX model loaded from {self.model_path}")
            return
        
        # Try PyTorch
        if self._try_load_pytorch():
            self.model_mode = "pytorch"
            self.logger.info("PyTorch model loaded")
            return
        
        # Fallback to rule-based
        self.model_mode = "rulebased"
        self.logger.warning("No trained model found. Using rule-based shock estimation.")
    
    def _try_load_onnx(self) -> bool:
        """Try to load ONNX model."""
        try:
            if not self.model_path.endswith('.onnx'):
                # Try ONNX path from config
                onnx_path = self.model_path.replace('.pkl', '.onnx')
            else:
                onnx_path = self.model_path
            
            import os
            if not os.path.exists(onnx_path):
                return False
            
            self.onnx_session = ort.InferenceSession(
                onnx_path,
                providers=["CPUExecutionProvider"]
            )
            return True
        except Exception as e:
            self.logger.debug(f"ONNX load failed: {e}")
            return False
    
    def _try_load_pytorch(self) -> bool:
        """Try to load PyTorch model."""
        try:
            self.pytorch_model = VolShockNN(hidden_size=32)
            # Try to load weights
            import os
            pytorch_path = self.model_path.replace('.pkl', '.pt').replace('.onnx', '.pt')
            if os.path.exists(pytorch_path):
                self.pytorch_model.load_state_dict(torch.load(pytorch_path, map_location='cpu'))
            self.pytorch_model.eval()
            return True
        except Exception as e:
            self.logger.debug(f"PyTorch load failed: {e}")
            return False
    
    def predict_shock(self, event_vector: EventVector) -> VolShock:
        """
        Predict volatility shock from an event vector.
        
        Args:
            event_vector: Processed event from NLP engine
            
        Returns:
            VolShock with predicted deltas for each tenor
        """
        # Generate shock ID
        shock_id = self._generate_shock_id(event_vector)
        
        # Check cache
        cached = self._get_cached_shock(shock_id)
        if cached:
            self.logger.debug(f"Cache hit for shock: {shock_id[:16]}")
            return cached
        
        # Prepare input features
        features = self._prepare_features(event_vector)
        
        # Predict based on model mode
        if self.model_mode == "onnx":
            deltas = self._predict_onnx(features)
        elif self.model_mode == "pytorch":
            deltas = self._predict_pytorch(features)
        else:
            deltas = self._predict_rulebased(event_vector)
        
        # Create VolShock
        vol_shock = VolShock(
            shock_id=shock_id,
            event_vector=event_vector,
            delta_1W_ATM=deltas[0],
            delta_1M_ATM=deltas[1],
            delta_3M_ATM=deltas[2],
            delta_6M_ATM=deltas[3],
            delta_1Y_ATM=deltas[4],
            delta_1M_25RR=deltas[5],
            delta_1M_25BF=deltas[6],
            predicted_at=datetime.now(),
            model_version=self.model_mode
        )
        
        # Cache the prediction
        self._cache_shock(shock_id, vol_shock)
        
        self.logger.info(
            f"Predicted vol shock: {shock_id[:16]}...",
            extra_fields={
                "event_type": event_vector.event_type.value,
                "sentiment": event_vector.sentiment.value,
                "delta_1m_atm": round(vol_shock.delta_1M_ATM, 4),
                "model_mode": self.model_mode
            }
        )
        
        return vol_shock
    
    def predict_batch(self, event_vectors: List[EventVector]) -> List[VolShock]:
        """
        Predict volatility shocks for multiple events.
        
        Args:
            event_vectors: List of processed events
            
        Returns:
            List of VolShock predictions
        """
        return [self.predict_shock(ev) for ev in event_vectors]
    
    def _prepare_features(self, event_vector: EventVector) -> np.ndarray:
        """
        Prepare input features for the model.
        
        Feature vector (12 dimensions):
        - sentiment_score: float
        - importance: float
        - surprise_factor: float
        - event_type: one-hot (6 dims)
        - sentiment: one-hot (3 dims) - redundant but helps
        """
        # Base features
        features = [
            event_vector.sentiment_score,  # -1 to 1
            event_vector.importance,       # 0 to 1
            event_vector.surprise_factor,  # 0 to 1
        ]
        
        # Event type one-hot
        event_type_onehot = EVENT_TYPE_ENCODING.get(event_vector.event_type, [0, 0, 0, 0, 0, 1])
        features.extend(event_type_onehot)
        
        # Sentiment one-hot
        sentiment_onehot = SENTIMENT_ENCODING.get(event_vector.sentiment, [0, 1, 0])
        features.extend(sentiment_onehot)
        
        return np.array(features, dtype=np.float32).reshape(1, -1)
    
    def _predict_onnx(self, features: np.ndarray) -> List[float]:
        """Predict using ONNX model."""
        try:
            output = self.onnx_session.run(None, {"input": features})
            deltas = output[0][0]
            return deltas.tolist()
        except Exception as e:
            self.logger.warning(f"ONNX prediction failed: {e}. Falling back to rule-based.")
            return self._predict_rulebased(self._features_to_event(features))
    
    def _predict_pytorch(self, features: np.ndarray) -> List[float]:
        """Predict using PyTorch model."""
        try:
            with torch.no_grad():
                input_tensor = torch.from_numpy(features)
                output = self.pytorch_model(input_tensor)
                return output.numpy()[0].tolist()
        except Exception as e:
            self.logger.warning(f"PyTorch prediction failed: {e}. Falling back to rule-based.")
            return self._predict_rulebased(self._features_to_event(features))
    
    def _features_to_event(self, features: np.ndarray) -> EventVector:
        """Convert features back to EventVector (for fallback)."""
        # This is a placeholder - in reality we'd pass the original event
        return EventVector(
            event_id="fallback",
            headline="fallback",
            event_type=EventType.UNKNOWN,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=float(features[0, 0]),
            importance=float(features[0, 1]),
            surprise_factor=float(features[0, 2]),
            entities={"central_banks": [], "currencies": [], "indicators": []},
            processed_at=datetime.now(),
            source="fallback"
        )
    
    def _predict_rulebased(self, event_vector: EventVector) -> List[float]:
        """
        Rule-based volatility shock prediction.
        
        This is a simplified heuristic model based on market experience:
        - Interest rate events have strong short-term vol impact
        - Employment data affects medium-term vol
        - Central bank communications have prolonged effects
        """
        
        # Base impact scaled by sentiment and importance
        base_impact = event_vector.sentiment_score * event_vector.importance * 0.3
        
        # Event-type specific scaling
        event_type_multipliers = {
            EventType.INTEREST_RATE: {
                "1W": 1.5, "1M": 1.8, "3M": 1.5, "6M": 1.2, "1Y": 1.0,
                "RR": 1.3, "BF": 0.8
            },
            EventType.INFLATION: {
                "1W": 1.3, "1M": 1.5, "3M": 1.6, "6M": 1.4, "1Y": 1.2,
                "RR": 1.2, "BF": 1.0
            },
            EventType.EMPLOYMENT: {
                "1W": 1.0, "1M": 1.2, "3M": 1.4, "6M": 1.3, "1Y": 1.1,
                "RR": 1.1, "BF": 0.9
            },
            EventType.CENTRAL_BANK: {
                "1W": 1.4, "1M": 1.6, "3M": 1.5, "6M": 1.3, "1Y": 1.1,
                "RR": 1.4, "BF": 1.1
            },
            EventType.MACRO: {
                "1W": 0.8, "1M": 1.0, "3M": 1.2, "6M": 1.1, "1Y": 1.0,
                "RR": 0.9, "BF": 0.8
            },
            EventType.UNKNOWN: {
                "1W": 0.5, "1M": 0.6, "3M": 0.6, "6M": 0.5, "1Y": 0.5,
                "RR": 0.5, "BF": 0.5
            }
        }
        
        multipliers = event_type_multipliers.get(
            event_vector.event_type,
            event_type_multipliers[EventType.UNKNOWN]
        )
        
        # Surprise factor amplifies the shock
        surprise_boost = 1.0 + event_vector.surprise_factor * 0.5
        
        # Calculate deltas
        deltas = [
            base_impact * multipliers["1W"] * surprise_boost,  # 1W ATM
            base_impact * multipliers["1M"] * surprise_boost,  # 1M ATM
            base_impact * multipliers["3M"] * surprise_boost,  # 3M ATM
            base_impact * multipliers["6M"] * surprise_boost,  # 6M ATM
            base_impact * multipliers["1Y"] * surprise_boost,  # 1Y ATM
            base_impact * multipliers["RR"] * surprise_boost,  # 1M 25RR
            base_impact * multipliers["BF"] * surprise_boost,  # 1M 25BF
        ]
        
        return deltas
    
    def _generate_shock_id(self, event_vector: EventVector) -> str:
        """Generate unique shock ID."""
        content = f"{event_vector.event_id}{datetime.now().isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _get_cached_shock(self, shock_id: str) -> Optional[VolShock]:
        """Get cached shock from Redis."""
        if not self.redis:
            return None
        
        cache_key = f"vol_shock:{shock_id}"
        try:
            cached_bytes = self.redis.get(cache_key)
            if cached_bytes:
                data = pickle.loads(cached_bytes)
                return VolShock(**data)
        except Exception as e:
            self.logger.warning(f"Redis cache get failed: {e}")
        
        return None
    
    def _cache_shock(self, shock_id: str, vol_shock: VolShock) -> None:
        """Cache predicted shock."""
        if not self.redis:
            return
        
        cache_key = f"vol_shock:{shock_id}"
        try:
            self.redis.setex(
                cache_key,
                self._cache_ttl,
                pickle.dumps(vol_shock.model_dump())
            )
        except Exception as e:
            self.logger.warning(f"Redis cache set failed: {e}")
    
    def train(
        self,
        training_data: List[Tuple[EventVector, List[float]]],
        epochs: int = 50,
        learning_rate: float = 0.001,
        batch_size: int = 32
    ) -> Dict[str, List[float]]:
        """
        Train the neural network model.
        
        Args:
            training_data: List of (EventVector, [7 deltas]) training examples
            epochs: Number of training epochs
            learning_rate: Learning rate
            batch_size: Batch size
            
        Returns:
            Training history with loss per epoch
        """
        if not self.pytorch_model:
            self.pytorch_model = VolShockNN(hidden_size=32)
        
        self.pytorch_model.train()
        
        optimizer = torch.optim.Adam(self.pytorch_model.parameters(), lr=learning_rate)
        criterion = nn.MSELoss()
        
        history = {"loss": []}
        
        # Prepare all features and labels
        all_features = []
        all_labels = []
        
        for event_vector, deltas in training_data:
            features = self._prepare_features(event_vector)
            all_features.append(features[0])
            all_labels.append(deltas)
        
        all_features = torch.FloatTensor(all_features)
        all_labels = torch.FloatTensor(all_labels)
        
        dataset = torch.utils.data.TensorDataset(all_features, all_labels)
        dataloader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)
        
        for epoch in range(epochs):
            epoch_loss = 0.0
            num_batches = 0
            
            for batch_features, batch_labels in dataloader:
                optimizer.zero_grad()
                
                outputs = self.pytorch_model(batch_features)
                loss = criterion(outputs, batch_labels)
                
                loss.backward()
                optimizer.step()
                
                epoch_loss += loss.item()
                num_batches += 1
            
            avg_loss = epoch_loss / num_batches
            history["loss"].append(avg_loss)
            
            if (epoch + 1) % 10 == 0:
                self.logger.info(f"Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.6f}")
        
        self.model_mode = "pytorch"
        self.logger.info("Training complete. Model saved to pytorch mode.")
        
        return history
    
    def save_model(self, path: str) -> None:
        """Save PyTorch model to file."""
        if self.pytorch_model:
            torch.save(self.pytorch_model.state_dict(), path)
            self.logger.info(f"Model saved to {path}")
    
    def export_onnx(self, path: str) -> None:
        """Export PyTorch model to ONNX format."""
        if not self.pytorch_model:
            raise ValueError("No PyTorch model to export")
        
        self.pytorch_model.eval()
        
        # Create dummy input
        dummy_input = torch.zeros(1, 12)
        
        # Export
        torch.onnx.export(
            self.pytorch_model,
            dummy_input,
            path,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}}
        )
        
        self.logger.info(f"ONNX model exported to {path}")
    
    def health_check(self) -> Dict[str, str]:
        """Health check for vol shock model."""
        return {
            "vol_shock_model": "healthy",
            "model_mode": self.model_mode,
            "model_path": self.model_path,
            "redis": "connected" if self.redis else "not_configured"
        }


# Convenience function for end-to-end prediction
def predict_vol_shock_from_event(event_vector: EventVector) -> VolShock:
    """
    Create a VolShockModel and predict shock for an event.
    
    This is a convenience function for one-off predictions.
    For production, create a VolShockModel instance and reuse it.
    """
    model = VolShockModel()
    return model.predict_shock(event_vector)
