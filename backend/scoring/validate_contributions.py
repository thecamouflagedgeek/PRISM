"""
PRISM - Feature Contribution Baseline Validation

Purpose:
    Audit how each feature contributes to the existing
    Logistic Regression scorecard.

Pipeline inspected:

    Raw Feature
        ↓
    WoE
        ↓
    Logistic Regression coefficient
        ↓
    Log-odds contribution
        ↓
    Score contribution

IMPORTANT:
    - Read-only
    - Does NOT retrain the model
    - Does NOT modify artifacts
    - Does NOT change thresholds
    - Uses the historical artifacts exactly as stored
"""

import os
import joblib
import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_DIR = os.path.join(BASE_DIR, "artifacts")

BINNING_PATH = os.path.join(ARTIFACT_DIR, "binning.pkl")
LR_PATH = os.path.join(ARTIFACT_DIR, "lr_model.pkl")
WOE_PATH = os.path.join(ARTIFACT_DIR, "woe_datasets.pkl")

FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]

# Historical score scaling parameters
PDO = 50
BASE_SCORE = 600
BASE_ODDS = 1 / 20

FACTOR = PDO / np.log(2)
OFFSET = BASE_SCORE - FACTOR * np.log(BASE_ODDS)


# ============================================================
# HELPERS
# ============================================================

def print_header(title):
    print()
    print("=" * 90)
    print(title)
    print("=" * 90)


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


# ============================================================
# LOAD ARTIFACTS
# ============================================================

def load_artifacts():

    print_header("PRISM - FEATURE CONTRIBUTION BASELINE VALIDATION")

    print()
    print("[1] Loading historical artifacts...")

    for path in [BINNING_PATH, LR_PATH, WOE_PATH]:

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Required artifact not found:\n{path}"
            )

    binning_models = joblib.load(BINNING_PATH)
    lr_model = joblib.load(LR_PATH)
    woe_data = joblib.load(WOE_PATH)

    print(f"    Binning : {BINNING_PATH}")
    print(f"    LR      : {LR_PATH}")
    print(f"    WOE     : {WOE_PATH}")

    return binning_models, lr_model, woe_data


# ============================================================
# MODEL CHECK
# ============================================================

def validate_model_structure(lr_model, woe_data):

    print()
    print("[2] Checking model structure...")

    if not hasattr(lr_model, "coef_"):
        raise TypeError(
            "Loaded LR artifact does not contain coefficients."
        )

    coefficients = np.asarray(lr_model.coef_)

    if coefficients.ndim != 2:
        raise ValueError(
            f"Unexpected coefficient shape: {coefficients.shape}"
        )

    if coefficients.shape[0] != 1:
        raise ValueError(
            "Expected binary Logistic Regression with one "
            "coefficient row."
        )

    if coefficients.shape[1] != len(FEATURES):
        raise ValueError(
            f"Expected {len(FEATURES)} coefficients but found "
            f"{coefficients.shape[1]}."
        )

    print(f"    Classes      : {lr_model.classes_}")
    print(f"    Intercept    : {lr_model.intercept_[0]:.8f}")
    print(f"    Coef shape   : {coefficients.shape}")

    print()
    print("    Feature mapping:")

    for feature, coef in zip(
        FEATURES,
        coefficients[0]
    ):
        print(
            f"      {feature:<25} "
            f"{coef:>12.8f}"
        )

    if not isinstance(woe_data, dict):
        raise TypeError(
            "WOE artifact is expected to be a dictionary."
        )

    required_keys = [
        "X_train_woe",
        "y_train",
        "X_test_woe",
        "y_test",
    ]

    missing_keys = [
        key for key in required_keys
        if key not in woe_data
    ]

    if missing_keys:
        raise KeyError(
            f"Missing WOE artifact keys: {missing_keys}"
        )


# ============================================================
# WOE STATISTICS
# ============================================================

def calculate_woe_statistics(X_woe):

    """
    Calculate distribution statistics for each WoE feature.
    """

    rows = []

    for feature in FEATURES:

        if feature not in X_woe.columns:
            raise KeyError(
                f"Feature '{feature}' not found in WOE dataset."
            )

        values = pd.to_numeric(
            X_woe[feature],
            errors="coerce"
        )

        rows.append({
            "feature": feature,
            "mean_woe": values.mean(),
            "std_woe": values.std(),
            "min_woe": values.min(),
            "max_woe": values.max(),
            "mean_abs_woe": values.abs().mean(),
        })

    return pd.DataFrame(rows)


# ============================================================
# CONTRIBUTION CALCULATION
# ============================================================

