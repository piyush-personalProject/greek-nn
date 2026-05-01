# modules/nn_risk_engine.py
"""
Module 5: NN Risk Engine
Computes portfolio Greeks using neural networks.
Accepts vol surface as input array, uses ONNX for production inference.
"""
import logging
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import time
from dataclasses import dataclass
import os

import onnxruntime as ort
import torch
import torch.nn as nn

from config import config
from schemas import (
    Portfolio, PortfolioPosition, Greeks, PortfolioGreeks, VolSurface,
    GreeksImpactWeights
)
from logger import get_logger

logger = get_logger(__name__)


class BlackScholesGreeksCPU:
    """
    CPU-based Black-Scholes Greeks computation.
    Used as fallback when NN model unavailable.
    """
    
    @staticmethod
    def d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Compute d1 in Black-Scholes formula."""
        if T <= 0 or sigma <= 0:
            return 0.0
        from scipy.stats import norm
        return (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    
    @staticmethod
    def d2(d1: float, T: float, sigma: float) -> float:
        """Compute d2 in Black-Scholes formula."""
        return d1 - sigma * np.sqrt(T)
    
    @staticmethod
    def delta(S: float, K: float, T: float, r: float, sigma: float, 
              option_type: str) -> float:
        """Compute delta."""
        from scipy.stats import norm
        d1 = BlackScholesGreeksCPU.d1(S, K, T, r, sigma)
        
        if option_type == "CALL":
            return norm.cdf(d1)
        else:  # PUT
            return norm.cdf(d1) - 1
    
    @staticmethod
    def gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Compute gamma."""
        from scipy.stats import norm
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = BlackScholesGreeksCPU.d1(S, K, T, r, sigma)
        return norm.pdf(d1) / (S * sigma * np.sqrt(T))
    
    @staticmethod
    def vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Compute vega (per 1% change in vol)."""
        from scipy.stats import norm
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = BlackScholesGreeksCPU.d1(S, K, T, r, sigma)
        return S * norm.pdf(d1) * np.sqrt(T) / 100  # Per 1% vol change
    
    @staticmethod
    def theta(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str) -> float:
        """Compute theta (per day)."""
        from scipy.stats import norm
        if T <= 0 or sigma <= 0:
            return 0.0
        
        d1 = BlackScholesGreeksCPU.d1(S, K, T, r, sigma)
        d2 = BlackScholesGreeksCPU.d2(d1, T, sigma)
        
        if option_type == "CALL":
            theta = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) - 
                    r * K * np.exp(-r * T) * norm.cdf(d2))
        else:  # PUT
            theta = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) + 
                    r * K * np.exp(-r * T) * norm.cdf(-d2))
        
        return theta / 365  # Per day
    
    @staticmethod
    def rho(S: float, K: float, T: float, r: float, sigma: float,
            option_type: str) -> float:
        """Compute rho (per 1% change in rates)."""
        from scipy.stats import norm
        if T <= 0 or sigma <= 0:
            return 0.0
        
        d2 = BlackScholesGreeksCPU.d2(
            BlackScholesGreeksCPU.d1(S, K, T, r, sigma), T, sigma
        )
        
        if option_type == "CALL":
            return K * T * np.exp(-r * T) * norm.cdf(d2) / 100
        else:  # PUT
            return -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100


class NNRiskEngine:
    """
    Neural Network Risk Engine.
    
    Modes:
    1. ONNX inference (production): Fast, no Python ML deps
    2. PyTorch (dev): Full gradient support
    3. Black-Scholes (fallback): When models unavailable
    """
    
    def __init__(self, model_mode: str = "auto"):
        """
        Initialize risk engine.
        
        Args:
            model_mode: "onnx", "pytorch", "blackscholes", or "auto"
        """
        self.logger = get_logger(self.__class__.__name__)
        self.model_mode = model_mode
        self.onnx_session = None
        self.pytorch_model = None
        self.device = "cpu"
        
        self._initialize_model()
        self.logger.info(f"NNRiskEngine initialized with mode: {self.model_mode}")
    
    def _initialize_model(self) -> None:
        """Initialize the appropriate model backend."""
        
        # Try ONNX first
        if self.model_mode in ["onnx", "auto"]:
            if self._try_load_onnx():
                self.model_mode = "onnx"
                self.logger.info("ONNX model loaded successfully")
                return
            elif self.model_mode == "onnx":
                raise FileNotFoundError(f"ONNX model not found at {config.ml.risk_nn_model_path}")
        
        # Try PyTorch
        if self.model_mode in ["pytorch", "auto"]:
            if self._try_load_pytorch():
                self.model_mode = "pytorch"
                self.logger.info("PyTorch model loaded successfully")
                return
            elif self.model_mode == "pytorch":
                raise FileNotFoundError("PyTorch model not found")
        
        # Fallback to Black-Scholes
        if self.model_mode in ["blackscholes", "auto"]:
            self.model_mode = "blackscholes"
            self.logger.warning("Falling back to Black-Scholes Greeks")
        else:
            raise ValueError(f"Unknown model mode: {self.model_mode}")
    
    def _try_load_onnx(self) -> bool:
        """Try to load ONNX model."""
        try:
            if not os.path.exists(config.ml.risk_nn_model_path):
                return False
            
            self.onnx_session = ort.InferenceSession(
                config.ml.risk_nn_model_path,
                providers=["CPUExecutionProvider"]
            )
            self.logger.info(f"Loaded ONNX model from {config.ml.risk_nn_model_path}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to load ONNX model: {e}")
            return False
    
    def _try_load_pytorch(self) -> bool:
        """Try to load PyTorch model."""
        try:
            # Placeholder for actual PyTorch model loading
            self.device = config.ml.risk_nn_device
            self.logger.info(f"PyTorch model setup on {self.device}")
            return False  # Not implemented in stub
        except Exception as e:
            self.logger.warning(f"Failed to load PyTorch model: {e}")
            return False
    
    def compute_portfolio_greeks(
        self,
        portfolio: Portfolio,
        vol_surface: VolSurface,
        spot_rates: Dict[str, float],
        risk_free_rate: float = 0.05
    ) -> PortfolioGreeks:
        """
        Compute Greeks for entire portfolio.
        
        Args:
            portfolio: Portfolio with positions
            vol_surface: Current vol surface
            spot_rates: Spot rates for instruments
            risk_free_rate: Risk-free rate for discounting
        
        Returns:
            PortfolioGreeks with aggregated and position-level Greeks
        """
        start_time = time.time()
        
        total_greeks = Greeks(
            delta=0.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0
        )
        position_greeks: Dict[str, Greeks] = {}
        
        for position in portfolio.positions:
            try:
                # Get vol for this position's tenor
                vol = self._get_vol_for_position(position, vol_surface)
                
                # Get spot for this instrument
                spot = spot_rates.get(position.instrument, position.spot)
                
                # Compute Greeks
                greeks = self._compute_position_greeks(
                    position, spot, vol, risk_free_rate
                )
                
                position_greeks[position.position_id] = greeks
                total_greeks = total_greeks + greeks
                
            except Exception as e:
                self.logger.error(
                    f"Failed to compute Greeks for position {position.position_id}: {e}",
                    extra_fields={"position_id": position.position_id}
                )
                position_greeks[position.position_id] = Greeks(
                    delta=0, gamma=0, vega=0, theta=0, rho=0
                )
        
        computation_time = (time.time() - start_time) * 1000  # ms
        
        return PortfolioGreeks(
            portfolio_id=portfolio.portfolio_id,
            timestamp=datetime.now(),
            vol_surface_version=vol_surface.version,
            total_greeks=total_greeks,
            position_greeks=position_greeks
        )
    
    def compute_impacted_greeks(
        self,
        portfolio: Portfolio,
        base_vol_surface: VolSurface,
        shocked_vol_surface: VolSurface,
        base_spot_rates: Dict[str, float],
        shocked_spot_rates: Optional[Dict[str, float]] = None,
        weights: GreeksImpactWeights = None,
        risk_free_rate: float = 0.05
    ) -> PortfolioGreeks:
        """
        Compute Greeks with weighted blending between base and shocked states.
        
        This allows calculating impacted Greeks by blending:
        - Greeks computed with live spot rate and base vol surface
        - Greeks computed with shocked vol surface (from news events)
        
        Args:
            portfolio: Portfolio with positions
            base_vol_surface: Base volatility surface
            shocked_vol_surface: Shocked volatility surface (from news)
            base_spot_rates: Live/base spot rates
            shocked_spot_rates: Shocked spot rates (optional - if None, uses base_spot_rates)
            weights: Blending weights for the calculation
            risk_free_rate: Risk-free rate for discounting
            
        Returns:
            PortfolioGreeks with weighted impacted Greeks
        """
        start_time = time.time()
        
        # Default weights if not provided
        if weights is None:
            weights = GreeksImpactWeights(
                spot_rate_weight=0.0,
                vol_shock_weight=1.0,
                spot_shock_weight=0.0
            )
        
        spot_factor, vol_shock_factor, spot_shock_factor = weights.to_blend_factors()
        
        # Compute Greeks with base state
        base_greeks = self.compute_portfolio_greeks(
            portfolio=portfolio,
            vol_surface=base_vol_surface,
            spot_rates=base_spot_rates,
            risk_free_rate=risk_free_rate
        )
        
        # Determine which spot rates to use for shocked calculation
        if shocked_spot_rates is not None and spot_shock_factor > 0:
            shocked_spots = shocked_spot_rates
        else:
            shocked_spots = base_spot_rates
        
        # Compute Greeks with shocked state
        shocked_greeks = self.compute_portfolio_greeks(
            portfolio=portfolio,
            vol_surface=shocked_vol_surface,
            spot_rates=shocked_spots,
            risk_free_rate=risk_free_rate
        )
        
        # Blend the Greeks based on weights
        # Formula: impacted = base * spot_factor + shocked * vol_shock_factor + spot_shocked * spot_shock_factor
        # Where spot_factor + vol_shock_factor + spot_shock_factor = 1.0
        
        total_greeks = Greeks(
            delta=base_greeks.total_greeks.delta * spot_factor + shocked_greeks.total_greeks.delta * vol_shock_factor,
            gamma=base_greeks.total_greeks.gamma * spot_factor + shocked_greeks.total_greeks.gamma * vol_shock_factor,
            vega=base_greeks.total_greeks.vega * spot_factor + shocked_greeks.total_greeks.vega * vol_shock_factor,
            theta=base_greeks.total_greeks.theta * spot_factor + shocked_greeks.total_greeks.theta * vol_shock_factor,
            rho=base_greeks.total_greeks.rho * spot_factor + shocked_greeks.total_greeks.rho * vol_shock_factor,
            vanna=self._blend_optional(base_greeks.total_greeks.vanna, shocked_greeks.total_greeks.vanna, spot_factor, vol_shock_factor),
            volga=self._blend_optional(base_greeks.total_greeks.volga, shocked_greeks.total_greeks.volga, spot_factor, vol_shock_factor)
        )
        
        # Blend position-level Greeks
        position_greeks: Dict[str, Greeks] = {}
        for pos_id in base_greeks.position_greeks:
            base_pos = base_greeks.position_greeks.get(pos_id, Greeks(delta=0, gamma=0, vega=0, theta=0, rho=0))
            shocked_pos = shocked_greeks.position_greeks.get(pos_id, Greeks(delta=0, gamma=0, vega=0, theta=0, rho=0))
            
            position_greeks[pos_id] = Greeks(
                delta=base_pos.delta * spot_factor + shocked_pos.delta * vol_shock_factor,
                gamma=base_pos.gamma * spot_factor + shocked_pos.gamma * vol_shock_factor,
                vega=base_pos.vega * spot_factor + shocked_pos.vega * vol_shock_factor,
                theta=base_pos.theta * spot_factor + shocked_pos.theta * vol_shock_factor,
                rho=base_pos.rho * spot_factor + shocked_pos.rho * vol_shock_factor,
                vanna=self._blend_optional(base_pos.vanna, shocked_pos.vanna, spot_factor, vol_shock_factor),
                volga=self._blend_optional(base_pos.volga, shocked_pos.volga, spot_factor, vol_shock_factor)
            )
        
        computation_time = (time.time() - start_time) * 1000  # ms
        
        return PortfolioGreeks(
            portfolio_id=portfolio.portfolio_id,
            timestamp=datetime.now(),
            vol_surface_version=f"blended_{base_vol_surface.version}_{shocked_vol_surface.version}",
            total_greeks=total_greeks,
            position_greeks=position_greeks
        )
    
    @staticmethod
    def _blend_optional(
        base_val: Optional[float],
        shocked_val: Optional[float],
        spot_factor: float,
        vol_shock_factor: float
    ) -> Optional[float]:
        """Blend optional Greek values."""
        if base_val is None and shocked_val is None:
            return None
        base_val = base_val or 0.0
        shocked_val = shocked_val or 0.0
        return base_val * spot_factor + shocked_val * vol_shock_factor
    
    def _get_vol_for_position(self, position: PortfolioPosition, 
                             vol_surface: VolSurface) -> float:
        """Get volatility for position from surface."""
        # Find closest tenor
        tenor_idx = np.searchsorted(vol_surface.tenors, position.tenor)
        tenor_idx = np.clip(tenor_idx, 0, len(vol_surface.tenors) - 1)
        
        # ATM vol (strike index 0) - volatilities is list of lists, not numpy array
        return float(vol_surface.volatilities[tenor_idx][0])
    
    def _compute_position_greeks(
        self,
        position: PortfolioPosition,
        spot: float,
        vol: float,
        risk_free_rate: float
    ) -> Greeks:
        """Compute Greeks for a single position."""
        
        if self.model_mode == "onnx":
            return self._compute_greeks_onnx(position, spot, vol, risk_free_rate)
        elif self.model_mode == "pytorch":
            return self._compute_greeks_pytorch(position, spot, vol, risk_free_rate)
        else:  # blackscholes
            return self._compute_greeks_blackscholes(position, spot, vol, risk_free_rate)
    
    def _compute_greeks_onnx(
        self,
        position: PortfolioPosition,
        spot: float,
        vol: float,
        risk_free_rate: float
    ) -> Greeks:
        """Compute Greeks using ONNX model."""
        
        # Prepare input for NN
        # Expected format: [spot, strike, tenor, vol, rate, option_type]
        option_type_encoded = 1.0 if position.option_type == "CALL" else 0.0
        
        input_array = np.array([[
            float(spot),
            float(position.strike),
            float(position.tenor),
            float(vol),
            float(risk_free_rate),
            option_type_encoded
        ]], dtype=np.float32)
        
        try:
            # Run inference
            output = self.onnx_session.run(None, {"input": input_array})
            
            # Expected output: [delta, gamma, vega, theta, rho]
            delta, gamma, vega, theta, rho = output[0][0]
            
            # Scale by position quantity
            return Greeks(
                delta=float(delta) * position.quantity,
                gamma=float(gamma) * position.quantity,
                vega=float(vega) * position.quantity,
                theta=float(theta) * position.quantity,
                rho=float(rho) * position.quantity
            )
        except Exception as e:
            self.logger.warning(f"ONNX inference failed: {e}. Falling back to BS.")
            return self._compute_greeks_blackscholes(
                position, spot, vol, risk_free_rate
            )
    
    def _compute_greeks_pytorch(
        self,
        position: PortfolioPosition,
        spot: float,
        vol: float,
        risk_free_rate: float
    ) -> Greeks:
        """Compute Greeks using PyTorch model (stub)."""
        # Placeholder - would use self.pytorch_model
        return self._compute_greeks_blackscholes(
            position, spot, vol, risk_free_rate
        )
    
    def _compute_greeks_blackscholes(
        self,
        position: PortfolioPosition,
        spot: float,
        vol: float,
        risk_free_rate: float
    ) -> Greeks:
        """Compute Greeks using Black-Scholes formulas."""
        
        bs = BlackScholesGreeksCPU
        
        delta = bs.delta(spot, position.strike, position.tenor, 
                        risk_free_rate, vol, position.option_type)
        gamma = bs.gamma(spot, position.strike, position.tenor,
                        risk_free_rate, vol)
        vega = bs.vega(spot, position.strike, position.tenor,
                      risk_free_rate, vol)
        theta = bs.theta(spot, position.strike, position.tenor,
                        risk_free_rate, vol, position.option_type)
        rho = bs.rho(spot, position.strike, position.tenor,
                    risk_free_rate, vol, position.option_type)
        
        return Greeks(
            delta=float(delta) * position.quantity,
            gamma=float(gamma) * position.quantity,
            vega=float(vega) * position.quantity,
            theta=float(theta) * position.quantity,
            rho=float(rho) * position.quantity
        )
    
    def compute_bucketed_vega(
        self,
        portfolio: Portfolio,
        vol_surface: VolSurface,
        spot_rates: Dict[str, float],
        risk_free_rate: float = 0.05
    ) -> Dict[str, float]:
        """
        Compute bucketed vega by tenor.
        Useful for understanding vol sensitivity across the curve.
        """
        bucketed_vega = {}
        
        for tenor in vol_surface.tenors:
            tenor_key = f"{tenor:.2f}Y"
            tenor_vega = 0.0
            
            for position in portfolio.positions:
                if abs(position.tenor - tenor) < 0.01:  # Close to this tenor
                    vol = self._get_vol_for_position(position, vol_surface)
                    spot = spot_rates.get(position.instrument, position.spot)
                    
                    greeks = self._compute_position_greeks(
                        position, spot, vol, risk_free_rate
                    )
                    tenor_vega += greeks.vega
            
            if tenor_vega != 0:
                bucketed_vega[tenor_key] = tenor_vega
        
        return bucketed_vega
    
    def health_check(self) -> Dict[str, str]:
        """Health check for risk engine."""
        health = {
            "nn_risk_engine": "healthy",
            "model_mode": self.model_mode
        }
        
        if self.model_mode == "onnx" and self.onnx_session:
            health["onnx_session"] = "active"
        elif self.model_mode == "pytorch" and self.pytorch_model:
            health["pytorch_model"] = "loaded"
        else:
            health["fallback_mode"] = "blackscholes"
        
        return health
    
    def train_and_export(
        self,
        output_path: str = "./models/risk_nn.onnx",
        num_samples: int = 1000,
        epochs: int = 100
    ) -> Dict[str, any]:
        """
        Train SimpleRiskNN model using Black-Scholes as ground truth
        and export to ONNX format.
        
        Args:
            output_path: Path to save the ONNX model
            num_samples: Number of training samples to generate
            epochs: Number of training epochs
            
        Returns:
            Training history
        """
        import os
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        
        # Generate training data using Black-Scholes
        training_data = self._generate_training_data(num_samples)
        
        # Create and train model
        self.pytorch_model = SimpleRiskNN(hidden_size=64)
        history = self.pytorch_model.train_model(training_data, epochs=epochs)
        
        # Export to ONNX
        pytorch_path = output_path.replace(".onnx", ".pt")
        self.pytorch_model.save_model(pytorch_path)
        self.pytorch_model.export_onnx(output_path)
        
        self.logger.info(f"Model trained and exported to {output_path}")
        
        return history
    
    def _generate_training_data(
        self,
        num_samples: int
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Generate training data using Black-Scholes formulas.
        
        Args:
            num_samples: Number of samples to generate
            
        Returns:
            List of (input_features, greeks_targets)
        """
        np.random.seed(42)  # For reproducibility
        
        training_data = []
        
        for _ in range(num_samples):
            # Random spot (80-120), strike (80-120), tenor (0.1-2), vol (0.1-0.5), rate (0.01-0.1)
            spot = np.random.uniform(80, 120)
            strike = np.random.uniform(80, 120)
            tenor = np.random.uniform(0.1, 2.0)
            vol = np.random.uniform(0.1, 0.5)
            rate = np.random.uniform(0.01, 0.1)
            option_type = np.random.choice(["CALL", "PUT"])
            option_type_encoded = 1.0 if option_type == "CALL" else 0.0
            
            # Input features
            input_features = np.array([
                spot, strike, tenor, vol, rate, option_type_encoded
            ], dtype=np.float32)
            
            # Compute Black-Scholes Greeks as targets
            bs = BlackScholesGreeksCPU
            delta = bs.delta(spot, strike, tenor, rate, vol, option_type)
            gamma = bs.gamma(spot, strike, tenor, rate, vol)
            vega = bs.vega(spot, strike, tenor, rate, vol)
            theta = bs.theta(spot, strike, tenor, rate, vol, option_type)
            rho = bs.rho(spot, strike, tenor, rate, vol, option_type)
            
            greeks_targets = np.array([delta, gamma, vega, theta, rho], dtype=np.float32)
            
            training_data.append((input_features, greeks_targets))
        
        return training_data


