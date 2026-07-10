"""
PRISM Credit Scoring Engine — Production Version
All mathematical corrections applied. Public API unchanged.
"""
from __future__ import annotations
import os
import numpy as np
import joblib
import pandas as pd
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────
_BASE      = os.path.dirname(__file__)
_ARTIFACTS = os.path.join(_BASE, "artifacts")

# Lazy-load to allow import without artifacts (testing)
_model          = None
_binning_models = None

def _load_artifacts():
    global _model, _binning_models
    if _model is None:
        _model          = joblib.load(os.path.join(_ARTIFACTS, "lr_model.pkl"))
        _binning_models = joblib.load(os.path.join(_ARTIFACTS, "binning.pkl"))

# ── Feature order (must match training) ───────────────────────
_FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]

# ── PDO / Scaling constants ────────────────────────────────────
#
#  Factor = PDO / ln(2)
#  Offset = BASE_SCORE - Factor × ln(BASE_ODDS)
#
#  Score  = Offset - Factor × log_odds
#         = Offset + Factor × ln(Odds_good)      [Odds_good = (1-PD)/PD]
#
#  BASE_ODDS is the good:bad odds (non-default:default) at which we
#  want the BASE_SCORE anchor point.  19:1 is the Basel convention.
#
_PDO        = 50
_BASE_SCORE = 600
_BASE_ODDS  = 19                          # good:bad (non-default:default)
_FACTOR     = _PDO / np.log(2)            # ≈ 72.13
_OFFSET     = _BASE_SCORE - _FACTOR * np.log(_BASE_ODDS)

# Optional calibration wrapper (set by apply_platt_calibration())
_platt_calibrator = None


# ─────────────────────────────────────────────────────────────
# SAFE HELPERS
# ─────────────────────────────────────────────────────────────

def _safe(d: Optional[dict], key: str):
    if not d or not isinstance(d, dict):
        return None
    val = d.get(key)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return val


# ─────────────────────────────────────────────────────────────
# FEATURE MAPPING
# ─────────────────────────────────────────────────────────────

def _map_features(bank, salary, utility) -> dict:
    return {
        "credit_debit_ratio": _safe(bank,    "credit_debit_ratio"),
        "cashflow_cv":         _safe(bank,    "cashflow_cv"),
        "net_to_gross_ratio":  _safe(salary,  "net_to_gross_ratio"),
        "utility_stability":   _safe(utility, "utility_stability"),  # NOT payment_discipline_flag
        "min_balance":         _safe(bank,    "min_balance_l3m"),
    }


# ─────────────────────────────────────────────────────────────
# WoE TRANSFORM
# Returns a named DataFrame (required by sklearn to avoid warnings
# and to enforce column order by name, not position).
# Missing values → passed as np.nan so OptimalBinning uses its
# trained Missing-bin WoE (not hardcoded 0.0).
# ─────────────────────────────────────────────────────────────

def _woe_transform(feature_dict: dict) -> pd.DataFrame:
    row = {}
    for col in _FEATURES:
        val    = feature_dict.get(col)
        binner = _binning_models[col]
        inp    = np.nan if val is None else val
        woe    = float(binner.transform([inp], metric="woe")[0])
        row[col] = woe
    return pd.DataFrame([row], columns=_FEATURES)


# ─────────────────────────────────────────────────────────────
# SCORE CONVERSION
# Score = OFFSET - FACTOR × log_odds
# where log_odds = decision_function() = ln(PD/(1-PD))
# Higher PD → more positive log_odds → lower score  ✓
# ─────────────────────────────────────────────────────────────

def _to_score(log_odds: float) -> int:
    return int(np.clip(_OFFSET - _FACTOR * log_odds, 300, 900))


# ─────────────────────────────────────────────────────────────
# RISK TIER
# Uses calibrated thresholds if provided; else fixed defaults.
# ─────────────────────────────────────────────────────────────

_tier_thresholds = None   # set externally via set_tier_thresholds()

def set_tier_thresholds(thresholds) -> None:
    """Inject calibrated TierThresholds from risk_tier_validator."""
    global _tier_thresholds
    _tier_thresholds = thresholds

def _risk_tier(pd_value: float) -> str:
    if _tier_thresholds is not None:
        from validation.risk_tier_validator import assign_risk_tier
        return assign_risk_tier(pd_value, _tier_thresholds)
    # Original fixed thresholds (unchanged for backward-compat)
    if pd_value < 0.20:   return "Low Risk"
    elif pd_value < 0.40: return "Medium Risk"
    elif pd_value < 0.70: return "High Risk"
    else:                 return "Very High Risk"


