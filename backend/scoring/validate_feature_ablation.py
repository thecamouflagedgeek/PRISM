
"""
PRISM - Feature Ablation Validation
------------------------------------

Purpose:
    Evaluate the contribution of each credit-risk feature by removing
    one feature at a time and comparing model performance.

This is an AUDIT-ONLY script.

It does NOT:
    - retrain the production model
    - modify lr_model.pkl
    - modify binning.pkl
    - modify PD thresholds
    - modify score scaling
    - overwrite production artifacts

Inputs:
    scoring/artifacts/woe_datasets.pkl
    scoring/artifacts/lr_model.pkl

Outputs:
    scoring/validation_results/feature_ablation.csv
"""

import os
import pickle
import numpy as np
import pandas as pd

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score,
    brier_score_loss,
    confusion_matrix,
)


# ============================================================
# CONFIGURATION
# ============================================================

ARTIFACT_DIR = os.path.join(
    os.path.dirname(__file__),
    "artifacts"
)

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__),
    "validation_results"
)

WOE_FILE = os.path.join(
    ARTIFACT_DIR,
    "woe_datasets.pkl"
)

MODEL_FILE = os.path.join(
    ARTIFACT_DIR,
    "lr_model.pkl"
)


FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance"
]


# ============================================================
# HELPERS
# ============================================================

def gini_from_auc(auc):
    return 2 * auc - 1


def ks_statistic(y_true, probabilities):
    """
    Calculate KS statistic between default and non-default
    cumulative distributions.
    """

    df = pd.DataFrame({
        "y": np.asarray(y_true),
        "pd": np.asarray(probabilities)
    })

    df = df.sort_values("pd")

    defaults = (df["y"] == 1).sum()
    non_defaults = (df["y"] == 0).sum()

    if defaults == 0 or non_defaults == 0:
        return np.nan

    df["cum_default"] = (
        (df["y"] == 1).cumsum() / defaults
    )

    df["cum_non_default"] = (
        (df["y"] == 0).cumsum() / non_defaults
    )

    return np.max(
        np.abs(
            df["cum_default"] -
            df["cum_non_default"]
        )
    )


def evaluate_model(X_train, y_train, X_test, y_test, feature_set):
    """
    Train an audit-only Logistic Regression model using the
    selected WOE features.

    IMPORTANT:
    This model is created only for ablation analysis.
    It does not overwrite the production model.
    """

    model = LogisticRegression(
        solver="lbfgs",
        C=1.0,
        max_iter=1000,
        class_weight="balanced",
        random_state=42
    )

    model.fit(
        X_train[feature_set],
        y_train
    )

    train_pd = model.predict_proba(
        X_train[feature_set]
    )[:, 1]

    test_pd = model.predict_proba(
        X_test[feature_set]
    )[:, 1]

    # --------------------------------------------------------
    # Discrimination
    # --------------------------------------------------------

    train_auc = roc_auc_score(
        y_train,
        train_pd
    )

    test_auc = roc_auc_score(
        y_test,
        test_pd
    )

    train_gini = gini_from_auc(train_auc)
    test_gini = gini_from_auc(test_auc)

    train_ks = ks_statistic(
        y_train,
        train_pd
    )

    test_ks = ks_statistic(
        y_test,
        test_pd
    )

    auc_gap = train_auc - test_auc

    # --------------------------------------------------------
    # Calibration
    # --------------------------------------------------------

    brier = brier_score_loss(
        y_test,
        test_pd
    )

    actual_default_rate = np.mean(y_test)
    mean_predicted_pd = np.mean(test_pd)

    pd_gap = (
        mean_predicted_pd -
        actual_default_rate
    )

    # --------------------------------------------------------
    # Threshold 0.50
    # --------------------------------------------------------

    predictions = (
        test_pd >= 0.50
    ).astype(int)

    tn, fp, fn, tp = confusion_matrix(
        y_test,
        predictions,
        labels=[0, 1]
    ).ravel()

    precision = (
        tp / (tp + fp)
        if (tp + fp) > 0
        else 0
    )

    recall = (
        tp / (tp + fn)
        if (tp + fn) > 0
        else 0
    )

    specificity = (
        tn / (tn + fp)
        if (tn + fp) > 0
        else 0
    )

    f1 = (
        2 * precision * recall /
        (precision + recall)
        if (precision + recall) > 0
        else 0
    )

    # --------------------------------------------------------
    # Coefficients
    # --------------------------------------------------------

    coefficients = dict(
        zip(
            feature_set,
            model.coef_[0]
        )
    )

    return {
        "features_used": ", ".join(feature_set),
        "feature_count": len(feature_set),

        "train_auc": train_auc,
        "test_auc": test_auc,

        "train_gini": train_gini,
        "test_gini": test_gini,

        "train_ks": train_ks,
        "test_ks": test_ks,

        "train_test_auc_gap": auc_gap,

        "brier_score": brier,

        "actual_default_rate": actual_default_rate,
        "mean_predicted_pd": mean_predicted_pd,
        "pd_gap": pd_gap,

        "precision_0.50": precision,
        "recall_0.50": recall,
        "specificity_0.50": specificity,
        "f1_0.50": f1,

        "coefficient_magnitudes": str(
            {
                feature: round(
                    abs(coefficients[feature]),
                    6
                )
                for feature in feature_set
            }
        )
    }