def calculate_contributions(X_woe, lr_model):

    """
    Calculate per-observation feature contributions.

    Logistic regression:

        log_odds = intercept + sum(coef_i * WoE_i)

    Therefore:

        feature_log_odds_contribution =
            coef_i * WoE_i

    Score contribution:

        feature_score_contribution =
            FACTOR * coef_i * WoE_i

    Note:
        The intercept is not included in individual feature
        contributions.
    """

    coefficients = lr_model.coef_[0]

    log_odds_contributions = pd.DataFrame(
        index=X_woe.index
    )

    score_contributions = pd.DataFrame(
        index=X_woe.index
    )

    for feature, coefficient in zip(
        FEATURES,
        coefficients
    ):

        values = pd.to_numeric(
            X_woe[feature],
            errors="coerce"
        ).fillna(0.0)

        log_odds_contributions[feature] = (
            coefficient * values
        )

        score_contributions[feature] = (
            FACTOR
            * coefficient
            * values
        )

    return (
        log_odds_contributions,
        score_contributions
    )


# ============================================================
# CONTRIBUTION SUMMARY
# ============================================================

def build_contribution_summary(
    X_woe,
    lr_model
):

    coefficients = lr_model.coef_[0]

    log_contrib, score_contrib = calculate_contributions(
        X_woe,
        lr_model
    )

    rows = []

    for i, feature in enumerate(FEATURES):

        coefficient = coefficients[i]

        log_values = log_contrib[feature]
        score_values = score_contrib[feature]

        rows.append({
            "feature": feature,

            "coefficient": coefficient,

            "mean_woe": X_woe[feature].mean(),

            "woe_std": X_woe[feature].std(),

            "min_woe": X_woe[feature].min(),

            "max_woe": X_woe[feature].max(),

            "mean_abs_log_odds_contribution":
                log_values.abs().mean(),

            "max_abs_log_odds_contribution":
                log_values.abs().max(),

            "mean_log_odds_contribution":
                log_values.mean(),

            "mean_abs_score_contribution":
                score_values.abs().mean(),

            "max_abs_score_contribution":
                score_values.abs().max(),

            "mean_score_contribution":
                score_values.mean(),

        })

    summary = pd.DataFrame(rows)

    # --------------------------------------------------------
    # Relative contribution
    # --------------------------------------------------------

    total_abs = summary[
        "mean_abs_score_contribution"
    ].sum()

    if total_abs > 0:

        summary["relative_contribution_pct"] = (
            summary[
                "mean_abs_score_contribution"
            ]
            / total_abs
            * 100
        )

    else:

        summary["relative_contribution_pct"] = 0.0

    return summary


# ============================================================
# SIGN / DIRECTION ANALYSIS
# ============================================================

def analyze_directions(summary):

    print()
    print_header("3. COEFFICIENT & DIRECTION ANALYSIS")

    print()
    print(
        "Important:"
        "\n  Positive score contribution -> increases score"
        "\n  Negative score contribution -> decreases score"
        "\n  In this scorecard, higher score generally means"
        "\n  lower modeled default risk."
    )

    print()
    print("-" * 110)

    print(
        f"{'Feature':<25}"
        f"{'Coefficient':>14}"
        f"{'Mean WoE':>12}"
        f"{'Mean Score':>16}"
        f"{'Avg |Score|':>16}"
        f"{'Relative %':>14}"
    )

    print("-" * 110)

    for _, row in summary.iterrows():

        print(
            f"{row['feature']:<25}"
            f"{row['coefficient']:>14.6f}"
            f"{row['mean_woe']:>12.4f}"
            f"{row['mean_score_contribution']:>16.4f}"
            f"{row['mean_abs_score_contribution']:>16.4f}"
            f"{row['relative_contribution_pct']:>13.2f}%"
        )


# ============================================================
# CONTRIBUTION RANGE ANALYSIS
# ============================================================

def analyze_ranges(summary):

    print()
    print_header("4. FEATURE CONTRIBUTION RANGE")

    print()
    print(
        f"{'Feature':<25}"
        f"{'Min WoE':>12}"
        f"{'Max WoE':>12}"
        f"{'Max |LogOdds|':>18}"
        f"{'Max |Score|':>16}"
    )

    print("-" * 90)

    for _, row in summary.iterrows():

        print(
            f"{row['feature']:<25}"
            f"{row['min_woe']:>12.4f}"
            f"{row['max_woe']:>12.4f}"
            f"{row['max_abs_log_odds_contribution']:>18.4f}"
            f"{row['max_abs_score_contribution']:>16.4f}"
        )


# ============================================================
# MOST INFLUENTIAL FEATURES
# ============================================================

def analyze_ranking(summary):

    print()
    print_header("5. FEATURE INFLUENCE RANKING")

    ranked = summary.sort_values(
        "mean_abs_score_contribution",
        ascending=False
    ).reset_index(drop=True)

    print()
    print(
        "Ranking is based on average absolute score contribution "
        "across the training population."
    )

    print()

    for i, row in ranked.iterrows():

        print(
            f"{i + 1}. {row['feature']}"
            f"  -> "
            f"{row['mean_abs_score_contribution']:.4f} "
            f"average |score contribution| "
            f"({row['relative_contribution_pct']:.2f}%)"
        )


