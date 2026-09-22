"""
PRISM Credit Scoring Engine
============================

Loads the trained scorecard artifacts (logistic-regression model +
WoE binning) and converts borrower financial features into:

    1. WoE-transformed feature values
    2. Log-odds
    3. Probability of Default (PD)
    4. Credit score (300-900, PDO scorecard scaling)
    5. Risk tier
    6. Reason codes / scorecard-SHAP explanations
    7. Confidence level
    8. Document-coverage based score capping

Role in the wider pipeline
---------------------------
`services/assessment_service.py::assess_borrower()` is now the single
integrated entry point for a full PRISM assessment (credit risk +
fraud risk). It orchestrates `DocumentPipeline`, `process_bank_doc()`,
the fraud engine, etc.

This module is the **credit-risk scoring engine** that
`assess_borrower()` calls into for the WoE + Logistic Regression
scorecard piece of that assessment. It has no knowledge of fraud
signals, document parsing, or raw transactions - it only turns
already-extracted bank/salary/utility features into a score. Any new
logic that depends on `transactions`, raw documents, or fraud rules
belongs in `assess_borrower()` / `fraud/fraud_engine.py`, not here.

Public functions
-----------------
    score_borrower(bank, salary, utility)              -> dict
    risk_score(bank, salary, utility)                    -> dict  (alias)
    simulate_whatif(bank, salary, utility, overrides)    -> dict
    apply_platt_calibration(calibrator)                  -> None
    set_tier_thresholds(thresholds)                      -> None

Important:
- Feature names here must match the trained scorecard.
- Missing values are passed to the trained Missing-WoE bin (np.nan),
  never hardcoded to 0.0.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

# ============================================================
# PATHS
# ============================================================

_BASE = os.path.dirname(os.path.abspath(__file__))
_ARTIFACTS = os.path.join(_BASE, "artifacts")
_MODEL_PATH = os.path.join(_ARTIFACTS, "lr_model.pkl")
_BINNING_PATH = os.path.join(_ARTIFACTS, "binning.pkl")

# Lazy-loaded so this module can be imported (e.g. by tests, or by
# assess_borrower() at collection time) without the artifacts being
# present on disk. Anything that actually scores a borrower calls
# _load_artifacts() first, which fails loudly if they're missing.
_model = None
_binning_models = None


def _load_artifacts() -> None:
    global _model, _binning_models
    if _model is not None and _binning_models is not None:
        return

    if not os.path.exists(_MODEL_PATH):
        raise FileNotFoundError(f"Logistic regression model not found: {_MODEL_PATH}")
    if not os.path.exists(_BINNING_PATH):
        raise FileNotFoundError(f"Binning model not found: {_BINNING_PATH}")

    _model = joblib.load(_MODEL_PATH)
    _binning_models = joblib.load(_BINNING_PATH)


# ============================================================
# FEATURE CONFIGURATION (order must match training)
# ============================================================

_FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]

_FEATURE_LABELS = {
    "credit_debit_ratio": "Credit-Debit Ratio",
    "cashflow_cv": "Cashflow Volatility",
    "net_to_gross_ratio": "Income Stability",
    "utility_stability": "Utility Payment Discipline",
    "min_balance": "Average Balance",
}

# ============================================================
# SCORECARD / PDO SCALING CONSTANTS
# ============================================================
#
#   Factor = PDO / ln(2)
#   Offset = BASE_SCORE - Factor * ln(BASE_ODDS)
#   Score  = Offset - Factor * log_odds
#
# BASE_ODDS is the good:bad (non-default:default) odds at which the
# BASE_SCORE anchor point sits.
#
# *** BASE_ODDS MUST STAY 20 ***
# The trained lr_model.pkl / binning.pkl artifacts under
# backend/scoring/artifacts were calibrated against Base Odds = 20.
# This constant does not retrain the model - changing it silently
# shifts every score/PD mapping produced from those artifacts.
# (One branch of this file's merge history used 19, framed as a
# "Basel convention" anchor. That does NOT match how these specific
# artifacts were built and must not be reintroduced without a
# corresponding retrain + revalidation of the scorecard.)
_PDO = 50
_BASE_SCORE = 600
_BASE_ODDS = 20
_FACTOR = _PDO / np.log(2)
_OFFSET = _BASE_SCORE - _FACTOR * np.log(_BASE_ODDS)

# Optional calibration wrapper (set via apply_platt_calibration()).
# When present, PD is sourced from the calibrator; log-odds/score
# always come from the base model so PDO scaling stays consistent.
_platt_calibrator = None

# Optional calibrated tier thresholds (set via set_tier_thresholds()).
_tier_thresholds = None


def apply_platt_calibration(calibrator) -> None:
    """Inject a fitted CalibratedClassifierCV wrapper. PD only - score/log-odds
    always come from the base model so PDO scaling remains mathematically
    consistent."""
    global _platt_calibrator
    _platt_calibrator = calibrator


def set_tier_thresholds(thresholds) -> None:
    """Inject calibrated TierThresholds from validation.risk_tier_validator."""
    global _tier_thresholds
    _tier_thresholds = thresholds


# ============================================================
# SAFE VALUE EXTRACTION
# ============================================================

def _safe(data: Optional[Dict[str, Any]], key: str) -> Optional[float]:
    """
    Safely extract a numeric value from a feature dict.
    Returns None if the dict is missing, the key is absent, the value
    is None, or the value can't be coerced to a finite float.
    """
    if not data:
        return None
    value = data.get(key)
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(value):
        return None
    return value


# ============================================================
# FEATURE MAPPING
# ============================================================

def _build_feature_dict(
    bank: Optional[Dict[str, Any]] = None,
    salary: Optional[Dict[str, Any]] = None,
    utility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[float]]:
    """Map the PRISM input sections onto the five trained scorecard features."""
    return {
        "credit_debit_ratio": _safe(bank, "credit_debit_ratio"),
        "cashflow_cv": _safe(bank, "cashflow_cv"),
        "net_to_gross_ratio": _safe(salary, "net_to_gross_ratio"),
        # NOTE: this is utility_stability, not payment_discipline_flag.
        "utility_stability": _safe(utility, "utility_stability"),
        # source feature is min_balance_l3m; trained scorecard feature is min_balance
        "min_balance": _safe(bank, "min_balance_l3m"),
    }


# ============================================================
# WoE TRANSFORMATION
# ============================================================

def _apply_woe(feature_dict: Dict[str, Optional[float]]) -> pd.DataFrame:
    """
    Apply the trained WoE binning models to the borrower features.
    Missing values are passed as np.nan so the trained Missing bin's
    WoE is used, rather than a hardcoded 0.0. Returns a named
    DataFrame (required by sklearn to avoid warnings and to enforce
    column order by name, not position).
    """
    row: Dict[str, float] = {}
    for feature in _FEATURES:
        if feature not in _binning_models:
            raise KeyError(f"Missing binning model for feature: {feature}")

        value = feature_dict.get(feature)
        binner = _binning_models[feature]
        inp = np.nan if value is None else value
        woe = binner.transform([inp], metric="woe")[0]

        try:
            woe = float(woe)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid WoE value generated for feature '{feature}': {woe}")
        if not np.isfinite(woe):
            raise ValueError(f"Non-finite WoE value generated for feature '{feature}': {woe}")

        row[feature] = woe

    return pd.DataFrame([row], columns=_FEATURES)


# ============================================================
# LOG-ODDS / PD / SCORE
# ============================================================

def _compute_log_odds(woe_df: pd.DataFrame) -> float:
    """
    Log-odds = intercept + coef . WoE, computed explicitly (rather than
    via model.decision_function()) so it stays correct even if _model
    is ever wrapped by something that changes decision_function
    semantics, and so we can validate coefficient/feature alignment.
    """
    values = woe_df[_FEATURES].to_numpy(dtype=float).reshape(-1)
    coefficients = np.asarray(_model.coef_[0], dtype=float)
    intercept = float(_model.intercept_[0])

    if len(coefficients) != len(_FEATURES):
        raise ValueError(
            "Model coefficient count does not match the configured feature "
            f"count. Expected {len(_FEATURES)}, got {len(coefficients)}."
        )

    return float(intercept + np.dot(coefficients, values))


def _compute_pd(log_odds: float) -> float:
    """Numerically stable sigmoid: log-odds -> Probability of Default."""
    if log_odds >= 0:
        probability = 1.0 / (1.0 + np.exp(-log_odds))
    else:
        exp_value = np.exp(log_odds)
        probability = exp_value / (1.0 + exp_value)
    return float(np.clip(probability, 1e-6, 1 - 1e-6))


def _to_score(log_odds: float) -> int:
    """Score = Offset - Factor * log_odds. Higher PD -> lower score."""
    return int(np.clip(_OFFSET - _FACTOR * log_odds, 300, 900))


# ============================================================
# RISK TIER
# ============================================================

def _risk_tier(pd_value: float) -> str:
    """Uses calibrated thresholds if injected via set_tier_thresholds(), else
    fixed defaults."""
    if _tier_thresholds is not None:
        from validation.risk_tier_validator import assign_risk_tier
        return assign_risk_tier(pd_value, _tier_thresholds)

    if pd_value < 0.20:
        return "Low Risk"
    elif pd_value < 0.40:
        return "Medium Risk"
    elif pd_value < 0.70:
        return "High Risk"
    else:
        return "Very High Risk"


# ============================================================
# REASON CODES (per-feature score contribution)
# ============================================================

def _feature_contributions(woe_df: pd.DataFrame) -> Dict[str, float]:
    """
    contribution_i = -Factor * coef_i * WoE_i  (in score points).
    Positive -> improves score, negative -> hurts score. These are
    scorecard contributions, not true SHAP values.
    """
    woe_values = (
        woe_df[_FEATURES]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .iloc[0]
        .to_numpy(dtype=float)
    )
    coefficients = np.asarray(_model.coef_[0], dtype=float)
    contributions = -_FACTOR * coefficients * woe_values
    return {feature: float(c) for feature, c in zip(_FEATURES, contributions)}


def _reason_codes(contributions: Dict[str, float]) -> List[Dict[str, Any]]:
    """Human-readable, ranked reason codes (strongest impact first)."""
    reasons = []
    for feature, contribution in contributions.items():
        if contribution > 0.01:
            impact = "positive"
        elif contribution < -0.01:
            impact = "negative"
        else:
            impact = "neutral"
        reasons.append({
            "factor": feature,
            "label": _FEATURE_LABELS.get(feature, feature),
            "score_contribution": round(contribution, 2),
            "impact": impact,
        })
    reasons.sort(key=lambda r: abs(r["score_contribution"]), reverse=True)
    return [r for r in reasons if abs(r["score_contribution"]) > 0.01]


def _build_shap_explanations(contributions: Dict[str, float]) -> List[Dict[str, Any]]:
    """
    Feature-level scorecard explanations for the current borrower.

    NOTE: the exact field names/shape here (feature_name, shap_value,
    contribution_type, feature_rank, generated_reason,
    score_contribution) are relied on by
    database.crud.save_shap_explanations() - do not rename or remove
    fields here without updating that consumer too.
    """
    explanations = []
    for feature in _FEATURES:
        contribution = contributions[feature]
        label = _FEATURE_LABELS.get(feature, feature)

        if contribution > 0.01:
            contribution_type = "Positive"
            reason = f"{label} improved the borrower's credit score."
        elif contribution < -0.01:
            contribution_type = "Negative"
            reason = f"{label} increased repayment risk and reduced the credit score."
        else:
            contribution_type = "Neutral"
            reason = f"{label} had no significant impact on the credit score."

        explanations.append({
            "feature_name": label,
            "shap_value": round(contribution, 6),
            "contribution_type": contribution_type,
            "feature_rank": 0,
            "generated_reason": reason,
            "score_contribution": round(contribution, 6),
        })

    explanations.sort(key=lambda x: abs(x["score_contribution"]), reverse=True)
    for rank, explanation in enumerate(explanations, start=1):
        explanation["feature_rank"] = rank
    return explanations


# ============================================================
# CONFIDENCE
# ============================================================

def _confidence(
    feature_dict: Dict[str, Optional[float]],
    bank: Optional[Dict[str, Any]],
    salary: Optional[Dict[str, Any]],
    utility: Optional[Dict[str, Any]],
    pd_value: float,
) -> Dict[str, Any]:
    """
    Weighted average (not multiplicative, so one missing source doesn't
    collapse the whole confidence score to ~0):
        40% document coverage (which source docs are present at all)
        30% feature-level data quality (how many of the 5 mapped
            features actually came through)
        30% model certainty (distance of PD from 0.5)
    """
    doc_coverage = (
        0.6 * (bank is not None)
        + 0.2 * (salary is not None)
        + 0.2 * (utility is not None)
    )
    n_present = sum(1 for f in _FEATURES if feature_dict.get(f) is not None)
    data_quality = n_present / len(_FEATURES)
    model_certainty = abs(pd_value - 0.5) * 2

    score = 0.4 * doc_coverage + 0.3 * data_quality + 0.3 * model_certainty
    score = float(np.clip(score, 0.0, 1.0))

    if score >= 0.75:
        band = "High"
    elif score >= 0.50:
        band = "Moderate"
    else:
        band = "Low"

    return {
        "score": round(score, 4),
        "band": band,
        "components": {
            "document_coverage": round(doc_coverage, 3),
            "data_quality": round(data_quality, 3),
            "model_certainty": round(model_certainty, 3),
        },
    }


# ============================================================
# MAIN ENTRYPOINT
# ============================================================

def score_borrower(
    bank: Optional[Dict[str, Any]] = None,
    salary: Optional[Dict[str, Any]] = None,
    utility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run the WoE + Logistic Regression credit scorecard for a single
    borrower. This is the credit-risk half of assess_borrower() in
    services/assessment_service.py; it has no knowledge of fraud
    signals or raw transactions - those stay in fraud_engine.py and
    assess_borrower() itself.
    """
    _load_artifacts()

    feature_dict = _build_feature_dict(bank, salary, utility)
    woe_df = _apply_woe(feature_dict)

    # Log-odds always come from the base model (not the calibrator)
    # so PDO scaling stays mathematically consistent.
    log_odds = _compute_log_odds(woe_df)

    if _platt_calibrator is not None:
        pd_value = float(np.clip(_platt_calibrator.predict_proba(woe_df)[0][1], 1e-6, 1 - 1e-6))
    else:
        pd_value = _compute_pd(log_odds)

    score = _to_score(log_odds)
    contributions = _feature_contributions(woe_df)
    reason_codes = _reason_codes(contributions)
    shap_explanations = _build_shap_explanations(contributions)
    confidence = _confidence(feature_dict, bank, salary, utility, pd_value)

    # Cap the score when supporting documentation is thin - a high
    # score built mostly on Missing-value WoE bins isn't trustworthy
    # enough to certify as prime-tier.
    doc_coverage = confidence["components"]["document_coverage"]
    if doc_coverage < 0.4:
        max_allowed_score = 500
    elif doc_coverage < 0.7:
        max_allowed_score = 700
    else:
        max_allowed_score = 900

    score_before_cap = score
    score = min(score, max_allowed_score)
    score_capped = score_before_cap > max_allowed_score

    documents_needed = []
    if bank is None:
        documents_needed.append("bank_statement")
    if salary is None:
        documents_needed.append("salary_slip_or_itr")
    if utility is None:
        documents_needed.append("utility_bill")

    return {
        "risk_score": score,
        "probability_of_default": round(pd_value, 4),
        "risk_tier": _risk_tier(pd_value),
        "log_odds": round(log_odds, 4),
        "features": {f: (None if v is None else float(v)) for f, v in feature_dict.items()},
        "woe_features": {f: round(float(woe_df.iloc[0][f]), 4) for f in _FEATURES},
        "reason_codes": reason_codes,
        "shap_explanations": shap_explanations,
        "confidence": confidence,
        "documents_needed": documents_needed,
        "score_capped": score_capped,
        "model_metadata": {
            "model_type": "WoE_Logistic_Scorecard",
            "pdo": _PDO,
            "base_score": _BASE_SCORE,
            "base_odds": _BASE_ODDS,
            "factor": round(_FACTOR, 4),
            "offset": round(_OFFSET, 4),
            "score_range": "300-900",
        },
    }


