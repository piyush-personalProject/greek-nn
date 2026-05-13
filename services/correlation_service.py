# services/correlation_service.py
"""
Correlation Risk Service

Handles cross-asset correlation risk for FX portfolios.
Models correlations between currency pairs and provides:
1. Correlation matrix management
2. Correlation-adjusted Greeks computation
3. Correlation stress testing scenarios
4. Diversification analysis

Correlation Model:
    Portfolio Greeks assume independent positions, but FX pairs are correlated.
    EURUSD and GBPUSD move together (~0.85 correlation)
    EURUSD and USDJPY move opposite (~-0.65 correlation)
    
    When correlated assets move together, risk is HIGHER than sum of parts.
    When uncorrelated assets spread, risk is LOWER (diversification benefit).
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import numpy as np

from schemas import (
    Greeks, CorrelationMatrix, CorrelationAdjustedGreeks,
    CorrelationStressTest, CorrelationStressResult, CorrelationRiskReport,
    RiskAttributionFactor, PortfolioPosition, GreeksImpactWeights, EventVector,
    NewsCorrelationImpact, CorrelationChangeReport
)
from logger import get_logger

logger = get_logger(__name__)


# Default FX correlation matrix based on typical market conditions
DEFAULT_FX_CORRELATIONS = {
    # Major pairs correlations (EURUSD as base)
    ("EURUSD", "GBPUSD"): 0.85,
    ("EURUSD", "AUDUSD"): 0.70,
    ("EURUSD", "NZDUSD"): 0.65,
    ("EURUSD", "USDCAD"): -0.45,
    ("EURUSD", "USDCHF"): -0.60,
    # USDJPY specific
    ("EURUSD", "USDJPY"): -0.65,
    ("GBPUSD", "USDJPY"): -0.55,
    ("AUDUSD", "USDJPY"): -0.50,
    ("USDCAD", "USDJPY"): 0.45,
    ("USDCHF", "USDJPY"): 0.55,
    # Cross pairs
    ("GBPUSD", "AUDUSD"): 0.80,
    ("GBPUSD", "NZDUSD"): 0.75,
    ("AUDUSD", "NZDUSD"): 0.90,
    ("USDCAD", "AUDUSD"): 0.60,
    ("USDCHF", "GBPUSD"): 0.65,
}

# Predefined crisis correlation multipliers (correlations tend to 1.0 during crises)
CRISIS_CORRELATION_SCENARIOS = {
    "2008_lehman": {
        "name": "2008 Lehman Crisis",
        "description": "Global financial crisis - all correlations tend to 1.0",
        "multipliers": {
            # All correlations double (0.5 -> 1.0, 0.85 -> 1.0)
            ("*", "*"): 2.0
        }
    },
    "covid_march_2020": {
        "name": "COVID March 2020",
        "description": "Pandemic crisis - USD strengthens vs all, correlations spike",
        "multipliers": {
            # EURUSD and GBPUSD correlations spike
            ("EURUSD", "GBPUSD"): 2.0,
            ("EURUSD", "AUDUSD"): 2.0,
            ("EURUSD", "NZDUSD"): 2.0,
            # USDJPY correlation with others becomes very negative
            ("EURUSD", "USDJPY"): 2.5,
            # Default for unspecified pairs
            ("*", "*"): 1.5
        }
    },
    "em_stress": {
        "name": "EM Stress",
        "description": "Emerging market currency stress",
        "multipliers": {
            ("AUDUSD", "NZDUSD"): 1.8,
            ("USDCAD", "AUDUSD"): 1.8,
            ("*", "*"): 1.3
        }
    },
    "risk_on_risk_off": {
        "name": "Risk-On/Risk-Off",
        "description": "Risk sentiment drives all correlations toward 1.0",
        "multipliers": {
            ("EURUSD", "GBPUSD"): 1.5,
            ("AUDUSD", "NZDUSD"): 1.5,
            ("EURUSD", "USDJPY"): 1.5,
            ("*", "*"): 1.4
        }
    }
}

# Event-type to correlation multiplier mapping
# When news events occur, correlations shift based on event characteristics
EVENT_CORRELATION_ADJUSTMENTS = {
    "CENTRAL_BANK": {
        "description": "Central bank decisions cause correlated moves in related pairs",
        "multipliers": {
            # Major pairs correlation increases during central bank events
            ("EURUSD", "GBPUSD"): 1.3,
            ("EURUSD", "AUDUSD"): 1.3,
            ("EURUSD", "NZDUSD"): 1.3,
            # USD crosses move together
            ("USDJPY", "USDCHF"): 1.4,
            ("USDCAD", "USDJPY"): 1.2,
            # Default multiplier for unspecified pairs
            ("*", "*"): 1.2
        }
    },
    "INTEREST_RATE": {
        "description": "Interest rate decisions drive correlated moves across yield-sensitive pairs",
        "multipliers": {
            ("EURUSD", "GBPUSD"): 1.4,
            ("AUDUSD", "NZDUSD"): 1.4,
            ("USDCAD", "AUDUSD"): 1.3,
            ("USDJPY", "USDCHF"): 1.5,
            ("*", "*"): 1.3
        }
    },
    "INFLATION": {
        "description": "Inflation data affects all pairs with correlated reaction",
        "multipliers": {
            ("EURUSD", "GBPUSD"): 1.3,
            ("EURUSD", "USDJPY"): 1.4,
            ("AUDUSD", "NZDUSD"): 1.5,
            ("USDCAD", "AUDUSD"): 1.3,
            ("*", "*"): 1.25
        }
    },
    "EMPLOYMENT": {
        "description": "Employment data drives USD correlation spikes",
        "multipliers": {
            ("EURUSD", "GBPUSD"): 1.2,
            ("USDJPY", "USDCHF"): 1.5,
            ("USDCAD", "AUDUSD"): 1.4,
            ("EURUSD", "USDJPY"): 1.3,
            ("*", "*"): 1.2
        }
    },
    "MACRO": {
        "description": "Macro events increase cross-asset correlations",
        "multipliers": {
            ("EURUSD", "GBPUSD"): 1.4,
            ("AUDUSD", "NZDUSD"): 1.4,
            ("EURUSD", "USDJPY"): 1.4,
            ("USDCAD", "AUDUSD"): 1.3,
            ("*", "*"): 1.3
        }
    },
    "GEOPOLITICAL": {
        "description": "Geopolitical risk drives safe-haven correlations",
        "multipliers": {
            # USD, JPY, CHF become positively correlated (safe haven flow)
            ("USDJPY", "USDCHF"): 1.6,
            ("EURUSD", "USDJPY"): 1.3,
            # Commodity currencies correlate
            ("AUDUSD", "NZDUSD"): 1.5,
            ("USDCAD", "AUDUSD"): 1.4,
            ("*", "*"): 1.3
        }
    },
    "EM_STRESS": {
        "description": "EM stress causes commodity currency correlations to spike",
        "multipliers": {
            ("AUDUSD", "NZDUSD"): 1.6,
            ("USDCAD", "AUDUSD"): 1.5,
            ("EURUSD", "GBPUSD"): 1.2,
            ("*", "*"): 1.4
        }
    },
    "NATURAL_DISASTER": {
        "description": "Natural disasters cause commodity currency correlation spikes",
        "multipliers": {
            ("AUDUSD", "NZDUSD"): 1.5,
            ("USDCAD", "AUDUSD"): 1.4,
            ("EURUSD", "GBPUSD"): 1.1,
            ("*", "*"): 1.3
        }
    }
}


@dataclass
class PositionCorrelationInfo:
    """Information about how a position relates to others via correlation."""
    position: PortfolioPosition
    correlated_positions: List[Tuple[PortfolioPosition, float]]  # (position, correlation)
    correlation_contribution: float  # Net contribution from correlations


class CorrelationService:
    """
    Service for cross-asset correlation risk management.
    
    Key capabilities:
    1. Maintain and serve correlation matrices
    2. Compute correlation-adjusted Greeks
    3. Run correlation stress tests
    4. Identify diversification opportunities
    """
    
    def __init__(self, correlation_matrix: Optional[CorrelationMatrix] = None):
        """
        Initialize correlation service.
        
        Args:
            correlation_matrix: Optional custom correlation matrix.
                              If not provided, uses default FX matrix.
        """
        self.logger = get_logger(self.__class__.__name__)
        
        if correlation_matrix is None:
            correlation_matrix = self._create_default_matrix()
        
        self.correlation_matrix = correlation_matrix
        self.news_correlation_history: List[NewsCorrelationImpact] = []
        self.logger.info(f"CorrelationService initialized with matrix: {correlation_matrix.matrix_id}")
    
    def _create_default_matrix(self) -> CorrelationMatrix:
        """Create default FX correlation matrix."""
        pairs = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY"]
        
        # Build full correlation matrix from defaults
        correlations = {}
        for (p1, p2), corr in DEFAULT_FX_CORRELATIONS.items():
            correlations[(p1, p2)] = corr
            correlations[(p2, p1)] = corr
        
        # Add self-correlations (always 1.0)
        for pair in pairs:
            correlations[(pair, pair)] = 1.0
        
        return CorrelationMatrix(
            matrix_id="default-fx-2026",
            pairs=pairs,
            correlations=correlations,
            source="market_data"
        )
    
    def get_correlation_matrix(self) -> CorrelationMatrix:
        """Get the current correlation matrix."""
        return self.correlation_matrix
    
    def update_correlation(self, pair1: str, pair2: str, correlation: float) -> None:
        """
        Update a single correlation in the matrix.
        
        Args:
            pair1: First currency pair
            pair2: Second currency pair
            correlation: New correlation value (-1 to 1)
        """
        correlation = max(-1.0, min(1.0, correlation))  # Clamp to valid range
        self.correlation_matrix.correlations[(pair1, pair2)] = correlation
        self.correlation_matrix.correlations[(pair2, pair1)] = correlation
        self.logger.info(f"Updated correlation {pair1}/{pair2}: {correlation}")
    
    def get_pairs_from_portfolio(self, positions: List[PortfolioPosition]) -> List[str]:
        """Extract unique instrument pairs from portfolio positions."""
        return list(set(pos.instrument for pos in positions))
    
    def compute_correlation_matrix_for_portfolio(
        self, 
        positions: List[PortfolioPosition]
    ) -> np.ndarray:
        """
        Compute correlation matrix for pairs in portfolio.
        
        Returns:
            N x N numpy array of correlations
        """
        pairs = self.get_pairs_from_portfolio(positions)
        n = len(pairs)
        
        if n == 0:
            return np.array([[]])
        
        if n == 1:
            return np.array([[1.0]])
        
        # Build correlation matrix
        corr_matrix = np.eye(n)  # Start with identity
        
        pair_to_idx = {pair: idx for idx, pair in enumerate(pairs)}
        
        for i, pair1 in enumerate(pairs):
            for j, pair2 in enumerate(pairs):
                if i != j:
                    corr = self.correlation_matrix.get_correlation(pair1, pair2)
                    corr_matrix[i, j] = corr
        
        return corr_matrix
    
    def compute_diversification_ratio(
        self,
        raw_greeks: Greeks,
        adjusted_greeks: Greeks
    ) -> float:
        """
        Compute diversification ratio.
        
        Ratio = adjusted_greeks / raw_greeks
        
        - Ratio < 1.0: Diversification benefit (risk reduced by correlations)
        - Ratio = 1.0: No diversification benefit (uncorrelated or concentrated)
        - Ratio > 1.0: Concentration risk (correlations increase effective risk)
        
        A ratio of 0.8 means correlations reduced risk by 20%.
        """
        raw_total = abs(raw_greeks.delta) + abs(raw_greeks.gamma) + abs(raw_greeks.vega)
        adjusted_total = abs(adjusted_greeks.delta) + abs(adjusted_greeks.gamma) + abs(adjusted_greeks.vega)
        
        if raw_total == 0:
            return 1.0
        
        return adjusted_total / raw_total if raw_total != 0 else 1.0
    
    def compute_correlation_adjusted_greeks(
        self,
        positions: List[PortfolioPosition],
        position_greeks: Dict[str, Greeks],
        total_greeks: Greeks,
        correlation_matrix: Optional[CorrelationMatrix] = None
    ) -> CorrelationAdjustedGreeks:
        """
        Compute Greeks adjusted for cross-asset correlations.
        
        The formula for correlation-adjusted variance:
        Var_portfolio = Σ_i Σ_j w_i * w_j * σ_i * σ_j * ρ_ij
        
        For Greeks, we approximate the correlation adjustment as:
        adjusted_vega = raw_vega * (1 + Σ_{j≠i} ρ_ij * (σ_j / σ_total))
        
        Args:
            positions: Portfolio positions
            position_greeks: Greeks per position
            total_greeks: Aggregated total Greeks
            correlation_matrix: Optional custom matrix (uses default if None)
        
        Returns:
            CorrelationAdjustedGreeks with raw, adjusted, and adjustment amounts
        """
        if correlation_matrix is None:
            correlation_matrix = self.correlation_matrix
        
        # Get unique pairs and build correlation matrix
        pairs = self.get_pairs_from_portfolio(positions)
        corr_matrix = self.compute_correlation_matrix_for_portfolio(positions)
        
        if len(pairs) <= 1:
            # Only one pair - no correlation adjustment needed
            return CorrelationAdjustedGreeks(
                raw_greeks=total_greeks,
                adjusted_greeks=total_greeks,
                correlation_adjustment=Greeks(delta=0, gamma=0, vega=0, theta=0, rho=0),
                diversification_benefit=Greeks(delta=0, gamma=0, vega=0, theta=0, rho=0),
                correlation_matrix_id=correlation_matrix.matrix_id,
                pairs_in_portfolio=pairs
            )
        
        # Compute position weights based on vega exposure
        total_vega = sum(abs(pos_g.vega) for pos_g in position_greeks.values())
        if total_vega == 0:
            total_vega = 1.0  # Avoid division by zero
        
        # Build position info by pair
        pair_to_positions: Dict[str, List[Tuple[PortfolioPosition, Greeks]]] = {}
        for pos in positions:
            greeks = position_greeks.get(pos.position_id, Greeks(delta=0, gamma=0, vega=0, theta=0, rho=0))
            if pos.instrument not in pair_to_positions:
                pair_to_positions[pos.instrument] = []
            pair_to_positions[pos.instrument].append((pos, greeks))
        
        # Aggregate Greeks by pair
        pair_greeks: Dict[str, Greeks] = {}
        for pair, pos_list in pair_to_positions.items():
            aggregated = Greeks(delta=0, gamma=0, vega=0, theta=0, rho=0)
            for _, g in pos_list:
                aggregated = aggregated + g
            pair_greeks[pair] = aggregated
        
        # Compute correlation-adjusted Greeks
        # Using the formula: adjusted = raw * correlation_factor
        # where correlation_factor accounts for cross-pair correlations
        
        adjusted_deltas = 0.0
        adjusted_gammas = 0.0
        adjusted_vegas = 0.0
        adjusted_thetas = 0.0
        adjusted_rhos = 0.0
        
        pair_list = list(pair_greeks.keys())
        n_pairs = len(pair_list)
        
        for i, pair1 in enumerate(pair_list):
            g1 = pair_greeks[pair1]
            
            for j, pair2 in enumerate(pair_list):
                g2 = pair_greeks[pair2]
                corr = corr_matrix[i, j] if i < n_pairs and j < n_pairs else (1.0 if i == j else 0.0)
                
                # Weight by relative vega contribution
                weight1 = abs(g1.vega) / total_vega if total_vega != 0 else 1.0 / n_pairs
                weight2 = abs(g2.vega) / total_vega if total_vega != 0 else 1.0 / n_pairs
                
                combined_weight = weight1 * weight2
                
                adjusted_deltas += g1.delta * corr * combined_weight * n_pairs
                adjusted_gammas += g1.gamma * corr * combined_weight * n_pairs
                adjusted_vegas += g1.vega * corr * combined_weight * n_pairs
                adjusted_thetas += g1.theta * corr * combined_weight * n_pairs
                adjusted_rhos += g1.rho * corr * combined_weight * n_pairs
        
        adjusted_greeks = Greeks(
            delta=float(adjusted_deltas),
            gamma=float(adjusted_gammas),
            vega=float(adjusted_vegas),
            theta=float(adjusted_thetas),
            rho=float(adjusted_rhos)
        )
        
        # Compute adjustments
        correlation_adjustment = Greeks(
            delta=adjusted_greeks.delta - total_greeks.delta,
            gamma=adjusted_greeks.gamma - total_greeks.gamma,
            vega=adjusted_greeks.vega - total_greeks.vega,
            theta=adjusted_greeks.theta - total_greeks.theta,
            rho=adjusted_greeks.rho - total_greeks.rho
        )
        
        # Diversification benefit is positive when adjustment reduces risk
        diversification_benefit = Greeks(
            delta=total_greeks.delta - adjusted_greeks.delta if abs(adjusted_greeks.delta) < abs(total_greeks.delta) else 0,
            gamma=total_greeks.gamma - adjusted_greeks.gamma if abs(adjusted_greeks.gamma) < abs(total_greeks.gamma) else 0,
            vega=total_greeks.vega - adjusted_greeks.vega if abs(adjusted_greeks.vega) < abs(total_greeks.vega) else 0,
            theta=total_greeks.theta - adjusted_greeks.theta if abs(adjusted_greeks.theta) < abs(total_greeks.theta) else 0,
            rho=total_greeks.rho - adjusted_greeks.rho if abs(adjusted_greeks.rho) < abs(total_greeks.rho) else 0
        )
        
        return CorrelationAdjustedGreeks(
            raw_greeks=total_greeks,
            adjusted_greeks=adjusted_greeks,
            correlation_adjustment=correlation_adjustment,
            diversification_benefit=diversification_benefit,
            correlation_matrix_id=correlation_matrix.matrix_id,
            pairs_in_portfolio=pairs
        )
    
    def run_stress_test(
        self,
        raw_greeks: Greeks,
        positions: List[PortfolioPosition],
        position_greeks: Dict[str, Greeks],
        scenario: CorrelationStressTest
    ) -> CorrelationStressResult:
        """
        Run a correlation stress test scenario.
        
        Args:
            raw_greeks: Current (baseline) portfolio Greeks
            positions: Portfolio positions
            position_greeks: Greeks per position
            scenario: Stress test scenario to apply
        
        Returns:
            CorrelationStressResult with baseline vs stressed Greeks
        """
        # Build stressed correlation matrix
        stressed_correlations = dict(self.correlation_matrix.correlations)
        
        for (pair1, pair2), multiplier in scenario.correlation_multipliers.items():
            if pair1 == "*" and pair2 == "*":
                # Apply to all correlations
                for key in list(stressed_correlations.keys()):
                    p1, p2 = key
                    stressed_correlations[key] = np.clip(
                        stressed_correlations[key] * multiplier,
                        -1.0, 1.0
                    )
            else:
                # Apply to specific pair
                if (pair1, pair2) in stressed_correlations:
                    stressed_correlations[(pair1, pair2)] = np.clip(
                        stressed_correlations[(pair1, pair2)] * multiplier,
                        -1.0, 1.0
                    )
                if (pair2, pair1) in stressed_correlations:
                    stressed_correlations[(pair2, pair1)] = np.clip(
                        stressed_correlations[(pair2, pair1)] * multiplier,
                        -1.0, 1.0
                    )
        
        stressed_matrix = CorrelationMatrix(
            matrix_id=f"stressed-{scenario.scenario_id}",
            pairs=self.correlation_matrix.pairs,
            correlations=stressed_correlations,
            source="stressed"
        )
        
        # Compute stressed Greeks
        stressed_result = self.compute_correlation_adjusted_greeks(
            positions=positions,
            position_greeks=position_greeks,
            total_greeks=raw_greeks,
            correlation_matrix=stressed_matrix
        )
        
        stressed_greeks = stressed_result.adjusted_greeks
        
        # Compute changes
        greeks_change = Greeks(
            delta=stressed_greeks.delta - raw_greeks.delta,
            gamma=stressed_greeks.gamma - raw_greeks.gamma,
            vega=stressed_greeks.vega - raw_greeks.vega,
            theta=stressed_greeks.theta - raw_greeks.theta,
            rho=stressed_greeks.rho - raw_greeks.rho
        )
        
        # Percentage changes
        def safe_pct(new_val, old_val):
            if old_val == 0:
                return 0.0
            return ((new_val - old_val) / abs(old_val)) * 100
        
        change_percentages = Greeks(
            delta=safe_pct(stressed_greeks.delta, raw_greeks.delta),
            gamma=safe_pct(stressed_greeks.gamma, raw_greeks.gamma),
            vega=safe_pct(stressed_greeks.vega, raw_greeks.vega),
            theta=safe_pct(stressed_greeks.theta, raw_greeks.theta),
            rho=safe_pct(stressed_greeks.rho, raw_greeks.rho)
        )
        
        # Identify highest impact pairs
        pairs = self.get_pairs_from_portfolio(positions)
        highest_impact = []
        for pair in pairs:
            pair_corr_sum = sum(
                abs(self.correlation_matrix.get_correlation(pair, other))
                for other in pairs if other != pair
            )
            highest_impact.append({
                "pair": pair,
                "total_correlation_exposure": round(pair_corr_sum, 2),
                "avg_correlation": round(pair_corr_sum / (len(pairs) - 1) if len(pairs) > 1 else 0, 2)
            })
        
        highest_impact.sort(key=lambda x: x["total_correlation_exposure"], reverse=True)
        
        return CorrelationStressResult(
            scenario=scenario,
            baseline_greeks=raw_greeks,
            stressed_greeks=stressed_greeks,
            greeks_change=greeks_change,
            change_percentages=change_percentages,
            highest_impact_pairs=highest_impact[:5]  # Top 5
        )
    
    def generate_correlation_risk_report(
        self,
        portfolio_id: str,
        positions: List[PortfolioPosition],
        position_greeks: Dict[str, Greeks],
        total_greeks: Greeks
    ) -> CorrelationRiskReport:
        """
        Generate comprehensive correlation risk report.
        
        Args:
            portfolio_id: Portfolio identifier
            positions: Portfolio positions
            position_greeks: Greeks per position
            total_greeks: Total aggregated Greeks
        
        Returns:
            CorrelationRiskReport with full analysis
        """
        import hashlib
        
        # Validate inputs
        if not positions:
            self.logger.warning("No positions provided for correlation risk report")
            positions = []
        
        if not position_greeks:
            self.logger.warning("No position Greeks provided, using empty dict")
            position_greeks = {}
        
        self.logger.info(
            f"Generating correlation risk report: portfolio_id={portfolio_id}, "
            f"positions={len(positions)}, position_greeks={len(position_greeks)}"
        )
        
        # Compute adjusted Greeks
        adjusted = self.compute_correlation_adjusted_greeks(
            positions=positions,
            position_greeks=position_greeks,
            total_greeks=total_greeks
        )
        self.logger.info(f"Correlation adjusted Greeks computed: adjusted_vega={adjusted.adjusted_greeks.vega}")
        
        # Diversification ratio
        div_ratio = self.compute_diversification_ratio(
            raw_greeks=total_greeks,
            adjusted_greeks=adjusted.adjusted_greeks
        )
        self.logger.info(f"Diversification ratio: {div_ratio}")
        
        # Find highly correlated pairs and diversification opportunities
        pairs = self.get_pairs_from_portfolio(positions)
        highly_correlated = []
        diversification_opps = []
        
        for i, pair1 in enumerate(pairs):
            for j, pair2 in enumerate(pairs):
                if i < j:
                    corr = self.correlation_matrix.get_correlation(pair1, pair2)
                    if abs(corr) >= 0.7:
                        highly_correlated.append({
                            "pair1": pair1,
                            "pair2": pair2,
                            "correlation": round(corr, 2)
                        })
                    elif abs(corr) <= 0.3:
                        diversification_opps.append({
                            "pair1": pair1,
                            "pair2": pair2,
                            "correlation": round(corr, 2)
                        })
        
        # Run predefined stress tests
        stress_tests = []
        for scenario_key, scenario_data in CRISIS_CORRELATION_SCENARIOS.items():
            scenario = CorrelationStressTest(
                scenario_id=scenario_key,
                name=scenario_data["name"],
                description=scenario_data["description"],
                correlation_multipliers=scenario_data["multipliers"]
            )
            result = self.run_stress_test(
                raw_greeks=total_greeks,
                positions=positions,
                position_greeks=position_greeks,
                scenario=scenario
            )
            stress_tests.append(result)
        
        # Correlation attribution factors
        correlation_attribution = []
        
        if div_ratio < 0.95:  # Significant diversification benefit
            benefit_pct = float((1.0 - div_ratio) * 100)
            correlation_attribution.append(RiskAttributionFactor(
                factor_type="correlation_effect",
                source="cross_asset_correlation",
                percentage=round(benefit_pct, 1),
                description=f"Correlations provide diversification benefit, reducing risk by {benefit_pct:.1f}%",
                evidence={"diversification_ratio": round(float(div_ratio), 3)}
            ))
        elif div_ratio > 1.05:  # Concentration risk
            risk_pct = float((div_ratio - 1.0) * 100)
            correlation_attribution.append(RiskAttributionFactor(
                factor_type="correlation_effect",
                source="cross_asset_correlation",
                percentage=round(risk_pct, 1),
                description=f"Correlations increase concentration risk by {risk_pct:.1f}%",
                evidence={"diversification_ratio": round(float(div_ratio), 3)}
            ))
        
        # Add pair-specific attributions for highly correlated pairs
        for hc in highly_correlated[:3]:  # Top 3
            correlation_attribution.append(RiskAttributionFactor(
                factor_type="correlation_effect",
                source=f"highly_correlated_pair_{hc['pair1']}_{hc['pair2']}",
                percentage=round(float(abs(hc['correlation']) * 20), 1),  # Scale correlation to percentage
                description=f"{hc['pair1']} and {hc['pair2']} have high correlation ({hc['correlation']}), contributing to concentration risk",
                evidence={"correlation": float(hc['correlation'])}
            ))
        
        # Generate report ID
        report_id = f"corr-report-{hashlib.sha256(f'{portfolio_id}{datetime.now().isoformat()}'.encode()).hexdigest()[:16]}"
        
        return CorrelationRiskReport(
            report_id=report_id,
            timestamp=datetime.now(),
            portfolio_id=portfolio_id,
            correlation_matrix_id=self.correlation_matrix.matrix_id,
            raw_total_greeks=total_greeks,
            adjusted_total_greeks=adjusted.adjusted_greeks,
            diversification_ratio=round(div_ratio, 3),
            highly_correlated_pairs=highly_correlated,
            diversification_opportunities=diversification_opps,
            stress_tests=stress_tests,
            correlation_attribution=correlation_attribution
        )
    
    def apply_news_event_correlation_adjustment(
        self,
        event_type: str,
        affected_pairs: List[str],
        sentiment: str = "neutral",
        sentiment_score: float = 0.0,
        headline: Optional[str] = None,
        url: Optional[str] = None
    ) -> "CorrelationMatrix":
        """
        Adjust correlation matrix based on a news event.
        
        When news events occur, correlations between affected pairs shift.
        The shift magnitude depends on:
        - Event type (CENTRAL_BANK has different impact than MACRO)
        - Affected pairs (pairs mentioned in news)
        - Sentiment (negative sentiment during crises increases correlations)
        
        Args:
            event_type: Type of news event (CENTRAL_BANK, MACRO, etc.)
            affected_pairs: List of FX pairs affected by this event
            sentiment: Sentiment of the news (positive/negative/neutral)
            sentiment_score: Numerical sentiment score (-1 to 1)
            headline: News headline (for tracking what caused the change)
            url: URL to original news article (for traceability)
        
        Returns:
            New CorrelationMatrix with adjusted correlations
        """
        # Look up event-type specific multipliers
        event_config = EVENT_CORRELATION_ADJUSTMENTS.get(event_type.upper().replace("-", "_"))
        
        if event_config is None:
            self.logger.debug(f"No correlation adjustment for event type: {event_type}")
            return self.correlation_matrix
        
        multipliers = event_config["multipliers"]
        description = event_config["description"]
        
        self.logger.info(f"Applying {event_type} correlation adjustment: {description}")
        
        # Create new correlation matrix with adjustments
        new_correlations = dict(self.correlation_matrix.correlations)
        original_correlations = dict(self.correlation_matrix.correlations)
        
        # Calculate dynamic multiplier based on sentiment
        # In crisis (negative sentiment), correlations increase more
        base_multiplier = 1.0
        if sentiment == "negative":
            base_multiplier = 1.0 + abs(sentiment_score) * 0.3  # Up to 30% extra
        elif sentiment == "positive":
            base_multiplier = 1.0 - sentiment_score * 0.1  # Slight reduction for positive
        
        # Track pair changes for the news correlation impact record
        pair_changes = []
        
        # Apply multipliers
        for (pair1, pair2), multiplier in multipliers.items():
            if pair1 == "*" and pair2 == "*":
                # Apply default multiplier to all correlations involving affected pairs
                for key in list(new_correlations.keys()):
                    p1, p2 = key
                    # Check if either pair is in affected pairs
                    if p1 in affected_pairs or p2 in affected_pairs:
                        old_corr = new_correlations.get(key, 0.0)
                        effective_mult = multiplier * base_multiplier
                        new_corr = np.clip(old_corr * effective_mult, -1.0, 1.0)
                        new_correlations[key] = new_corr
                        
                        if abs(new_corr - old_corr) > 0.001:
                            pair_changes.append({
                                "pair": f"{p1}_{p2}",
                                "old_corr": round(old_corr, 3),
                                "new_corr": round(new_corr, 3),
                                "change": round(new_corr - old_corr, 3)
                            })
            else:
                # Apply to specific pair if one of them is in affected pairs
                if pair1 in affected_pairs or pair2 in affected_pairs:
                    old_corr_1 = new_correlations.get((pair1, pair2), 0.0)
                    old_corr_2 = new_correlations.get((pair2, pair1), 0.0)
                    old_corr = old_corr_1 if old_corr_1 != 0.0 else old_corr_2
                    
                    effective_mult = multiplier * base_multiplier
                    new_corr = np.clip(old_corr * effective_mult, -1.0, 1.0)
                    
                    if (pair1, pair2) in new_correlations:
                        new_correlations[(pair1, pair2)] = new_corr
                    if (pair2, pair1) in new_correlations:
                        new_correlations[(pair2, pair1)] = new_corr
                    
                    if abs(new_corr - old_corr) > 0.001:
                        pair_changes.append({
                            "pair": f"{pair1}_{pair2}",
                            "old_corr": round(old_corr, 3),
                            "new_corr": round(new_corr, 3),
                            "change": round(new_corr - old_corr, 3)
                        })
        
        # Create adjusted matrix
        adjusted_matrix = CorrelationMatrix(
            matrix_id=f"{self.correlation_matrix.matrix_id}-adjusted-{event_type.lower()}",
            pairs=self.correlation_matrix.pairs,
            correlations=new_correlations,
            source=f"news_adjustment_{event_type.lower()}"
        )
        
        # Record the news correlation impact for traceability
        news_impact = NewsCorrelationImpact(
            headline=headline or f"{event_type} event affecting {', '.join(affected_pairs)}",
            url=url,
            event_type=event_type,
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            affected_pairs=affected_pairs,
            reason=description,
            pair_changes=pair_changes,
            multiplier_applied=base_multiplier,
            timestamp=datetime.now()
        )
        self.news_correlation_history.append(news_impact)
        
        self.logger.info(
            f"Created adjusted correlation matrix: {adjusted_matrix.matrix_id} "
            f"for event {event_type}, pairs: {affected_pairs}"
        )
        
        return adjusted_matrix
    
    def get_adjusted_correlation_matrix_for_event(
        self,
        event_vector: "EventVector"
    ) -> "CorrelationMatrix":
        """
        Get a correlation matrix adjusted for a specific news event.
        
        Args:
            event_vector: EventVector from news ingestion containing
                         event_type, affected_pairs, sentiment, etc.
        
        Returns:
            CorrelationMatrix with event-adjusted correlations
        """
        event_type = event_vector.event_type or "UNKNOWN"
        affected_pairs = event_vector.affected_pairs or []
        sentiment = event_vector.sentiment or "neutral"
        sentiment_score = getattr(event_vector, 'sentiment_score', 0.0) or 0.0
        
        if not affected_pairs:
            self.logger.debug("No affected pairs, returning base correlation matrix")
            return self.correlation_matrix
        
        return self.apply_news_event_correlation_adjustment(
            event_type=event_type,
            affected_pairs=affected_pairs,
            sentiment=sentiment,
            sentiment_score=sentiment_score
        )
    
    def get_correlation_change_summary(
        self,
        original_matrix: CorrelationMatrix,
        adjusted_matrix: CorrelationMatrix
    ) -> Dict[str, Any]:
        """
        Summarize how correlations changed between two matrices.
        
        Args:
            original_matrix: Base correlation matrix
            adjusted_matrix: Adjusted correlation matrix
        
        Returns:
            Dictionary with change summary statistics
        """
        changes = []
        max_increase = 0.0
        max_decrease = 0.0
        
        for (pair1, pair2), new_corr in adjusted_matrix.correlations.items():
            old_corr = original_matrix.correlations.get((pair1, pair2), 1.0)
            if pair1 != pair2:  # Skip self-correlations
                delta = new_corr - old_corr
                if abs(delta) > 0.01:  # Only significant changes
                    changes.append({
                        "pair1": pair1,
                        "pair2": pair2,
                        "old_correlation": round(old_corr, 3),
                        "new_correlation": round(new_corr, 3),
                        "change": round(delta, 3)
                    })
                    if delta > max_increase:
                        max_increase = delta
                    if delta < max_decrease:
                        max_decrease = delta
        
        return {
            "total_changes": len(changes),
            "max_increase": round(max_increase, 3),
            "max_decrease": round(max_decrease, 3),
            "changes": sorted(changes, key=lambda x: abs(x["change"]), reverse=True)[:10]
        }
    
    def get_news_correlation_history(self) -> List[NewsCorrelationImpact]:
        """Get history of all news events that caused correlation changes."""
        return self.news_correlation_history
    
    def get_correlation_change_report(
        self,
        portfolio_id: str = "FX-PORTFOLIO-01"
    ) -> CorrelationChangeReport:
        """
        Generate a report showing all correlation changes caused by news events.
        
        This report provides full traceability:
        - Which news headlines caused correlation variations
        - Why correlations changed (based on event type rules)
        - Links to original articles (URLs)
        - Factor percentages for each change
        
        Args:
            portfolio_id: Portfolio this report is for
        
        Returns:
            CorrelationChangeReport with full history
        """
        import hashlib
        
        # Calculate cumulative impact
        total_pairs_affected = set()
        for impact in self.news_correlation_history:
            total_pairs_affected.update(impact.affected_pairs)
        
        cumulative_impact = {
            "total_news_events": len(self.news_correlation_history),
            "total_pairs_affected": list(total_pairs_affected),
            "unique_event_types": list(set(i.event_type for i in self.news_correlation_history))
        }
        
        # Generate report ID
        report_id = f"corr-change-{hashlib.sha256(f'{portfolio_id}{datetime.now().isoformat()}'.encode()).hexdigest()[:16]}"
        
        return CorrelationChangeReport(
            report_id=report_id,
            timestamp=datetime.now(),
            portfolio_id=portfolio_id,
            base_correlation_matrix_id=self.correlation_matrix.matrix_id,
            current_correlation_matrix_id=f"{self.correlation_matrix.matrix_id}-current",
            news_correlation_impacts=self.news_correlation_history,
            total_changes=len(self.news_correlation_history),
            cumulative_impact=cumulative_impact
        )
    
    def get_available_scenarios(self) -> List[Dict[str, str]]:
        """Get list of available correlation stress scenarios."""
        return [
            {"id": key, "name": data["name"], "description": data["description"]}
            for key, data in CRISIS_CORRELATION_SCENARIOS.items()
        ]


# Singleton instance
_correlation_service: Optional[CorrelationService] = None


def get_correlation_service() -> CorrelationService:
    """Get the global correlation service instance."""
    global _correlation_service
    if _correlation_service is None:
        _correlation_service = CorrelationService()
    return _correlation_service