# ─────────────────────────────────────────────────────────────
# REASON CODES  (per-feature score contribution)
# contribution_j = -FACTOR × β_j × WoE_j   [in score points]
# Negative = hurts score.  Sorted by |contribution| desc.
# ─────────────────────────────────────────────────────────────

def _reason_codes(X_woe_df: pd.DataFrame) -> list:
    coefs     = _model.coef_[0]
    woe_vals  = X_woe_df.values[0]
    reasons   = []
    for i, col in enumerate(_FEATURES):
        score_contrib = -_FACTOR * coefs[i] * woe_vals[i]
        reasons.append({
            "factor":             col,
            "woe":                round(float(woe_vals[i]), 4),
            "coefficient":        round(float(coefs[i]), 4),
            "score_contribution": round(float(score_contrib), 2),
            "impact":             "positive" if score_contrib > 0 else "negative",
        })
    reasons.sort(key=lambda x: abs(x["score_contribution"]), reverse=True)
    return reasons[:4]


# ─────────────────────────────────────────────────────────────
# CONFIDENCE SCORE
# Weighted average (not multiplicative) to avoid single-zero collapse.
# ─────────────────────────────────────────────────────────────

def _confidence(feature_dict: dict, bank, salary, utility, pd_value: float) -> dict:
    doc_coverage = (
        0.6 * (bank    is not None) +
        0.2 * (salary  is not None) +
        0.2 * (utility is not None)
    )
    n_present    = sum(1 for f in _FEATURES if feature_dict.get(f) is not None)
    data_quality = n_present / len(_FEATURES)          # was hardcoded 1.0
    model_certainty = abs(pd_value - 0.5) * 2

    # Weighted average: doc 40%, quality 30%, certainty 30%
    score = 0.4 * doc_coverage + 0.3 * data_quality + 0.3 * model_certainty

    return {
        "confidence_pct": round(score * 100, 2),
        "band": (
            "High Confidence"     if score >= 0.75 else
            "Moderate Confidence" if score >= 0.50 else
            "Low Confidence"
        ),
        "components": {
            "document_coverage": round(doc_coverage,     3),
            "data_quality":      round(data_quality,     3),
            "model_certainty":   round(model_certainty,  3),
        },
    }


# ─────────────────────────────────────────────────────────────
# CALIBRATION WRAPPER (optional, non-breaking)
# ─────────────────────────────────────────────────────────────

def apply_platt_calibration(calibrator) -> None:
    """
    Inject a fitted CalibratedClassifierCV wrapper.
    If set, PD is sourced from the calibrator instead of the raw model.
    Score formula and all downstream outputs remain unchanged.
    """
    global _platt_calibrator
    _platt_calibrator = calibrator


# ─────────────────────────────────────────────────────────────
# MAIN ENTRYPOINT  (public API — schema unchanged)
# ─────────────────────────────────────────────────────────────

def compute_risk_score(
    bank_features:    Optional[dict],
    salary_features:  Optional[dict],
    utility_features: Optional[dict],
) -> dict:

    _load_artifacts()

    feature_dict = _map_features(bank_features, salary_features, utility_features)
    X_woe        = _woe_transform(feature_dict)

    # Log-odds: always from the base logistic model (not calibrator)
    # so PDO scaling remains mathematically consistent.
    log_odds = float(_model.decision_function(X_woe)[0])

    # PD: from calibrator if available, else raw model
    if _platt_calibrator is not None:
        pd_value = float(np.clip(_platt_calibrator.predict_proba(X_woe)[0][1], 1e-6, 1-1e-6))
    else:
        pd_value = float(np.clip(_model.predict_proba(X_woe)[0][1], 1e-6, 1-1e-6))

    score = _to_score(log_odds)

    print("FEATURES")
    print(feature_dict)
    print()
    print("WOE")
    print(X_woe)
    print()
    print("LOG ODDS")
    print(log_odds)
    print()
    print("PD")
    print(pd_value)
    print()
    print("SCORE")
    print(score)
    return {
        "risk_score":             score,
        "probability_of_default": round(pd_value, 4),
        "risk_tier":              _risk_tier(pd_value),
        "log_odds":               round(log_odds, 4),
        "reason_codes":           _reason_codes(X_woe),
        "confidence":             _confidence(feature_dict, bank_features,
                                              salary_features, utility_features, pd_value),
        "model_metadata": {
            "model_type":  "WoE_Logistic_Scorecard",
            "pdo":         _PDO,
            "base_score":  _BASE_SCORE,
            "base_odds":   _BASE_ODDS,
            "factor":      round(_FACTOR, 4),
            "offset":      round(_OFFSET, 4),
            "score_range": "300–900",
        },
        "feature_woe_values": {
            col: round(float(X_woe[col].iloc[0]), 4)
            for col in _FEATURES
        },
    }