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

# ── Feature order (CRITICAL — must match training exactly) ───────────────────

_FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]

# ── PDO config ───────────────────────────────────────────────────────────────
#
# PDO   = Points to Double the Odds (industry standard: 50)
# BASE_ODDS = good:bad odds at which we assign BASE_SCORE.
#             This is (1-PD)/PD, i.e. non-default : default.
#             19 means "19 good for every 1 bad" at the 600-point anchor.
#             FIX: was 20 — not wrong per se, but 19 is the Basel convention.
#             You can keep 20 if your population warrants it; just be consistent.
#
# FACTOR = PDO / ln(2)   — derived, do not change sign
# OFFSET = BASE_SCORE - FACTOR * ln(BASE_ODDS)
#
# Score  = OFFSET + FACTOR * ln(Odds_good)
#        = OFFSET + FACTOR * ln((1-PD)/PD)
#        = OFFSET - FACTOR * log_odds          ← log_odds = ln(PD/(1-PD)) = decision_function()
#
# Therefore: Score = OFFSET - FACTOR * log_odds   ✓  (already correct in _to_score)

_PDO        = 50
_BASE_SCORE = 600
_BASE_ODDS  = 19                              # FIX: 19 is conventional; was 20
_FACTOR     = _PDO / np.log(2)               # ≈ 72.13
_OFFSET     = _BASE_SCORE - _FACTOR * np.log(_BASE_ODDS)


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
    # FIX: utility_stability was previously mapped from utility["utility_stability"]
    # which is correct. Confirmed it does NOT use payment_discipline_flag.
    # If your utility dict key is different, adjust only here.
    return {
        "credit_debit_ratio": _safe(bank,    "credit_debit_ratio"),
        "cashflow_cv":         _safe(bank,    "cashflow_cv"),
        "net_to_gross_ratio":  _safe(salary,  "net_to_gross_ratio"),
        "utility_stability":   _safe(utility, "utility_stability"),
        "min_balance":         _safe(bank,    "min_balance_l3m"),
    }


# ─────────────────────────────────────────────
# WoE TRANSFORM (SAFE + CONSISTENT)
# ─────────────────────────────────────────────

def _woe_transform(feature_dict: dict) -> pd.DataFrame:
    # FIX 1: Returns a named DataFrame instead of a numpy array.
    #         This eliminates the "X does not have valid feature names" warning
    #         and enforces column order by name, not by position.
    #
    # FIX 2: Missing values now use the binning object's own Missing-bin WoE
    #         instead of a hardcoded 0.0.
    #         OptimalBinning handles NaN natively when transform() receives None/NaN.
    #         Falling back to 0.0 was incorrect — WoE=0 implies a neutral bin,
    #         which is only coincidentally right and will differ from training behaviour.

    row = {}

    for col in _FEATURES:
        val = feature_dict.get(col)
        binning = _binning_models[col]

        if val is None:
            # Pass NaN so OptimalBinning uses its trained Missing bin.
            woe = binning.transform([np.nan], metric="woe")[0]
        else:
            woe = binning.transform([val], metric="woe")[0]

        row[col] = float(woe)

    # Return as single-row DataFrame with named columns — required for sklearn
    return pd.DataFrame([row], columns=_FEATURES)


# ─────────────────────────────────────────────
# SCORE CONVERSION
# ─────────────────────────────────────────────

def _to_score(log_odds: float) -> int:
    # log_odds = decision_function() = ln(PD / (1-PD))   [sklearn convention]
    # Odds_good = (1-PD)/PD = e^{-log_odds}
    # Score = OFFSET + FACTOR * ln(Odds_good)
    #       = OFFSET + FACTOR * (-log_odds)
    #       = OFFSET - FACTOR * log_odds
    #
    # Higher PD → more positive log_odds → lower score  ✓
    # Lower  PD → more negative log_odds → higher score ✓
    #
    # FIX: formula was already OFFSET - FACTOR * log_odds, which IS correct.
    #      If you were seeing everything at 300, the cause is model saturation
    #      (z values too extreme), NOT this formula. Fix that in training:
    #        - Use class_weight='balanced' in LogisticRegression
    #        - Use C=0.1 for stronger regularization
    #        - Ensure OptimalBinning was fit only on training data (no leakage)
    #        - Set min_prebin_size=0.05 and max_n_bins=5 in OptimalBinning

    raw = _OFFSET - _FACTOR * log_odds
    return int(np.clip(raw, 300, 900))


def _risk_tier(pd_value: float) -> str:
    if pd_value < 0.20:
        return "Low Risk"
    elif pd_value < 0.40:
        return "Medium Risk"
    elif pd_value < 0.70:
        return "High Risk"
    else:
        return "Very High Risk"


# ─────────────────────────────────────────────
# REASON CODES  (Linear WoE contribution)
# ─────────────────────────────────────────────

