"""
PRISM — scoring/risk_scorer.py
================================
Single entry point for the LR scoring pipeline.
Called exclusively from route/assess.py as:

    from scoring.risk_scorer import compute_risk_score
    result = compute_risk_score(bank_features, salary_features, utility_features)

Accepts the feature dicts produced by:
    BankFeatureEngineer.build_features()
    SalaryFeatureEngineer.build_features()
    UtilityFeatureEngineer.build_features()

and maps them onto the 5 trained model features:
    credit_debit_ratio, cashflow_cv, net_to_gross_ratio,
    utility_stability, min_balance

Does NOT touch parsers, OCR, sessions, or any ingestion logic.
"""

import os
import numpy as np
import joblib
from typing import Optional, Dict

# ── Artifact paths ────────────────────────────────────────────────────────────
_BASE = os.path.dirname(__file__)   # backend/scoring/
_ARTIFACTS = os.path.join(_BASE, "artifacts")

# Loaded once at import time — not on every request
_model          = joblib.load(os.path.join(_ARTIFACTS, "lr_model.pkl"))
_binning_models = joblib.load(os.path.join(_ARTIFACTS, "binning_models.pkl"))
_woe_meta       = joblib.load(os.path.join(_ARTIFACTS, "woe_datasets.pkl"))
_mean_woe       = _woe_meta["X_train_woe"].values.mean(axis=0)  # for SHAP

# Feature order MUST match what the model was trained on
_FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]

# PDO scaling constants
_PDO        = 50
_BASE_SCORE = 600
_BASE_ODDS  = 1 / 20
_FACTOR     = _PDO / np.log(2)
_OFFSET     = _BASE_SCORE - _FACTOR * np.log(_BASE_ODDS)

_FEATURE_LABELS = {
    "credit_debit_ratio" : "Credit-to-Debit Ratio",
    "cashflow_cv"        : "Cashflow Stability",
    "net_to_gross_ratio" : "Net-to-Gross Salary Ratio",
    "utility_stability"  : "Utility Payment Stability",
    "min_balance"        : "Minimum Account Balance",
}

# ─────────────────────────────────────────────────────────────────────────────


def _map_features(
    bank    : Optional[dict],
    salary  : Optional[dict],
    utility : Optional[dict],
) -> dict:
    """
    Maps the three feature engineer outputs into the flat dict of
    the 5 model features.

    Field names below match what BankFeatureEngineer / SalaryFeatureEngineer /
    UtilityFeatureEngineer actually return. If your engineers use different
    key names, adjust the .get() calls here — nowhere else needs to change.
    """
    return {
        # ── From BankFeatureEngineer ──────────────────────────────────────────
        "credit_debit_ratio" : _safe(bank,    "credit_debit_ratio"),
        "cashflow_cv"        : _safe(bank,    "cashflow_cv"),
        "min_balance"        : _safe(bank,    "min_balance"),

        # ── From SalaryFeatureEngineer ────────────────────────────────────────
        "net_to_gross_ratio" : _safe(salary,  "net_to_gross_ratio"),

        # ── From UtilityFeatureEngineer ───────────────────────────────────────
        # payment_discipline_flag is boolean → convert to float for binning
        "utility_stability"  : float(_safe(utility, "payment_discipline_flag") or 0.0),
    }


def _safe(d: Optional[dict], key: str):
    """Return d[key] if d is a non-None dict with that key, else None."""
    if not d or not isinstance(d, dict):
        return None
    val = d.get(key)
    return None if val is None or (isinstance(val, float) and np.isnan(val)) else val


def _woe_transform(feature_dict: dict) -> np.ndarray:
    """
    Transform raw feature values → WoE vector using trained binning models.
    Missing values map to 0.0 (neutral WoE — no log-odds contribution).
    Returns shape (1, n_features).
    """
    woe_vals = []
    for col in _FEATURES:
        val = feature_dict.get(col)
        if val is None:
            woe_vals.append(0.0)
        else:
            woe_vals.append(
                float(_binning_models[col].transform(
                    np.array([val]), metric="woe"
                )[0])
            )
    return np.array(woe_vals).reshape(1, -1)


def _to_score(log_odds: float) -> int:
    return int(np.clip(_OFFSET + _FACTOR * log_odds, 300, 900))


