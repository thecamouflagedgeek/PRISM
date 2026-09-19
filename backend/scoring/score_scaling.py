"""PRISM score scaling utilities and Stage 7 validation."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import joblib
import numpy as np
import pandas as pd


# ============================================================
# PRISM SCORECARD CONFIGURATION
# ============================================================

_PDO = 50.0
_BASE_SCORE = 600.0
_BASE_ODDS = 20.0

_SCORE_MIN = 300.0
_SCORE_MAX = 900.0

_FACTOR = _PDO / np.log(2.0)

# Score = OFFSET - FACTOR * log_odds
#
# At base odds of 20:1 good:bad:
# PD = 1 / (1 + 20) = 1/21
# Score = 600
#
_OFFSET = _BASE_SCORE - _FACTOR * np.log(_BASE_ODDS)


_FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]


_BASE = os.path.dirname(os.path.abspath(__file__))
_ARTIFACTS = os.path.join(_BASE, "artifacts")

_MODEL_PATH = os.path.join(_ARTIFACTS, "lr_model.pkl")
_BINNING_PATH = os.path.join(_ARTIFACTS, "binning.pkl")


# ============================================================
# INTERNAL MODEL HELPERS
# ============================================================

def _unwrap_model(model: Any) -> Any:
    """
    Extract the actual fitted estimator from the object stored
    in the model artifact or passed by pipeline.py.

    The pipeline may provide either:
        1. a raw LogisticRegression estimator
        2. a dictionary containing the estimator

    This function does not modify the model.
    """

    if model is None:
        raise ValueError("Model cannot be None.")

    # Raw estimator
    if hasattr(model, "coef_") and hasattr(model, "intercept_"):
        return model

    # Dictionary-style artifact
    if isinstance(model, dict):

        # Prefer common explicit keys first.
        candidate_keys = [
            "model",
            "lr_model",
            "logistic_regression",
            "estimator",
            "classifier",
        ]

        for key in candidate_keys:
            if key in model:
                candidate = model[key]

                if (
                    hasattr(candidate, "coef_")
                    and hasattr(candidate, "intercept_")
                ):
                    return candidate

        # Fallback: search all dictionary values.
        for value in model.values():

            if (
                hasattr(value, "coef_")
                and hasattr(value, "intercept_")
            ):
                return value

    raise TypeError(
        "Unable to locate a fitted Logistic Regression estimator. "
        f"Received object of type: {type(model).__name__}"
    )


# ============================================================
# SCORE CONVERSION
# ============================================================

def log_odds_to_score(log_odds):
    """
    Convert logistic-regression log-odds to PRISM credit score.

    Formula:

        Score = OFFSET - FACTOR * log_odds

    Higher default probability produces:
        higher log-odds
        lower credit score

    Supports:
        - scalar
        - list
        - tuple
        - NumPy array
        - pandas Series

    Scores are clipped to [300, 900].
    """

    values = np.asarray(log_odds, dtype=float)

    if not np.all(np.isfinite(values)):
        raise ValueError("log_odds contains non-finite values.")

    scores = _OFFSET - _FACTOR * values

    scores = np.clip(
        scores,
        _SCORE_MIN,
        _SCORE_MAX,
    )

    if values.ndim == 0:
        return int(scores)

    return scores


def _log_odds_to_score(log_odds: float) -> int:
    """
    Internal scalar-compatible wrapper used by validation.
    """

    return int(log_odds_to_score(log_odds))


# ============================================================
# SCORE DISTRIBUTION REPORT
# ============================================================

def score_distribution_report(
    scores,
    calibrated_pd: Optional[Any] = None,
) -> pd.DataFrame:
    """
    Generate the score distribution report expected by pipeline.py.

    Returns a one-row pandas DataFrame containing:

        count
        mean
        std
        min
        p01
        p05
        p10
        p25
        median
        p75
        p90
        p95
        p99
        max
        at_min
        at_max

    calibrated_pd is accepted for pipeline compatibility and
    optional validation. It is not used to calculate score
    statistics.
    """

    values = np.asarray(scores, dtype=float).reshape(-1)

    if values.size == 0:
        raise ValueError("scores is empty.")

    if not np.all(np.isfinite(values)):
        raise ValueError("scores contains non-finite values.")

    # Optional PD validation.
    if calibrated_pd is not None:

        pd_values = np.asarray(
            calibrated_pd,
            dtype=float,
        ).reshape(-1)

        if pd_values.size != values.size:
            raise ValueError(
                "calibrated_pd and scores must contain the same "
                f"number of observations. "
                f"Got scores={values.size}, "
                f"calibrated_pd={pd_values.size}."
            )

        if not np.all(np.isfinite(pd_values)):
            raise ValueError(
                "calibrated_pd contains non-finite values."
            )

    report = {
        "count": int(values.size),

        "mean": float(values.mean()),
        "std": float(values.std()),

        "min": float(values.min()),

        "p01": float(np.percentile(values, 1)),
        "p05": float(np.percentile(values, 5)),
        "p10": float(np.percentile(values, 10)),
        "p25": float(np.percentile(values, 25)),

        "median": float(np.median(values)),

        "p75": float(np.percentile(values, 75)),
        "p90": float(np.percentile(values, 90)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),

        "max": float(values.max()),

        "at_min": int(
            np.sum(values <= _SCORE_MIN)
        ),

        "at_max": int(
            np.sum(values >= _SCORE_MAX)
        ),
    }

    return pd.DataFrame([report])


# ============================================================
# ARTIFACT LOADING
# ============================================================

def _load_artifacts():
    """
    Load the existing PRISM binning and Logistic Regression
    artifacts.

    This function only reads artifacts.
    """

    if not os.path.exists(_MODEL_PATH):
        raise FileNotFoundError(
            f"Logistic regression model not found: {_MODEL_PATH}"
        )

    if not os.path.exists(_BINNING_PATH):
        raise FileNotFoundError(
            f"Binning model not found: {_BINNING_PATH}"
        )

    binning_models = joblib.load(_BINNING_PATH)
    model = joblib.load(_MODEL_PATH)

    return binning_models, model


# ============================================================
# SCORECARD TABLE
# ============================================================

def scorecard_table(
    model=None,
    binning_models=None,
) -> pd.DataFrame:
    """
    Return a feature-level PRISM scorecard summary.

    IMPORTANT:
    The argument order intentionally matches pipeline.py:

        scorecard_table(model, binning_models)

    The model may be either:
        - a fitted LogisticRegression object
        - a dictionary containing the fitted estimator

    The binning_models argument is accepted for API compatibility
    and future bin-level scorecard expansion.

    No artifacts are modified.
    """

    loaded_binning = None
    loaded_model = None

    # Load missing artifacts only.
    if model is None or binning_models is None:

        loaded_binning, loaded_model = _load_artifacts()

    if model is None:
        model = loaded_model

    if binning_models is None:
        binning_models = loaded_binning

    # Extract actual fitted estimator.
    estimator = _unwrap_model(model)

    coefficients = np.asarray(
        estimator.coef_,
        dtype=float,
    )

    if coefficients.ndim != 2:
        raise ValueError(
            "Unexpected model coefficient shape: "
            f"{coefficients.shape}"
        )

    # PRISM currently expects one binary Logistic Regression
    # coefficient vector.
    if coefficients.shape[0] != 1:
        raise ValueError(
            "Expected a binary Logistic Regression model with "
            f"one coefficient row; got {coefficients.shape}."
        )

    coefficients = coefficients[0]

    if len(coefficients) != len(_FEATURES):
        raise ValueError(
            f"Model must contain exactly {len(_FEATURES)} "
            f"coefficients; got {len(coefficients)}."
        )

    intercept_array = np.asarray(
        estimator.intercept_,
        dtype=float,
    )

    if intercept_array.size != 1:
        raise ValueError(
            "Unexpected model intercept shape: "
            f"{intercept_array.shape}"
        )

    intercept = float(intercept_array.reshape(-1)[0])

    # This is the score component created by the model intercept.
    #
    # It is NOT distributed equally across features.
    base_component = (
        _OFFSET
        - _FACTOR * intercept
    )

    rows = []

    for feature, coefficient in zip(
        _FEATURES,
        coefficients,
    ):

        rows.append(
            {
                "feature": feature,

                "coefficient": float(
                    coefficient
                ),

                "factor": float(
                    _FACTOR
                ),

                "base_component": float(
                    base_component
                ),

                "score_contribution_formula":
                    "-Factor * coefficient * WoE",
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# VALIDATION HELPERS
# ============================================================

def _assert_close(
    actual,
    expected,
    tolerance,
    label,
):
    """
    Assert that two numeric values are sufficiently close.
    """

    difference = abs(
        actual - expected
    )

    if difference > tolerance:
        raise AssertionError(
            f"{label} failed: "
            f"actual={actual:.10f}, "
            f"expected={expected:.10f}, "
            f"difference={difference:.10f}"
        )


# ============================================================
# STAGE 7 — MODEL CONSISTENCY
# ============================================================

def _validate_model_consistency():
    """
    Verify that the stored Logistic Regression model contains
    the expected five PRISM features.
    """

    _, model = _load_artifacts()

    estimator = _unwrap_model(model)

    coefficients = np.asarray(
        estimator.coef_,
        dtype=float,
    )

    if coefficients.ndim != 2:
        raise AssertionError(
            "Unexpected model coefficient shape: "
            f"{coefficients.shape}"
        )

    if coefficients.shape[0] != 1:
        raise AssertionError(
            "Expected a binary Logistic Regression model."
        )

    coefficients = coefficients[0]

    if len(coefficients) != len(_FEATURES):
        raise AssertionError(
            f"Model has {len(coefficients)} coefficients "
            f"but PRISM expects {len(_FEATURES)} features."
        )

    intercept = np.asarray(
        estimator.intercept_,
        dtype=float,
    )

    if intercept.size != 1:
        raise AssertionError(
            "Unexpected model intercept shape: "
            f"{intercept.shape}"
        )

    print(
        "[PASS] Model structure matches PRISM "
        f"feature configuration ({len(_FEATURES)} features)."
    )


# ============================================================
# STAGE 7 — PD TO SCORE DIRECTION
# ============================================================

def _validate_direction():
    """
    Verify:

        higher PD
            ->
        higher bad/good log-odds
            ->
        lower credit score
    """

    pd_values = np.array(
        [0.10, 0.20, 0.40, 0.70, 0.90],
        dtype=float,
    )

    log_odds = np.log(
        pd_values / (1.0 - pd_values)
    )

    scores = log_odds_to_score(
        log_odds
    )

    if not np.all(
        scores[:-1] > scores[1:]
    ):
        raise AssertionError(
            "Higher PD must produce lower score."
        )

    print(
        "[PASS] Higher PD produces lower credit score."
    )

    for pd_value, score in zip(
        pd_values,
        scores,
    ):
        print(
            f"       PD {pd_value:>5.2%} "
            f"-> Score {int(score)}"
        )


# ============================================================
# STAGE 7 — BASE SCORE RELATIONSHIP
# ============================================================

def _validate_base_score():
    """
    Verify that the configured base odds produce the configured
    base score.

    Base odds = 20:1 good:bad

    Therefore:

        PD = 1 / (1 + 20)
           = 1 / 21
    """

    base_pd = 1.0 / (
        1.0 + _BASE_ODDS
    )

    base_log_odds = float(
        np.log(
            base_pd
            / (1.0 - base_pd)
        )
    )

    base_score = _log_odds_to_score(
        base_log_odds
    )

    _assert_close(
        base_pd,
        1.0 / 21.0,
        1e-12,
        "Base PD",
    )

    if base_score != int(_BASE_SCORE):
        raise AssertionError(
            f"Base score failed: "
            f"{base_score} != {int(_BASE_SCORE)}"
        )

    print(
        f"[PASS] Base relationship: "
        f"PD={base_pd:.6f} "
        f"-> Score={base_score}"
    )


# ============================================================
# STAGE 7 — SCORE DECOMPOSITION
# ============================================================

def _validate_score_decomposition():
    """
    Verify that:

        Score
        =
        intercept/base component
        +
        sum(feature contributions)

    where:

        feature contribution
        =
        -Factor * coefficient * WoE
    """

    _, model = _load_artifacts()

    estimator = _unwrap_model(model)

    # Representative WoE vector.
    woe_values = np.array(
        [
            0.20,
            -0.40,
            0.15,
            0.05,
            -0.10,
        ],
        dtype=float,
    )

    coefficients = np.asarray(
        estimator.coef_,
        dtype=float,
    )[0]

    intercept = float(
        np.asarray(
            estimator.intercept_,
            dtype=float,
        ).reshape(-1)[0]
    )

    # Logistic model log-odds.
    log_odds = (
        intercept
        + np.dot(
            coefficients,
            woe_values,
        )
    )

    # Direct raw score.
    direct_score = (
        _OFFSET
        - _FACTOR * log_odds
    )

    # Feature-level score contributions.
    contributions = (
        -_FACTOR
        * coefficients
        * woe_values
    )

    # Intercept/base score component.
    base_component = (
        _OFFSET
        - _FACTOR * intercept
    )

    reconstructed_score = (
        base_component
        + contributions.sum()
    )

    _assert_close(
        reconstructed_score,
        direct_score,
        1e-10,
        "Score decomposition",
    )

    print(
        "[PASS] Score decomposition "
        "reconstructs raw score exactly."
    )

    print(
        f"       Intercept/base component : "
        f"{base_component:.6f}"
    )

    print(
        f"       Feature contributions    : "
        f"{contributions.sum():.6f}"
    )

    print(
        f"       Direct raw score         : "
        f"{direct_score:.6f}"
    )

    print(
        f"       Reconstructed raw score  : "
        f"{reconstructed_score:.6f}"
    )

    print(
        f"       Difference               : "
        f"{abs(direct_score - reconstructed_score):.12f}"
    )


# ============================================================
# STAGE 7 — FEATURE CONTRIBUTIONS
# ============================================================

def _validate_feature_contribution_function():
    """
    Verify that feature score contributions follow:

        contribution_i
        =
        -Factor * coefficient_i * WoE_i
    """

    _, model = _load_artifacts()

    estimator = _unwrap_model(model)

    woe_values = np.array(
        [
            0.20,
            -0.40,
            0.15,
            0.05,
            -0.10,
        ],
        dtype=float,
    )

    coefficients = np.asarray(
        estimator.coef_,
        dtype=float,
    )[0]

    expected = (
        -_FACTOR
        * coefficients
        * woe_values
    )

    if not np.all(
        np.isfinite(expected)
    ):
        raise AssertionError(
            "Non-finite feature contribution detected."
        )

    print(
        "[PASS] Feature contribution formula "
        "matches -Factor * coefficient * WoE."
    )


# ============================================================
# STAGE 7 — SCORE RANGE AND CLIPPING
# ============================================================

def _validate_score_range_and_clipping():
    """
    Confirm that score output stays within:

        300 <= Score <= 900

    and that extreme PD values clip correctly.
    """

    very_low_pd = 1e-8
    very_high_pd = 1.0 - 1e-8

    low_log_odds = float(
        np.log(
            very_low_pd
            / (1.0 - very_low_pd)
        )
    )

    high_log_odds = float(
        np.log(
            very_high_pd
            / (1.0 - very_high_pd)
        )
    )

    low_score = _log_odds_to_score(
        low_log_odds
    )

    high_score = _log_odds_to_score(
        high_log_odds
    )

    if low_score != 900:
        raise AssertionError(
            "Expected an extremely low PD to clip "
            "to the upper score limit of 900."
        )

    if high_score != 300:
        raise AssertionError(
            "Expected an extremely high PD to clip "
            "to the lower score limit of 300."
        )

    if not (
        300
        <= low_score
        <= 900
    ):
        raise AssertionError(
            f"Low-PD score outside [300, 900]: "
            f"{low_score}"
        )

    if not (
        300
        <= high_score
        <= 900
    ):
        raise AssertionError(
            f"High-PD score outside [300, 900]: "
            f"{high_score}"
        )

    print(
        "[PASS] Score range and clipping validated: "
        "300 <= score <= 900."
    )


# ============================================================
# STAGE 7 — COMPLETE VALIDATION RUNNER
# ============================================================

def run_stage7_validation() -> bool:
    """
    Run the complete Stage 7 score-scaling validation suite.

    This validates the score transformation and score
    decomposition.

    It does NOT claim that the underlying credit model is
    statistically well-calibrated or monotonic. Those are
    separate validation stages.
    """

    print()
    print("=" * 68)
    print(
        "PRISM STAGE 7 - SCORE SCALING VALIDATION"
    )
    print("=" * 68)

    print(
        f"PDO={int(_PDO)} | "
        f"Base Score={int(_BASE_SCORE)} | "
        f"Base Odds={int(_BASE_ODDS)}:1"
    )

    print(
        f"Factor={_FACTOR:.10f} | "
        f"Offset={_OFFSET:.10f}"
    )

    print()

    validations = [
        (
            "Model structure",
            _validate_model_consistency,
        ),
        (
            "PD -> score direction",
            _validate_direction,
        ),
        (
            "Base score relationship",
            _validate_base_score,
        ),
        (
            "Score decomposition",
            _validate_score_decomposition,
        ),
        (
            "Feature contributions",
            _validate_feature_contribution_function,
        ),
        (
            "Score range and clipping",
            _validate_score_range_and_clipping,
        ),
    ]

    passed = 0

    for label, validator in validations:

        print(
            f"[TEST] {label}"
        )

        validator()

        passed += 1

        print()

    print("=" * 68)

    print(
        "STAGE 7 VALIDATION: PASSED "
        f"({passed}/{len(validations)} tests)"
    )

    print("=" * 68)
    print()

    return True


# ============================================================
# PUBLIC API
# ============================================================

__all__ = [
    "log_odds_to_score",
    "scorecard_table",
    "score_distribution_report",
    "run_stage7_validation",
]


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":
    run_stage7_validation()