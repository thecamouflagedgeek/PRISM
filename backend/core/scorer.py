"""
PRISM — scorer.py (Production Inference)
==========================================
This is the inference-time entry point called by the FastAPI /assess endpoint.

It replaces the old hardcoded WoE table approach with proper model artifacts
trained in Stages 3–7. All coefficients, WoE values, and scaling parameters
are derived from the fitted model — not manually set.

Call flow:
    raw features (bank, salary, utility)
        → Stage 4: WoE transform   (binning_models.pkl)
        → Stage 5: LR inference    (lr_model.pkl)
        → Stage 6: PD              (sigmoid of log_odds)
        → Stage 7: Credit score    (PDO scaling)
        → Stage 8: SHAP reasons    (β_i × WoE_i contribution)
        → Stage 9: Confidence      (coverage × quality × fraud × certainty)
        → Final output dict

Usage:
    from scorer import compute_risk_score

    result = compute_risk_score(
        bank    = {"credit_debit_ratio": 1.5, "cashflow_cv": 0.3, "min_balance": 40000},
        salary  = {"net_to_gross_ratio": 0.82},
        utility = {"payment_discipline_flag": True},
        fraud_confidence = 0.95
    )
"""

import numpy as np
import joblib
import os
from typing import Optional, Dict

# ── Import PRISM pipeline stages ──────────────────────────────────────────────
from scoring.woe import woe_for_single_record
from scoring.score_scaling      import log_odds_to_score, FACTOR, OFFSET, FEATURES
from explain.explainability    import reason_codes_for_borrower, adverse_action_notice
from scoring.confidence  import confidence_for_api_response

# ── Load trained artifacts (loaded once at module import time) ────────────────
_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "scoring", "artifacts")

_model          = joblib.load(os.path.join(_ARTIFACT_DIR, "lr_model.pkl"))
_binning_models = joblib.load(os.path.join(_ARTIFACT_DIR, "binning_models.pkl"))

# Background WoE means for SHAP (from training set)
_woe_data    = joblib.load(os.path.join(_ARTIFACT_DIR, "woe_datasets.pkl"))
_mean_woe    = _woe_data["X_train_woe"].values.mean(axis=0)

print("[scorer.py] Artifacts loaded successfully.")

# ──────────────────────────────────────────────────────────────────────────────


def _flatten_to_feature_dict(
    bank    : Optional[dict],
    salary  : Optional[dict],
    utility : Optional[dict]
) -> dict:
    """
    Map the three document dicts into the flat feature dict PRISM expects.
    Missing values pass as None → WoE transform uses 0.0 (neutral).
    """
    return {
        "credit_debit_ratio" : bank.get("credit_debit_ratio") if bank else None,
        "cashflow_cv"        : bank.get("cashflow_cv")        if bank else None,
        "net_to_gross_ratio" : salary.get("net_to_gross_ratio") if salary else None,
        "utility_stability"  : (
            float(utility.get("payment_discipline_flag", 0))
            if utility else None
        ),
        "min_balance"        : bank.get("min_balance")        if bank else None,
    }


def compute_risk_score(
    bank             : Optional[dict] = None,
    salary           : Optional[dict] = None,
    utility          : Optional[dict] = None,
    fraud_confidence : float = 1.0
) -> Dict:
    """
    Main inference function for PRISM.

    Parameters
    ----------
    bank             : parsed bank statement fields (from Stage 1 extractor)
    salary           : parsed salary slip fields
    utility          : parsed utility bill fields
    fraud_confidence : fraud module output, ∈ [0, 1] (default 1.0 if not run)

    Returns
    -------
    Full risk assessment dict compatible with the FastAPI response schema.
    """

    # ── Stage 4: WoE Transformation ───────────────────────────────────────────
    feature_dict = _flatten_to_feature_dict(bank, salary, utility)
    X_woe        = woe_for_single_record(feature_dict, _binning_models)
    # X_woe shape: (1, n_features)

    # ── Stage 5: LR Inference ─────────────────────────────────────────────────
    log_odds = _model.decision_function(X_woe)[0]

    # ── Stage 6: Probability of Default ───────────────────────────────────────
    pd_value = float(_model.predict_proba(X_woe)[0][1])
    pd_value = float(np.clip(pd_value, 0.0003, 0.9999))

    # ── Stage 7: Credit Score (PDO Scaling) ───────────────────────────────────
    score = int(log_odds_to_score(np.array([log_odds]))[0])

    # Risk tier (PD-based)
    if pd_value < 0.20:
        risk_tier = "Low Risk"
    elif pd_value < 0.40:
        risk_tier = "Medium Risk"
    elif pd_value < 0.70:
        risk_tier = "High Risk"
    else:
        risk_tier = "Very High Risk"

    # ── Stage 8: SHAP Reason Codes ────────────────────────────────────────────
    coefs      = _model.coef_[0]
    shap_row   = coefs * (X_woe[0] - _mean_woe)         # exact LR SHAP
    reason_codes = reason_codes_for_borrower(shap_row)
    notice       = adverse_action_notice(reason_codes)

    # ── Stage 9: Confidence ───────────────────────────────────────────────────
    confidence = confidence_for_api_response(
        bank    = bank,
        salary  = salary,
        utility = utility,
        pd_value= pd_value,
        fraud_confidence = fraud_confidence
    )

    # ── Final Response ────────────────────────────────────────────────────────
    return {
        "risk_score"            : score,
        "probability_of_default": round(pd_value, 4),
        "risk_tier"             : risk_tier,
        "log_odds"              : round(float(log_odds), 4),

        "confidence"            : confidence,

        "reason_codes"          : [
            {
                "factor"    : rc["label"],
                "shap_value": rc["shap_value"],
                "impact"    : rc["direction"],
            }
            for rc in reason_codes
        ],

        "adverse_action_notice" : notice,

        "model_metadata"        : {
            "model_type"   : "WoE_Logistic_Scorecard",
            "pdo"          : 50,
            "base_score"   : 600,
            "base_odds"    : "1:20",
            "score_range"  : "300–900",
            "factor"       : round(FACTOR, 4),
            "offset"       : round(OFFSET, 4),
            "n_features"   : len(FEATURES),
            "features_used": FEATURES,
        },

        "feature_woe_values"    : {
            FEATURES[i]: round(float(X_woe[0][i]), 4)
            for i in range(len(FEATURES))
        },

        "feature_shap_values"   : {
            FEATURES[i]: round(float(shap_row[i]), 4)
            for i in range(len(FEATURES))
        },
    }


# ── STANDALONE TEST ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    # Test case 1: Low-risk borrower
    result = compute_risk_score(
        bank = {
            "credit_debit_ratio": 1.8,
            "cashflow_cv"       : 0.22,
            "min_balance"       : 55000
        },
        salary = {
            "net_to_gross_ratio": 0.85
        },
        utility = {
            "payment_discipline_flag": True
        },
        fraud_confidence = 0.95
    )

    print("Test Case 1 — Low Risk Borrower")
    print(json.dumps(result, indent=2))

    # Test case 2: High-risk borrower
    result2 = compute_risk_score(
        bank = {
            "credit_debit_ratio": 0.7,
            "cashflow_cv"       : 0.80,
            "min_balance"       : 8000
        },
        salary = {
            "net_to_gross_ratio": 0.55
        },
        utility = {
            "payment_discipline_flag": False
        },
        fraud_confidence = 0.60
    )

    print("\nTest Case 2 — High Risk Borrower")
    print(json.dumps(result2, indent=2))