# ============================================================
# LOAD DATA
# ============================================================

print("=" * 70)
print("PRISM - FEATURE ABLATION VALIDATION")
print("=" * 70)

print("\nArtifact directory:")
print(ARTIFACT_DIR)

print("\nLoading artifacts...")

if not os.path.exists(WOE_FILE):
    raise FileNotFoundError(
        f"Missing WOE dataset: {WOE_FILE}"
    )

if not os.path.exists(MODEL_FILE):
    raise FileNotFoundError(
        f"Missing LR model: {MODEL_FILE}"
    )


with open(WOE_FILE, "rb") as f:
    woe_data = pickle.load(f)


with open(MODEL_FILE, "rb") as f:
    production_model = pickle.load(f)


X_train = woe_data["X_train_woe"]
y_train = np.asarray(
    woe_data["y_train"]
)

X_test = woe_data["X_test_woe"]
y_test = np.asarray(
    woe_data["y_test"]
)


# ============================================================
# SANITY CHECKS
# ============================================================

print("\n" + "=" * 70)
print("SANITY CHECKS")
print("=" * 70)

print(f"Train observations : {len(X_train)}")
print(f"Test observations  : {len(X_test)}")

print(f"Train WOE shape    : {X_train.shape}")
print(f"Test WOE shape     : {X_test.shape}")

print(f"Features available : {list(X_train.columns)}")

missing_features = [
    feature
    for feature in FEATURES
    if feature not in X_train.columns
]

if missing_features:
    raise ValueError(
        f"Missing features: {missing_features}"
    )

if len(y_train) != len(X_train):
    raise ValueError(
        "Train X/y length mismatch"
    )

if len(y_test) != len(X_test):
    raise ValueError(
        "Test X/y length mismatch"
    )

print("Sanity checks: PASS")


# ============================================================
# PRODUCTION MODEL REFERENCE
# ============================================================

print("\n" + "=" * 70)
print("PRODUCTION MODEL REFERENCE")
print("=" * 70)

print(
    f"Production model type : "
    f"{type(production_model).__name__}"
)

print(
    f"Production features   : "
    f"{FEATURES}"
)

print(
    "\nThe production model will NOT be modified."
)


# ============================================================
# DEFINE ABLATION SETS
# ============================================================

ablation_sets = []

# ------------------------------------------------------------
# Baseline: all five features
# ------------------------------------------------------------

ablation_sets.append(
    ("ALL_FEATURES", FEATURES.copy())
)

# ------------------------------------------------------------
# Remove one feature at a time
# ------------------------------------------------------------

for feature_to_remove in FEATURES:

    remaining_features = [
        feature
        for feature in FEATURES
        if feature != feature_to_remove
    ]

    ablation_sets.append(
        (
            f"WITHOUT_{feature_to_remove}",
            remaining_features
        )
    )


# ============================================================
# RUN ABLATION
# ============================================================

print("\n" + "=" * 70)
print("RUNNING FEATURE ABLATION")
print("=" * 70)

results = []

