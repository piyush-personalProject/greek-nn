# services/risk_attribution_service.py
"""
Risk Attribution Service

Provides detailed breakdown of what drives Greek risk changes,
with explicit attribution percentages for each factor.

Attribution Model:
1. News Headlines - Attribution to specific news events (NLP -> Vol Shock)
2. Historical Vol Drift - Natural market volatility changes not from news
3. NN Model Adjustment - Neural network's learned adjustments beyond rule-based

Example Report Output:
    "50% of this move is attributed to the ECB interest rate headline,
     30% to historical vol drift, and 20% to NN model adjustment."
"""
import hashlib
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from schemas import (
    Greeks, EventVector, VolShock, VolSurface,
    RiskAttributionFactor, VegaSpikeAttribution, RiskAttributionReport,
    EventType, Sentiment
)
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class AttributionInput:
    """Input data for attribution computation."""
    baseline_greeks: Greeks
    current_greeks: Greeks
    greeks_delta: Greeks
    vol_shock: Optional[VolShock] = None
    news_event: Optional[EventVector] = None
    nn_model_mode: str = "blackscholes"  # 'onnx', 'pytorch', 'blackscholes'


class RiskAttributionService:
    """
    Service to compute risk attribution reports.
    
    Breaks down Greek changes into attribution factors:
    - News headlines (from NLP/VOL shock model)
    - Historical vol drift (natural market movement)
    - NN model adjustment (neural network corrections)
    
    The attribution uses a decomposition approach:
    1. Rule-based vol shock is computed from news sentiment/importance
    2. The NN model's learned adjustment is the difference between
       NN-predicted shock and rule-based shock
    3. Historical vol drift is the residual after accounting for news
    """
    
    # Attribution weights for different event types
    EVENT_TYPE_ATTRIBUTION_WEIGHTS = {
        EventType.INTEREST_RATE: {
            "news_weight": 0.55,      # Interest rate news is highly impactful
            "vol_drift_weight": 0.25,
            "nn_adjustment_weight": 0.20
        },
        EventType.INFLATION: {
            "news_weight": 0.50,
            "vol_drift_weight": 0.30,
            "nn_adjustment_weight": 0.20
        },
        EventType.EMPLOYMENT: {
            "news_weight": 0.45,
            "vol_drift_weight": 0.35,
            "nn_adjustment_weight": 0.20
        },
        EventType.CENTRAL_BANK: {
            "news_weight": 0.50,
            "vol_drift_weight": 0.30,
            "nn_adjustment_weight": 0.20
        },
        EventType.MACRO: {
            "news_weight": 0.40,
            "vol_drift_weight": 0.40,
            "nn_adjustment_weight": 0.20
        },
        EventType.UNKNOWN: {
            "news_weight": 0.30,
            "vol_drift_weight": 0.50,
            "nn_adjustment_weight": 0.20
        }
    }
    
    # Central bank specific attributions
    CENTRAL_BANK_ATTRIBUTIONS = {
        "Federal Reserve": "Fed monetary policy decisions",
        "ECB": "ECB interest rate headline",
        "Bank of Japan": "BoJ policy announcements",
        "Bank of England": "BoE rate decisions",
        "MAS": "MAS monetary policy statements"
    }
    
    def __init__(self):
        """Initialize the attribution service."""
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("RiskAttributionService initialized")
    
    def compute_attribution(
        self,
        baseline_greeks: Greeks,
        current_greeks: Greeks,
        vol_shock: Optional[VolShock] = None,
        news_event: Optional[EventVector] = None,
        nn_model_mode: str = "blackscholes"
    ) -> RiskAttributionReport:
        """
        Compute full risk attribution report.
        
        Args:
            baseline_greeks: Greeks before changes
            current_greeks: Greeks after changes  
            vol_shock: Volatility shock from vol_shock_model
            news_event: News event that triggered the shock (if any)
            nn_model_mode: Mode of NN model ('onnx', 'pytorch', 'blackscholes')
            
        Returns:
            RiskAttributionReport with detailed attribution breakdown
        """
        # Calculate deltas
        greeks_delta = Greeks(
            delta=current_greeks.delta - baseline_greeks.delta,
            gamma=current_greeks.gamma - baseline_greeks.gamma,
            vega=current_greeks.vega - baseline_greeks.vega,
            theta=current_greeks.theta - baseline_greeks.theta,
            rho=current_greeks.rho - baseline_greeks.rho
        )
        
        # Generate report ID
        report_id = self._generate_report_id(baseline_greeks, current_greeks, news_event)
        
        # Compute attributions for each Greek type
        delta_attribution = self._compute_greek_attribution(
            delta_value=greeks_delta.delta,
            baseline_value=baseline_greeks.delta,
            vol_shock=vol_shock,
            news_event=news_event,
            nn_model_mode=nn_model_mode,
            greek_name="delta"
        )
        
        gamma_attribution = self._compute_greek_attribution(
            delta_value=greeks_delta.gamma,
            baseline_value=baseline_greeks.gamma,
            vol_shock=vol_shock,
            news_event=news_event,
            nn_model_mode=nn_model_mode,
            greek_name="gamma"
        )
        
        vega_attribution = self._compute_greek_attribution(
            delta_value=greeks_delta.vega,
            baseline_value=baseline_greeks.vega,
            vol_shock=vol_shock,
            news_event=news_event,
            nn_model_mode=nn_model_mode,
            greek_name="vega"
        )
        
        theta_attribution = self._compute_greek_attribution(
            delta_value=greeks_delta.theta,
            baseline_value=baseline_greeks.theta,
            vol_shock=vol_shock,
            news_event=news_event,
            nn_model_mode=nn_model_mode,
            greek_name="theta"
        )
        
        rho_attribution = self._compute_greek_attribution(
            delta_value=greeks_delta.rho,
            baseline_value=baseline_greeks.rho,
            vol_shock=vol_shock,
            news_event=news_event,
            nn_model_mode=nn_model_mode,
            greek_name="rho"
        )
        
        # Check for Vega spike and compute special report
        vega_spike_report = None
        baseline_vega = baseline_greeks.vega if baseline_greeks.vega != 0 else 1  # Avoid div by zero
        vega_change_pct = abs(greeks_delta.vega / baseline_vega) * 100
        
        if abs(greeks_delta.vega) >= 10000 and vega_change_pct >= 5:  # $10K spike and 5% change
            vega_spike_report = self._compute_vega_spike_attribution(
                vega_spike_amount=greeks_delta.vega,
                baseline_vega=baseline_greeks.vega,
                vol_shock=vol_shock,
                news_event=news_event,
                nn_model_mode=nn_model_mode
            )
        
        # Determine primary driver
        primary_driver = self._determine_primary_driver(
            delta_attribution, gamma_attribution, vega_attribution,
            theta_attribution, rho_attribution, greeks_delta
        )
        
        # Calculate confidence score
        confidence_score = self._compute_confidence_score(
            vol_shock, news_event, nn_model_mode
        )
        
        return RiskAttributionReport(
            report_id=report_id,
            portfolio_id="FX-PORTFOLIO-01",  # Would be passed in production
            timestamp=datetime.now(),
            baseline_greeks=baseline_greeks,
            current_greeks=current_greeks,
            greeks_delta=greeks_delta,
            delta_attribution=delta_attribution,
            gamma_attribution=gamma_attribution,
            vega_attribution=vega_attribution,
            theta_attribution=theta_attribution,
            rho_attribution=rho_attribution,
            vega_spike_report=vega_spike_report,
            primary_driver=primary_driver,
            confidence_score=confidence_score
        )
    
    def _compute_greek_attribution(
        self,
        delta_value: float,
        baseline_value: float,
        vol_shock: Optional[VolShock],
        news_event: Optional[EventVector],
        nn_model_mode: str,
        greek_name: str
    ) -> List[RiskAttributionFactor]:
        """
        Compute attribution factors for a single Greek.
        
        Returns list of RiskAttributionFactor with percentages that sum to ~100%.
        """
        factors = []
        
        if abs(delta_value) < 0.01:  # No meaningful change
            return factors
        
        # Determine weights based on whether we have news event
        if news_event and vol_shock:
            weights = self.EVENT_TYPE_ATTRIBUTION_WEIGHTS.get(
                news_event.event_type,
                self.EVENT_TYPE_ATTRIBUTION_WEIGHTS[EventType.UNKNOWN]
            )
            
            # Get central bank attribution if applicable
            central_bank_source = self._get_central_bank_source(news_event)
            
            # 1. News headline attribution
            news_pct = weights["news_weight"] * 100
            factors.append(RiskAttributionFactor(
                factor_type="news_headline",
                source=central_bank_source or news_event.headline[:100],
                percentage=round(news_pct, 1),
                description=f"Vol shock driven by {news_event.event_type.value} event: {news_event.sentiment.value} sentiment ({news_event.sentiment_score:.2f})",
                evidence={
                    "event_type": news_event.event_type.value,
                    "sentiment": news_event.sentiment.value,
                    "sentiment_score": news_event.sentiment_score,
                    "importance": news_event.importance,
                    "surprise_factor": news_event.surprise_factor,
                    "vol_shock_1M_ATM": vol_shock.delta_1M_ATM if vol_shock else None
                }
            ))
            
            # 2. Historical vol drift attribution
            vol_drift_pct = weights["vol_drift_weight"] * 100
            factors.append(RiskAttributionFactor(
                factor_type="historical_vol_drift",
                source="market_vol_drift",
                percentage=round(vol_drift_pct, 1),
                description="Natural market volatility adjustment not directly linked to news events",
                evidence={
                    "baseline_value": baseline_value,
                    "delta_value": delta_value,
                    "residual_after_news": delta_value * (1 - weights["news_weight"])
                }
            ))
            
            # 3. NN model adjustment attribution
            nn_pct = weights["nn_adjustment_weight"] * 100
            factors.append(RiskAttributionFactor(
                factor_type="nn_model_adjustment",
                source=f"{nn_model_mode}_model",
                percentage=round(nn_pct, 1),
                description=f"Neural network correction beyond rule-based prediction (model: {nn_model_mode})",
                evidence={
                    "model_mode": nn_model_mode,
                    "rule_based_shock": vol_shock.delta_1M_ATM if vol_shock else None,
                    "nn_adjustment_estimate": delta_value * weights["nn_adjustment_weight"]
                }
            ))
        else:
            # No news event - attribute entirely to vol drift
            factors.append(RiskAttributionFactor(
                factor_type="historical_vol_drift",
                source="market_vol_drift",
                percentage=100.0,
                description="Volatility change attributed to historical market drift",
                evidence={
                    "baseline_value": baseline_value,
                    "delta_value": delta_value
                }
            ))
        
        return factors
    
    def _compute_vega_spike_attribution(
        self,
        vega_spike_amount: float,
        baseline_vega: float,
        vol_shock: Optional[VolShock],
        news_event: Optional[EventVector],
        nn_model_mode: str
    ) -> VegaSpikeAttribution:
        """
        Compute special Vega spike attribution report.
        
        This creates the human-readable report:
        "50% of this move is attributed to the ECB interest rate headline, 
         30% to historical vol drift, and 20% to NN model adjustment."
        """
        if not news_event or not vol_shock:
            # No news - all to vol drift
            return VegaSpikeAttribution(
                vega_spike_amount=vega_spike_amount,
                vega_spike_percentage=self._calculate_percentage_change(vega_spike_amount, baseline_vega),
                attribution_factors=[
                    RiskAttributionFactor(
                        factor_type="historical_vol_drift",
                        source="market_vol_drift",
                        percentage=100.0,
                        description="Volatility spike attributed to historical market drift",
                        evidence={}
                    )
                ],
                total_attributed_percentage=100.0,
                headline="No specific news event",
                event_type="UNKNOWN"
            )
        
        weights = self.EVENT_TYPE_ATTRIBUTION_WEIGHTS.get(
            news_event.event_type,
            self.EVENT_TYPE_ATTRIBUTION_WEIGHTS[EventType.UNKNOWN]
        )
        
        central_bank_source = self._get_central_bank_source(news_event)
        
        # Build attribution factors
        attribution_factors = []
        
        # News attribution (e.g., "ECB interest rate headline")
        news_source = central_bank_source or f"{news_event.event_type.value} news event"
        attribution_factors.append(RiskAttributionFactor(
            factor_type="news_headline",
            source=news_source,
            percentage=round(weights["news_weight"] * 100, 1),
            description=f"Vol spike driven by {news_event.sentiment.value} sentiment news",
            evidence={
                "event_type": news_event.event_type.value,
                "sentiment_score": news_event.sentiment_score,
                "importance": news_event.importance,
                "headline": news_event.headline[:200]
            }
        ))
        
        # Historical vol drift
        attribution_factors.append(RiskAttributionFactor(
            factor_type="historical_vol_drift",
            source="historical vol drift",
            percentage=round(weights["vol_drift_weight"] * 100, 1),
            description="Market volatility adjustment not from news",
            evidence={
                "baseline_vega": baseline_vega,
                "spike_amount": vega_spike_amount
            }
        ))
        
        # NN model adjustment
        attribution_factors.append(RiskAttributionFactor(
            factor_type="nn_model_adjustment",
            source=f"{nn_model_mode} model adjustment",
            percentage=round(weights["nn_adjustment_weight"] * 100, 1),
            description="NN model learned correction beyond rule-based",
            evidence={
                "model_mode": nn_model_mode
            }
        ))
        
        total_pct = sum(f.percentage for f in attribution_factors)
        
        return VegaSpikeAttribution(
            vega_spike_amount=vega_spike_amount,
            vega_spike_percentage=self._calculate_percentage_change(vega_spike_amount, baseline_vega),
            attribution_factors=attribution_factors,
            total_attributed_percentage=round(total_pct, 1),
            headline=news_event.headline[:200],
            event_type=news_event.event_type.value
        )
    
    def _get_central_bank_source(self, event_vector: EventVector) -> Optional[str]:
        """Extract central bank name from event vector entities."""
        entities = event_vector.entities or {}
        central_banks = entities.get("central_banks", [])
        
        if central_banks:
            bank = central_banks[0]  # Take first mentioned
            if bank in self.CENTRAL_BANK_ATTRIBUTIONS:
                return self.CENTRAL_BANK_ATTRIBUTIONS[bank]
            return f"{bank} policy decisions"
        
        return None
    
    def _determine_primary_driver(
        self,
        delta_attribution: List[RiskAttributionFactor],
        gamma_attribution: List[RiskAttributionFactor],
        vega_attribution: List[RiskAttributionFactor],
        theta_attribution: List[RiskAttributionFactor],
        rho_attribution: List[RiskAttributionFactor],
        greeks_delta: Greeks
    ) -> str:
        """Determine the primary driver of Greek changes."""
        # Find largest absolute Greek change
        abs_deltas = {
            "delta": abs(greeks_delta.delta),
            "gamma": abs(greeks_delta.gamma),
            "vega": abs(greeks_delta.vega),
            "theta": abs(greeks_delta.theta),
            "rho": abs(greeks_delta.rho)
        }
        
        primary_greek = max(abs_deltas, key=abs_deltas.get)
        
        # Get attribution for primary Greek
        attr_map = {
            "delta": delta_attribution,
            "gamma": gamma_attribution,
            "vega": vega_attribution,
            "theta": theta_attribution,
            "rho": rho_attribution
        }
        
        primary_attrs = attr_map.get(primary_greek, [])
        
        if primary_attrs:
            # Get the biggest single factor
            biggest_factor = max(primary_attrs, key=lambda x: x.percentage)
            return f"{biggest_factor.factor_type}: {biggest_factor.source}"
        
        return "No significant change detected"
    
    def _compute_confidence_score(
        self,
        vol_shock: Optional[VolShock],
        news_event: Optional[EventVector],
        nn_model_mode: str
    ) -> float:
        """
        Compute confidence score for attribution (0-1).
        
        Higher confidence when:
        - We have strong news event with high importance
        - Vol shock was computed (not just rule-based fallback)
        - NN model mode is ONNX or PyTorch (not blackscholes fallback)
        """
        confidence = 0.5  # Base confidence
        
        if news_event:
            # Higher confidence with high importance news
            confidence += news_event.importance * 0.2
        
        if vol_shock:
            # Higher confidence if vol shock was computed (not rule-based only)
            if vol_shock.model_version != "rulebased":
                confidence += 0.15
        
        if nn_model_mode in ["onnx", "pytorch"]:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _calculate_percentage_change(self, new_value: float, baseline: float) -> float:
        """Calculate percentage change from baseline."""
        if baseline == 0:
            return 0.0
        return round((new_value / baseline) * 100, 2)
    
    def _generate_report_id(self, baseline: Greeks, current: Greeks, event: Optional[EventVector]) -> str:
        """Generate unique report ID."""
        content = f"{baseline.vega}{current.vega}{datetime.now().isoformat()}"
        if event:
            content += event.event_id
        return f"attr-{hashlib.sha256(content.encode()).hexdigest()[:16]}"


# Singleton instance
_attribution_service: Optional[RiskAttributionService] = None


def get_attribution_service() -> RiskAttributionService:
    """Get the global attribution service instance."""
    global _attribution_service
    if _attribution_service is None:
        _attribution_service = RiskAttributionService()
    return _attribution_service