def risk_score(
    bank: Optional[Dict[str, Any]] = None,
    salary: Optional[Dict[str, Any]] = None,
    utility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Backward-compatible alias for score_borrower()."""
    return score_borrower(bank=bank, salary=salary, utility=utility)


def simulate_whatif(
    bank: Optional[Dict[str, Any]],
    salary: Optional[Dict[str, Any]],
    utility: Optional[Dict[str, Any]],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Recompute score/PD with one or more mapped feature values
    overridden. Keys in `overrides` must match names in _FEATURES;
    unknown keys are ignored.
    """
    _load_artifacts()

    base_dict = _build_feature_dict(bank, salary, utility)
    sim_dict = {**base_dict, **{k: v for k, v in overrides.items() if k in _FEATURES}}

    woe_df = _apply_woe(sim_dict)
    log_odds = _compute_log_odds(woe_df)
    pd_value = _compute_pd(log_odds)
    score = _to_score(log_odds)

    return {
        "simulated_score": score,
        "simulated_pd": round(pd_value, 4),
        "simulated_risk_tier": _risk_tier(pd_value),
        "overrides_applied": {k: v for k, v in overrides.items() if k in _FEATURES},
        "ignored_keys": [k for k in overrides if k not in _FEATURES],
        "feature_woe_values": {f: round(float(woe_df.iloc[0][f]), 4) for f in _FEATURES},
    }


__all__ = [
    "score_borrower",
    "risk_score",
    "simulate_whatif",
    "apply_platt_calibration",
    "set_tier_thresholds",
]