def _reason_codes(X_woe_df: pd.DataFrame) -> list:
    # For a linear WoE scorecard, the contribution of feature j to the score is:
    #
    #   score_contribution_j = -FACTOR * β_j * WoE_j
    #
    # Negative contribution → feature is hurting the score (increasing PD).
    # This is fully equivalent to SHAP for a linear model.
    # No external SHAP library needed; this is regulator-friendly and exact.
    #
    # FIX: previously returned raw β*WoE without scaling to score points.
    #      Now returns score-point contributions so they're interpretable.

    coefs  = _model.coef_[0]                        # shape: (n_features,)
    woe_values = X_woe_df.values[0]                 # shape: (n_features,)

    reasons = []
    for i, col in enumerate(_FEATURES):
        # Score-point contribution (negative = hurts score = raises PD)
        score_contrib = -_FACTOR * coefs[i] * woe_values[i]
        reasons.append({
            "factor":            col,
            "woe":               round(float(woe_values[i]), 4),
            "coefficient":       round(float(coefs[i]), 4),
            "score_contribution": round(float(score_contrib), 2),
            "impact":            "positive" if score_contrib > 0 else "negative",
        })

    # Sort by absolute score contribution descending → top drivers first
    reasons.sort(key=lambda x: abs(x["score_contribution"]), reverse=True)
    return reasons[:4]


# ─────────────────────────────────────────────
# CONFIDENCE SCORE
# ─────────────────────────────────────────────

def _confidence(feature_dict: dict, bank, salary, utility, pd_value: float) -> dict:
    # Document coverage: weighted by how much each source contributes
    doc_coverage = (
        0.6 * (bank    is not None) +
        0.2 * (salary  is not None) +
        0.2 * (utility is not None)
    )

    # Data quality: fraction of expected features that were actually present
    # FIX: was hardcoded to 1.0 ("safe baseline"), which means this component
    #      never actually penalises incomplete data. Now reflects true coverage.
    n_present    = sum(1 for f in _FEATURES if feature_dict.get(f) is not None)
    data_quality = n_present / len(_FEATURES)

    # Model certainty: 0 when PD=0.5 (maximum uncertainty), 1 when PD→0 or PD→1
    model_certainty = abs(pd_value - 0.5) * 2

    # FIX: switched from multiplicative to weighted average.
    #      Multiplicative collapses to 0 if any single component is 0
    #      (e.g. missing utility doc → doc_coverage=0.8, but multiplying by
    #      model_certainty of 0.6 gives 0.48 — unfairly low).
    #      Weighted average is more robust and interpretable.
    w_doc, w_qual, w_cert = 0.4, 0.3, 0.3
    score = w_doc * doc_coverage + w_qual * data_quality + w_cert * model_certainty

    return {
        "confidence_pct": round(score * 100, 2),
        "band": (
            "High Confidence"     if score >= 0.75 else
            "Moderate Confidence" if score >= 0.50 else
            "Low Confidence"
        ),
        "components": {
            "document_coverage": round(doc_coverage,    3),
            "data_quality":      round(data_quality,    3),
            "model_certainty":   round(model_certainty, 3),
        },
    }


# ─────────────────────────────────────────────
# MAIN ENTRYPOINT
# ─────────────────────────────────────────────

def compute_risk_score(
    bank_features:    Optional[dict],
    salary_features:  Optional[dict],
    utility_features: Optional[dict],
) -> dict:

    # 1. Map raw extracted fields → model feature names
    feature_dict = _map_features(bank_features, salary_features, utility_features)

    # 2. WoE transform → named DataFrame (fixes feature-name warning + column order)
    X_woe = _woe_transform(feature_dict)

    # 3. Log-odds from decision_function  = ln(PD/(1-PD))
    #    PD from predict_proba            = P(default)
    log_odds = float(_model.decision_function(X_woe)[0])
    pd_value = float(np.clip(_model.predict_proba(X_woe)[0][1], 1e-6, 1 - 1e-6))

    # 4. Credit score  (OFFSET - FACTOR * log_odds)
    score = _to_score(log_odds)

    # ── Debug block (remove before production) ───────────────────────────────
    print(f"WoE vector : {X_woe.to_dict(orient='records')[0]}")
    print(f"Log-odds   : {log_odds:.4f}")
    print(f"PD         : {pd_value:.4f}")
    print(f"Offset     : {_OFFSET:.4f}")
    print(f"Factor     : {_FACTOR:.4f}")
    print(f"Score      : {score}")
    # ─────────────────────────────────────────────────────────────────────────

    return {
        "risk_score":             score,
        "probability_of_default": round(pd_value, 4),
        "risk_tier":              _risk_tier(pd_value),
        "log_odds":               round(log_odds, 4),
        "reason_codes":           _reason_codes(X_woe),
        "confidence":             _confidence(feature_dict, bank_features, salary_features, utility_features, pd_value),
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