# Utility for training a simple NN model (stub)
class SimpleRiskNN(nn.Module):
    """
    Simple neural network for Greeks prediction.
    Input: [spot, strike, tenor, vol, rate, option_type]
    Output: [delta, gamma, vega, theta, rho]
    
    In production, this would be much more sophisticated.
    """
    
    def __init__(self, hidden_size: int = 64):
        super().__init__()
        self.fc1 = nn.Linear(6, hidden_size)
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.fc3 = nn.Linear(hidden_size, 5)  # 5 Greeks
        self.relu = nn.ReLU()
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        x = self.fc3(x)
        return x
    
    def train_model(
        self,
        training_data: List[Tuple[np.ndarray, np.ndarray]],
        epochs: int = 100,
        learning_rate: float = 0.001,
        batch_size: int = 32
    ) -> Dict[str, List[float]]:
        """
        Train the neural network.
        
        Args:
            training_data: List of (input_features, greeks_targets) training examples
                          Input: [spot, strike, tenor, vol, rate, option_type]
                          Output: [delta, gamma, vega, theta, rho]
            epochs: Number of training epochs
            learning_rate: Learning rate
            batch_size: Batch size
            
        Returns:
            Training history with loss per epoch
        """
        import torch.utils.data
        
        self.train()
        
        optimizer = torch.optim.Adam(self.parameters(), lr=learning_rate)
        criterion = nn.MSELoss()
        
        history = {"loss": []}
        
        # Prepare all features and labels
        all_features = torch.FloatTensor(np.array([x[0] for x in training_data]))
        all_labels = torch.FloatTensor(np.array([x[1] for x in training_data]))
        
        dataset = torch.utils.data.TensorDataset(all_features, all_labels)
        dataloader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)
        
        for epoch in range(epochs):
            epoch_loss = 0.0
            num_batches = 0
            
            for batch_features, batch_labels in dataloader:
                optimizer.zero_grad()
                
                outputs = self(batch_features)
                loss = criterion(outputs, batch_labels)
                
                loss.backward()
                optimizer.step()
                
                epoch_loss += loss.item()
                num_batches += 1
            
            avg_loss = epoch_loss / num_batches
            history["loss"].append(avg_loss)
            
            if (epoch + 1) % 10 == 0:
                logger.info(f"Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.6f}")
        
        return history
    
    def save_model(self, path: str) -> None:
        """Save PyTorch model to file."""
        torch.save(self.state_dict(), path)
        logger.info(f"PyTorch model saved to {path}")
    
    def load_model(self, path: str) -> None:
        """Load PyTorch model from file."""
        self.load_state_dict(torch.load(path, map_location='cpu'))
        logger.info(f"PyTorch model loaded from {path}")
    
    def export_onnx(self, path: str) -> None:
        """Export PyTorch model to ONNX format."""
        self.eval()
        
        # Create dummy input matching expected format
        dummy_input = torch.zeros(1, 6)
        
        # Export using legacy ONNX opset version for compatibility
        # Suppress Unicode output by redirecting to avoid emoji issues on Windows
        import sys
        import io
        
        # Capture stdout during export to avoid Unicode errors on Windows
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        try:
            torch.onnx.export(
                self,
                dummy_input,
                path,
                input_names=["input"],
                output_names=["output"],
                opset_version=14
            )
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        logger.info(f"ONNX model exported to {path}")
