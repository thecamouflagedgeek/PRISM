import os
import numpy as np
import joblib
import pandas as pd
from typing import Optional, Dict

# ── Paths ─────────────────────────────────────────────

_BASE = os.path.dirname(__file__)
_ARTIFACTS = os.path.join(_BASE, "artifacts")

_model = joblib.load(os.path.join(_ARTIFACTS, "lr_model.pkl"))
_binning_models = joblib.load(os.path.join(_ARTIFACTS, "binning.pkl"))

# ── Feature order (CRITICAL) ─────────────────────────

_FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]

# ── PDO config ───────────────────────────────────────

_PDO = 50
_BASE_SCORE = 600
_BASE_ODDS = 1 / 20
_FACTOR = _PDO / np.log(2)
_OFFSET = _BASE_SCORE - _FACTOR * np.log(_BASE_ODDS)


# ─────────────────────────────────────────────
# SAFE HELPERS
# ─────────────────────────────────────────────

def _safe(d: Optional[dict], key: str):
    if not d or not isinstance(d, dict):
        return None
    val = d.get(key)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return val


# ─────────────────────────────────────────────
# FEATURE MAPPING (STRICT & SAFE)
# ─────────────────────────────────────────────

def _map_features(bank, salary, utility):

    return {
        "credit_debit_ratio": _safe(bank, "credit_debit_ratio"),
        "cashflow_cv": _safe(bank, "cashflow_cv"),
        "min_balance": _safe(bank, "min_balance"),
        "net_to_gross_ratio": _safe(salary, "net_to_gross_ratio"),
        "utility_stability": float(_safe(utility, "payment_discipline_flag") or 0.0),
    }


# ─────────────────────────────────────────────
# WO E TRANSFORM (SAFE + CONSISTENT)
# ─────────────────────────────────────────────

def _woe_transform(feature_dict: dict):

    row = []

    for col in _FEATURES:
        val = feature_dict.get(col)

        if val is None:
            row.append(0.0)
            continue

        binning = _binning_models[col]
        woe = binning.transform([val], metric="woe")[0]
        row.append(float(woe))

    return np.array(row).reshape(1, -1)


# ─────────────────────────────────────────────
# SCORE CONVERSION
# ─────────────────────────────────────────────

def _to_score(log_odds: float):
    return int(np.clip(_OFFSET + _FACTOR * log_odds, 300, 900))


def _risk_tier(pd_value: float):
    if pd_value < 0.20:
        return "Low Risk"
    elif pd_value < 0.40:
        return "Medium Risk"
    elif pd_value < 0.70:
        return "High Risk"
    else:
        return "Very High Risk"


# ─────────────────────────────────────────────
# SHAP (CORRECTED FOR LINEAR MODEL)
# ─────────────────────────────────────────────

def _shap_reason_codes(X_woe_row: np.ndarray):

    coefs = _model.coef_[0]
    intercept = _model.intercept_[0]

    contributions = coefs * X_woe_row[0]

    reasons = []

    for i, col in enumerate(_FEATURES):
        reasons.append({
            "factor": col,
            "contribution": float(contributions[i]),
            "impact": "positive" if contributions[i] > 0 else "negative"
        })

    reasons.sort(key=lambda x: abs(x["contribution"]), reverse=True)

    return reasons[:4]


# ─────────────────────────────────────────────
# CONFIDENCE SCORE
# ─────────────────────────────────────────────

def _confidence(feature_dict,bank, salary, utility, pd_value):

    doc_coverage = (
        0.6 * (bank is not None) +
        0.2 * (salary is not None) +
        0.2 * (utility is not None)
    )

    n_present = sum(
        1 for f in _FEATURES
        if feature_dict.get(f) is not None
    )

    data_quality = 1.0  # safe baseline (avoid false penalties)
    model_certainty = abs(pd_value - 0.5) * 2

    score = doc_coverage * data_quality * model_certainty

    return {
        "confidence_pct": round(score * 100, 2),
        "band": (
            "High Confidence" if score >= 0.8 else
            "Moderate Confidence" if score >= 0.5 else
            "Low Confidence"
        ),
        "components": {
            "document_coverage": round(doc_coverage, 3),
            "data_quality": round(data_quality, 3),
            "model_certainty": round(model_certainty, 3),
        }
    }


# ─────────────────────────────────────────────
# MAIN ENTRYPOINT
# ─────────────────────────────────────────────

def compute_risk_score(bank_features, salary_features, utility_features):

    feature_dict = _map_features(bank_features, salary_features, utility_features)

    X_woe = _woe_transform(feature_dict)

    log_odds = float(_model.decision_function(X_woe)[0])
    pd_value = float(np.clip(_model.predict_proba(X_woe)[0][1], 1e-6, 1 - 1e-6))

    score = _to_score(log_odds)

    return {
        "risk_score": score,
        "probability_of_default": round(pd_value, 4),
        "risk_tier": _risk_tier(pd_value),
        "log_odds": round(log_odds, 4),
        "reason_codes": _shap_reason_codes(X_woe),
        "confidence": _confidence(feature_dict,bank_features, salary_features, utility_features, pd_value),
        "model_metadata": {
            "model_type": "WoE_Logistic_Scorecard",
            "pdo": _PDO,
            "base_score": _BASE_SCORE,
            "score_range": "300–900"
        },
        "feature_woe_values": {
            _FEATURES[i]: round(float(X_woe[0][i]), 4)
            for i in range(len(_FEATURES))
        }
    }