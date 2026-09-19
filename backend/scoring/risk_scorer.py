
"""
PRISM - Risk Scorer

Loads the trained scorecard artifacts and converts borrower financial
features into:

    1. WoE-transformed feature values
    2. Log-odds
    3. Probability of Default (PD)
    4. Credit score
    5. Risk tier
    6. Scorecard feature contributions
    7. Confidence level

Important:
- The model and binning artifacts are loaded from backend/scoring/artifacts.
- Feature names here must match the trained scorecard.
- Missing values are passed to the trained Missing WoE bin.
"""

import os
from typing import Any, Dict, Optional

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


# ============================================================
# LOAD MODEL ARTIFACTS
# ============================================================

if not os.path.exists(_MODEL_PATH):
    raise FileNotFoundError(
        f"Logistic regression model not found: {_MODEL_PATH}"
    )

if not os.path.exists(_BINNING_PATH):
    raise FileNotFoundError(
        f"Binning model not found: {_BINNING_PATH}"
    )


_model = joblib.load(_MODEL_PATH)
_binning_models = joblib.load(_BINNING_PATH)


# ============================================================
# FEATURE CONFIGURATION
# ============================================================

_FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]


# ============================================================
# SCORECARD CONFIGURATION
# ============================================================

# Points to Double the Odds
#
# Existing scorecard artifacts were built using:
#     PDO = 50
#     Base Score = 600
#     Base Odds = 20
#
# Therefore this must remain 20 here.
_PDO = 50
_BASE_SCORE = 600
_BASE_ODDS = 20


_FACTOR = _PDO / np.log(2)
_OFFSET = _BASE_SCORE - _FACTOR * np.log(_BASE_ODDS)


# ============================================================
# RISK TIERS
# ============================================================

def _risk_tier(pd_value: float) -> str:
    """
    Convert Probability of Default into a PRISM risk tier.
    """

    if pd_value < 0.20:
        return "Low"

    if pd_value < 0.40:
        return "Medium"

    if pd_value < 0.70:
        return "High"

    return "Very High"


# ============================================================
# SAFE VALUE EXTRACTION
# ============================================================