for experiment_name, feature_set in ablation_sets:

    print("\n" + "-" * 70)
    print(experiment_name)
    print("-" * 70)

    print(
        "Features:",
        ", ".join(feature_set)
    )

    result = evaluate_model(
        X_train,
        y_train,
        X_test,
        y_test,
        feature_set
    )

    result["experiment"] = experiment_name

    results.append(result)

    print(
        f"Test AUC : "
        f"{result['test_auc']:.6f}"
    )

    print(
        f"Test Gini: "
        f"{result['test_gini']:.6f}"
    )

    print(
        f"Test KS  : "
        f"{result['test_ks']:.6f}"
    )

    print(
        f"Brier    : "
        f"{result['brier_score']:.6f}"
    )

    print(
        f"PD gap   : "
        f"{result['pd_gap']:+.6f}"
    )

    print(
        f"F1 @ 0.50: "
        f"{result['f1_0.50']:.6f}"
    )


# ============================================================
# RESULTS DATAFRAME
# ============================================================

results_df = pd.DataFrame(results)

# Put experiment first
columns = [
    "experiment",
    "feature_count",
    "features_used",

    "train_auc",
    "test_auc",

    "train_gini",
    "test_gini",

    "train_ks",
    "test_ks",

    "train_test_auc_gap",

    "brier_score",

    "actual_default_rate",
    "mean_predicted_pd",
    "pd_gap",

    "precision_0.50",
    "recall_0.50",
    "specificity_0.50",
    "f1_0.50",

    "coefficient_magnitudes"
]

results_df = results_df[columns]


# ============================================================
# COMPARE AGAINST BASELINE
# ============================================================

baseline = results_df[
    results_df["experiment"] == "ALL_FEATURES"
].iloc[0]


results_df["delta_test_auc"] = (
    results_df["test_auc"] -
    baseline["test_auc"]
)

results_df["delta_test_gini"] = (
    results_df["test_gini"] -
    baseline["test_gini"]
)

results_df["delta_test_ks"] = (
    results_df["test_ks"] -
    baseline["test_ks"]
)

results_df["delta_brier"] = (
    results_df["brier_score"] -
    baseline["brier_score"]
)

results_df["delta_pd_gap"] = (
    results_df["pd_gap"] -
    baseline["pd_gap"]
)

results_df["delta_f1_0.50"] = (
    results_df["f1_0.50"] -
    baseline["f1_0.50"]
)


# ============================================================
# SAVE RESULTS
# ============================================================

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)

output_file = os.path.join(
    OUTPUT_DIR,
    "feature_ablation.csv"
)

results_df.to_csv(
    output_file,
    index=False
)


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("FEATURE ABLATION SUMMARY")
print("=" * 70)

display_columns = [
    "experiment",
    "test_auc",
    "test_gini",
    "test_ks",
    "brier_score",
    "pd_gap",
    "f1_0.50",
    "delta_test_auc",
    "delta_brier"
]

print(
    results_df[
        display_columns
    ].to_string(
        index=False,
        float_format=lambda x: f"{x:.6f}"
    )
)


# ============================================================
# BEST / WORST FEATURES
# ============================================================

print("\n" + "=" * 70)
print("ABLATION INTERPRETATION")
print("=" * 70)

ablation_only = results_df[
    results_df["experiment"] != "ALL_FEATURES"
].copy()

# Lowest AUC after removal = feature whose removal hurts most
most_important = ablation_only.loc[
    ablation_only["delta_test_auc"].idxmin()
]

# Highest AUC after removal = feature whose removal improves most
largest_improvement = ablation_only.loc[
    ablation_only["delta_test_auc"].idxmax()
]

print(
    "\nLargest AUC loss after removing:"
)

print(
    f"  {most_important['experiment']}"
)

print(
    f"  Test AUC change: "
    f"{most_important['delta_test_auc']:+.6f}"
)

print(
    "\nLargest AUC improvement after removing:"
)

print(
    f"  {largest_improvement['experiment']}"
)

print(
    f"  Test AUC change: "
    f"{largest_improvement['delta_test_auc']:+.6f}"
)


# ============================================================
# IMPORTANT NOTICE
# ============================================================

print("\n" + "=" * 70)
print("AUDIT STATUS")
print("=" * 70)

print(
    "Feature ablation completed."
)

print(
    "NO production model was modified."
)

print(
    "NO artifacts were overwritten."
)

print(
    "NO threshold was changed."
)

print(
    "Results saved to:"
)

print(output_file)
