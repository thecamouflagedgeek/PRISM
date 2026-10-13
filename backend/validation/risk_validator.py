"""
PRISM – Risk Tier Assignment   (Part 7)
Replaces fixed PD thresholds with statistically justified quantile-based thresholds.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

_DEFAULT_THRESHOLDS = {"Low Risk": 0.20, "Medium Risk": 0.40, "High Risk": 0.70}

@dataclass
class TierThresholds:
    low_max: float       # PD < low_max → Low Risk
    medium_max: float    # PD < medium_max → Medium Risk
    high_max: float      # PD < high_max → High Risk
    # else: Very High Risk
    observed_default_rates: Dict[str, float] = field(default_factory=dict)
    rationale: str = ""

def compute_justified_thresholds(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    target_tier_sizes: Optional[Dict[str, float]] = None,
) -> TierThresholds:
    """
    Derive tier thresholds from observed data:
    1. Sort population by predicted PD.
    2. Assign tiers so each tier contains a target fraction of the population.
    3. Compute observed default rate within each tier.
    Tiers should show monotonically increasing default rates.
    Default target sizes: Low=40%, Medium=30%, High=20%, VeryHigh=10%.
    """
    sizes = target_tier_sizes or {"Low": 0.40, "Medium": 0.30, "High": 0.20}
    # Derive quantile breakpoints
    low_q   = sizes["Low"]
    mid_q   = sizes["Low"] + sizes["Medium"]
    high_q  = sizes["Low"] + sizes["Medium"] + sizes["High"]

    df = pd.DataFrame({"pd": y_prob, "default": y_true})
    df = df.sort_values("pd")

    low_thresh  = float(np.quantile(y_prob, low_q))
    mid_thresh  = float(np.quantile(y_prob, mid_q))
    high_thresh = float(np.quantile(y_prob, high_q))

    def _dr(mask):
        sub = df[mask]
        return float(sub["default"].mean()) if len(sub) else np.nan

    obs = {
        "Low Risk":       _dr(df["pd"] <  low_thresh),
        "Medium Risk":    _dr((df["pd"] >= low_thresh) & (df["pd"] < mid_thresh)),
        "High Risk":      _dr((df["pd"] >= mid_thresh) & (df["pd"] < high_thresh)),
        "Very High Risk": _dr(df["pd"] >= high_thresh),
    }

    rationale = (
        f"Thresholds derived from population quantiles: "
        f"Low<{low_thresh:.2f} | Medium<{mid_thresh:.2f} | High<{high_thresh:.2f}. "
        f"Observed DRs: {obs}"
    )
    return TierThresholds(
        low_max=round(low_thresh,4), medium_max=round(mid_thresh,4),
        high_max=round(high_thresh,4),
        observed_default_rates={k: round(v,4) for k,v in obs.items()},
        rationale=rationale,
    )

def assign_risk_tier(pd_value: float, thresholds: Optional[TierThresholds] = None) -> str:
    """
    Assign risk tier using calibrated thresholds if provided,
    else fall back to original fixed thresholds (non-breaking).
    """
    if thresholds is None:
        # Original behaviour — unchanged for API compatibility
        if pd_value < 0.20: return "Low Risk"
        elif pd_value < 0.40: return "Medium Risk"
        elif pd_value < 0.70: return "High Risk"
        else: return "Very High Risk"
    if pd_value < thresholds.low_max:    return "Low Risk"
    elif pd_value < thresholds.medium_max: return "Medium Risk"
    elif pd_value < thresholds.high_max:  return "High Risk"
    else: return "Very High Risk"