def _safe(
    data: Optional[Dict[str, Any]],
    key: str,
) -> Optional[float]:
    """
    Safely extract a numeric value from a dictionary.

    Returns None when:
    - dictionary is missing
    - key does not exist
    - value is None
    - value cannot be converted to a finite float
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
# BUILD RAW FEATURE VECTOR
# ============================================================

def _build_feature_dict(
    bank: Optional[Dict[str, Any]] = None,
    salary: Optional[Dict[str, Any]] = None,
    utility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[float]]:
    """
    Convert the different PRISM input sections into the exact
    five features expected by the scorecard.
    """

    return {
        "credit_debit_ratio": _safe(
            bank,
            "credit_debit_ratio",
        ),

        "cashflow_cv": _safe(
            bank,
            "cashflow_cv",
        ),

        "net_to_gross_ratio": _safe(
            salary,
            "net_to_gross_ratio",
        ),

        "utility_stability": _safe(
            utility,
            "utility_stability",
        ),

        # The source feature is min_balance_l3m,
        # while the trained scorecard feature is min_balance.
        "min_balance": _safe(
            bank,
            "min_balance_l3m",
        ),
    }


# ============================================================
# WoE TRANSFORMATION
# ============================================================

def _apply_woe(
    feature_dict: Dict[str, Optional[float]],
) -> pd.DataFrame:
    """
    Apply the trained WoE binning models to the borrower features.

    Missing values are intentionally passed as np.nan so that the
    trained Missing bin handles them rather than forcing WoE = 0.
    """

    row: Dict[str, float] = {}

    for feature in _FEATURES:

        if feature not in _binning_models:
            raise KeyError(
                f"Missing binning model for feature: {feature}"
            )

        value = feature_dict.get(feature)

        binning = _binning_models[feature]

        if value is None:
            woe = binning.transform(
                [np.nan],
                metric="woe",
            )[0]

        else:
            woe = binning.transform(
                [value],
                metric="woe",
            )[0]

        try:
            woe = float(woe)
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid WoE value generated for feature '{feature}': "
                f"{woe}"
            )

        if not np.isfinite(woe):
            raise ValueError(
                f"Non-finite WoE value generated for feature '{feature}': "
                f"{woe}"
            )

        row[feature] = woe

    return pd.DataFrame(
        [row],
        columns=_FEATURES,
    )


# ============================================================
# LOG-ODDS
# ============================================================

def _compute_log_odds(
    woe_df: pd.DataFrame,
) -> float:
    """
    Calculate model log-odds from the WoE-transformed features.
    """

    values = woe_df[_FEATURES].to_numpy(
        dtype=float
    ).reshape(-1)

    coefficients = np.asarray(
        _model.coef_[0],
        dtype=float,
    )

    intercept = float(_model.intercept_[0])

    if len(coefficients) != len(_FEATURES):
        raise ValueError(
            "Model coefficient count does not match the configured "
            f"feature count. Expected {len(_FEATURES)}, got "
            f"{len(coefficients)}."
        )

    return float(
        intercept + np.dot(coefficients, values)
    )


# ============================================================
# PD
# ============================================================

def _compute_pd(
    log_odds: float,
) -> float:
    """
    Convert logistic-regression log-odds into Probability of Default.
    """

    # Numerically stable sigmoid.
    if log_odds >= 0:
        exp_value = np.exp(-log_odds)
        probability = 1.0 / (1.0 + exp_value)

    else:
        exp_value = np.exp(log_odds)
        probability = exp_value / (1.0 + exp_value)

    return float(
        np.clip(
            probability,
            0.0,
            1.0,
        )
    )


# ============================================================
# CREDIT SCORE
# ============================================================

def _log_odds_to_score(
    log_odds: float,
) -> int:
    """
    Convert model log-odds into the PRISM scorecard score.

    Scorecard scaling:

        Score = Offset - Factor * LogOdds

    with:

        PDO = 50
        Base Score = 600
        Base Odds = 20
    """

    raw_score = (
        _OFFSET
        - _FACTOR * log_odds
    )

    return int(
        np.clip(
            raw_score,
            300,
            900,
        )
    )


# ============================================================
# SCORECARD FEATURE CONTRIBUTIONS
# ============================================================

def _feature_contributions(
    woe_df: pd.DataFrame,
) -> Dict[str, float]:
    """
    Calculate each feature's contribution to the final score.

    This is the exact scorecard feature contribution:

        contribution_i = -Factor * coefficient_i * WoE_i

    These values explain how each feature moves the score relative
    to the scorecard intercept.

    Note:
        These are scorecard contributions, not true SHAP values.
    """

    woe_values = woe_df[_FEATURES].to_numpy(
        dtype=float
    ).reshape(-1)

    coefficients = np.asarray(
        _model.coef_[0],
        dtype=float,
    )

    contributions = (
        -_FACTOR
        * coefficients
        * woe_values
    )

    return {
        feature: float(contribution)
        for feature, contribution in zip(
            _FEATURES,
            contributions,
        )
    }


# ============================================================
# REASON CODES
# ============================================================

def _build_reason_codes(
    contributions: Dict[str, float],
    top_n: int = 4,
) -> list:
    """
    Return the strongest scorecard feature contributions.

    Features are ranked by absolute score impact.
    """

    ranked = sorted(
        contributions.items(),
        key=lambda item: abs(item[1]),
        reverse=True,
    )

    reasons = []

    for feature, contribution in ranked[:top_n]:

        direction = (
            "increases risk"
            if contribution < 0
            else "reduces risk"
        )

        reasons.append(
            {
                "feature": feature,
                "contribution": round(
                    contribution,
                    2,
                ),
                "direction": direction,
            }
        )

    return reasons


# ============================================================
# CONFIDENCE
# ============================================================

def _compute_confidence(
    feature_dict: Dict[str, Optional[float]],
    pd_value: float,
) -> Dict[str, Any]:
    """
    Compute the current PRISM confidence indicator.

    This is a heuristic confidence layer based on:

        - document/data coverage
        - feature completeness
        - distance of PD from 0.5

    It is NOT a calibrated probability of model correctness.
    """

    present_features = sum(
        value is not None
        for value in feature_dict.values()
    )

    data_quality = (
        present_features / len(_FEATURES)
    )

    model_certainty = abs(
        pd_value - 0.5
    ) * 2.0

    document_coverage = data_quality

    confidence = (
        0.4 * document_coverage
        + 0.3 * data_quality
        + 0.3 * model_certainty
    )

    confidence = float(
        np.clip(
            confidence,
            0.0,
            1.0,
        )
    )

    if confidence >= 0.75:
        band = "High"

    elif confidence >= 0.50:
        band = "Moderate"

    else:
        band = "Low"

    return {
        "score": round(
            confidence,
            4,
        ),
        "band": band,
        "data_quality": round(
            data_quality,
            4,
        ),
        "model_certainty": round(
            model_certainty,
            4,
        ),
    }


# ============================================================
# MAIN SCORING FUNCTION
# ============================================================

def score_borrower(
    bank: Optional[Dict[str, Any]] = None,
    salary: Optional[Dict[str, Any]] = None,
    utility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Score a borrower using the existing PRISM scorecard.

    Parameters
    ----------
    bank:
        Bank statement derived features.

    salary:
        Salary/income derived features.

    utility:
        Utility payment derived features.

    Returns
    -------
    dict
        Complete PRISM risk assessment.
    """

    # --------------------------------------------------------
    # 1. Build raw feature vector
    # --------------------------------------------------------

    feature_dict = _build_feature_dict(
        bank=bank,
        salary=salary,
        utility=utility,
    )

    # --------------------------------------------------------
    # 2. Apply WoE transformation
    # --------------------------------------------------------

    woe_df = _apply_woe(
        feature_dict
    )

    # --------------------------------------------------------
    # 3. Compute model log-odds
    # --------------------------------------------------------

    log_odds = _compute_log_odds(
        woe_df
    )

    # --------------------------------------------------------
    # 4. Compute PD
    # --------------------------------------------------------

    pd_value = _compute_pd(
        log_odds
    )

    # --------------------------------------------------------
    # 5. Convert to score
    # --------------------------------------------------------

    score = _log_odds_to_score(
        log_odds
    )

    # --------------------------------------------------------
    # 6. Determine risk tier
    # --------------------------------------------------------

    risk_tier = _risk_tier(
        pd_value
    )

    # --------------------------------------------------------
    # 7. Feature contributions
    # --------------------------------------------------------

    contributions = _feature_contributions(
        woe_df
    )

    # --------------------------------------------------------
    # 8. Reason codes
    # --------------------------------------------------------

    reason_codes = _build_reason_codes(
        contributions
    )

    # --------------------------------------------------------
    # 9. Confidence
    # --------------------------------------------------------

    confidence = _compute_confidence(
        feature_dict,
        pd_value,
    )

    # --------------------------------------------------------
    # 10. Return result
    # --------------------------------------------------------

    return {
        "score": score,

        "pd": round(
            pd_value,
            6,
        ),

        "risk_tier": risk_tier,

        "log_odds": round(
            log_odds,
            6,
        ),

        "features": {
            feature: (
                None
                if value is None
                else float(value)
            )
            for feature, value
            in feature_dict.items()
        },

        "woe_features": {
            feature: round(
                float(woe_df.iloc[0][feature]),
                6,
            )
            for feature in _FEATURES
        },

        "feature_contributions": {
            feature: round(
                contribution,
                2,
            )
            for feature, contribution
            in contributions.items()
        },

        "reason_codes": reason_codes,

        "confidence": confidence,
    }


# ============================================================
# OPTIONAL BACKWARD-COMPATIBLE ALIAS
# ============================================================

def risk_score(
    bank: Optional[Dict[str, Any]] = None,
    salary: Optional[Dict[str, Any]] = None,
    utility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Backward-compatible alias for existing code that may call
    risk_score().
    """

    return score_borrower(
        bank=bank,
        salary=salary,
        utility=utility,
    )


# ============================================================
# MODULE EXPORTS
# ============================================================

__all__ = [
    "score_borrower",
    "risk_score",
]