def _risk_tier(pd_value: float) -> str:
    if pd_value < 0.20:   return "Low Risk"
    elif pd_value < 0.40: return "Medium Risk"
    elif pd_value < 0.70: return "High Risk"
    else:                 return "Very High Risk"


def _shap_reason_codes(X_woe_row: np.ndarray) -> list:
    """
    Exact SHAP for LR: φ_i = β_i × (WoE_i − E[WoE_i])
    Sorted by absolute impact, top 4 returned.
    """
    coefs   = _model.coef_[0]
    phi     = coefs * (X_woe_row - _mean_woe)

    reasons = []
    for i, col in enumerate(_FEATURES):
        reasons.append({
            "factor"    : _FEATURE_LABELS[col],
            "shap_value": round(float(phi[i]), 4),
            "impact"    : "positive" if phi[i] > 0 else "negative",
        })

    reasons.sort(key=lambda r: abs(r["shap_value"]), reverse=True)
    return reasons[:4]


def _confidence(
    bank    : Optional[dict],
    salary  : Optional[dict],
    utility : Optional[dict],
    pd_value: float,
) -> dict:
    """
    Multiplicative confidence:
        C = doc_coverage × data_quality × model_certainty
    (fraud_confidence excluded here — injected by fraud module if available)
    """
    doc_coverage = (
        0.60 * (bank    is not None) +
        0.20 * (salary  is not None) +
        0.20 * (utility is not None)
    )

    # Count non-None model features
    n_present = sum(
        1 for col in _FEATURES
        if _safe(bank or salary or utility, col) is not None
            or (col == "net_to_gross_ratio" and salary)
            or (col == "utility_stability"  and utility)
    )
    data_quality = n_present / len(_FEATURES)

    model_certainty = abs(pd_value - 0.5) * 2   # 0 at PD=0.5, 1 at PD=0 or 1

    score = doc_coverage * data_quality * model_certainty

    if score >= 0.80:   band = "High Confidence"
    elif score >= 0.50: band = "Moderate Confidence"
    elif score >= 0.20: band = "Low Confidence — Manual Review Recommended"
    else:               band = "Very Low Confidence — Do Not Automate Decision"

    return {
        "confidence_pct": round(score * 100, 2),
        "band"          : band,
        "components"    : {
            "document_coverage": round(doc_coverage,   3),
            "data_quality"     : round(data_quality,   3),
            "model_certainty"  : round(model_certainty,3),
        },
    }


# ── Public API ────────────────────────────────────────────────────────────────

def compute_risk_score(
    bank_features    : Optional[dict],
    salary_features  : Optional[dict],
    utility_features : Optional[dict],
) -> Dict:
    """
    Main scoring function. Called from route/assess.py.

    Parameters
    ----------
    bank_features    : output of BankFeatureEngineer.build_features()
    salary_features  : output of SalaryFeatureEngineer.build_features()  or None
    utility_features : output of UtilityFeatureEngineer.build_features() or None

    Returns
    -------
    dict — full risk assessment result, spread into the /assess response
    """
    # 1. Map engineer outputs → model feature dict
    feature_dict = _map_features(bank_features, salary_features, utility_features)

    # 2. WoE transform
    X_woe    = _woe_transform(feature_dict)

    # 3. LR inference
    log_odds = float(_model.decision_function(X_woe)[0])
    pd_value = float(np.clip(_model.predict_proba(X_woe)[0][1], 0.0003, 0.9999))

    # 4. Credit score (PDO scaling)
    score    = _to_score(log_odds)

    # 5. Reason codes (exact SHAP)
    reason_codes = _shap_reason_codes(X_woe[0])

    # 6. Confidence
    confidence = _confidence(bank_features, salary_features, utility_features, pd_value)

    return {
        "risk_score"            : score,
        "probability_of_default": round(pd_value, 4),
        "risk_tier"             : _risk_tier(pd_value),
        "log_odds"              : round(log_odds, 4),
        "confidence"            : confidence,
        "reason_codes"          : reason_codes,
        "model_metadata"        : {
            "model_type" : "WoE_Logistic_Scorecard",
            "pdo"        : _PDO,
            "base_score" : _BASE_SCORE,
            "base_odds"  : "1:20",
            "score_range": "300–900",
        },
        "feature_woe_values"    : {
            _FEATURES[i]: round(float(X_woe[0][i]), 4)
            for i in range(len(_FEATURES))
        },
    }