# ============================================================
# EXTREME CONTRIBUTION CHECK
# ============================================================

def analyze_extremes(
    X_woe,
    lr_model
):

    print()
    print_header("6. EXTREME CONTRIBUTION CHECK")

    _, score_contrib = calculate_contributions(
        X_woe,
        lr_model
    )

    print()

    for feature in FEATURES:

        values = score_contrib[feature]

        largest_positive = values.max()
        largest_negative = values.min()

        print(f"{feature}:")
        print(
            f"    Largest positive contribution : "
            f"{largest_positive:+.4f}"
        )
        print(
            f"    Largest negative contribution : "
            f"{largest_negative:+.4f}"
        )


# ============================================================
# SCORE RECONCILIATION CHECK
# ============================================================

def check_score_reconciliation(
    X_woe,
    lr_model
):

    """
    Verify that:

        score =
            OFFSET + FACTOR * (
                intercept + sum(feature contributions)
            )

    This is NOT the final score artifact validation yet.
    It simply checks whether the feature contribution
    mathematics is internally consistent with the LR model.
    """

    print()
    print_header("7. LOG-ODDS / SCORE CONTRIBUTION RECONCILIATION")

    coefficients = lr_model.coef_[0]
    intercept = lr_model.intercept_[0]

    log_contrib, score_contrib = calculate_contributions(
        X_woe,
        lr_model
    )

    reconstructed_log_odds = (
        intercept
        + log_contrib.sum(axis=1)
    )

    reconstructed_score = (
        OFFSET
        + FACTOR * reconstructed_log_odds
    )

    direct_log_odds = (
        lr_model.decision_function(X_woe)
    )

    direct_score = (
        OFFSET
        + FACTOR * direct_log_odds
    )

    log_difference = (
        reconstructed_log_odds
        - direct_log_odds
    )

    score_difference = (
        reconstructed_score
        - direct_score
    )

    print()
    print(
        f"Maximum log-odds difference : "
        f"{np.max(np.abs(log_difference)):.12f}"
    )

    print(
        f"Maximum score difference    : "
        f"{np.max(np.abs(score_difference)):.12f}"
    )

    if np.max(np.abs(log_difference)) < 1e-10:

        print()
        print(
            "PASS - Feature contributions reconcile with "
            "the Logistic Regression decision function."
        )

    else:

        print()
        print(
            "REVIEW - Feature contributions do not fully "
            "reconcile with the Logistic Regression output."
        )


# ============================================================
# FINAL SUMMARY
# ============================================================

def print_final_summary(summary):

    print()
    print_header("8. CONTRIBUTION VALIDATION SUMMARY")

    ranked = summary.sort_values(
        "mean_abs_score_contribution",
        ascending=False
    )

    print()

    print(
        f"{'Rank':<6}"
        f"{'Feature':<25}"
        f"{'IV-independent contribution':>28}"
    )

    print("-" * 70)

    for rank, (_, row) in enumerate(
        ranked.iterrows(),
        start=1
    ):

        print(
            f"{rank:<6}"
            f"{row['feature']:<25}"
            f"{row['relative_contribution_pct']:>25.2f}%"
        )

    print()
    print(
        "Note: Contribution percentage is based on the average "
        "absolute score contribution across the training data."
    )

    print(
        "It is a descriptive diagnostic, not a measure of causal "
        "importance or independent feature importance."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    (
        binning_models,
        lr_model,
        woe_data
    ) = load_artifacts()

    validate_model_structure(
        lr_model,
        woe_data
    )

    # --------------------------------------------------------
    # Use training WOE population for contribution analysis.
    # --------------------------------------------------------

    X_train_woe = woe_data["X_train_woe"]

    if not isinstance(X_train_woe, pd.DataFrame):
        X_train_woe = pd.DataFrame(
            X_train_woe,
            columns=FEATURES
        )

    # Ensure feature ordering matches LR model.
    X_train_woe = X_train_woe[FEATURES].copy()

    print()
    print("[3] Training WOE population...")
    print(
        f"    Observations : {len(X_train_woe)}"
    )
    print(
        f"    Features     : {len(X_train_woe.columns)}"
    )

    # --------------------------------------------------------
    # Build contribution summary.
    # --------------------------------------------------------

    summary = build_contribution_summary(
        X_train_woe,
        lr_model
    )

    analyze_directions(summary)

    analyze_ranges(summary)

    analyze_ranking(summary)

    analyze_extremes(
        X_train_woe,
        lr_model
    )

    check_score_reconciliation(
        X_train_woe,
        lr_model
    )

    print_final_summary(summary)

    # --------------------------------------------------------
    # Final status
    # --------------------------------------------------------

    print()
    print_header("CONTRIBUTION VALIDATION COMPLETE")

    print()
    print("No model or artifact was modified.")
    print("No retraining was performed.")
    print("No thresholds were changed.")
    print()


if __name__ == "__main__":
    main()