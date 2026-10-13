"""
PRISM - P1 Model-Level Validation
----------------------------------

Purpose:
    Validate the existing historical Logistic Regression scorecard
    at the MODEL level.

Checks:
    1. Discrimination
       - AUC
       - Gini
       - KS
       - Accuracy / Precision / Recall / F1

    2. Calibration
       - Brier score
       - Calibration by PD band
       - Mean predicted PD vs actual default rate

    3. Risk-tier behaviour
       - Population in each PD/risk band
       - Average predicted PD
       - Actual default rate
       - Prediction gap

    4. Threshold analysis
       - Precision
       - Recall
       - Specificity
       - FPR
       - F1
       - Confusion matrix

    5. Train vs Test comparison
       - AUC
       - Gini
       - KS

IMPORTANT:
    This script does NOT:
        - retrain the model
        - modify artifacts
        - change thresholds
        - calibrate PD
        - merge bins
"""

import os
import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    roc_auc_score,
    roc_curve,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    brier_score_loss,
)


# ============================================================
# CONFIGURATION
# ============================================================

ARTIFACT_DIR = os.path.join(
    os.path.dirname(__file__),
    "artifacts"
)

WOE_PATH = os.path.join(ARTIFACT_DIR, "woe_datasets.pkl")
MODEL_PATH = os.path.join(ARTIFACT_DIR, "lr_model.pkl")
PD_PATH = os.path.join(ARTIFACT_DIR, "pd_output.pkl")


FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]


# ============================================================
# HELPERS
# ============================================================

def print_section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def calculate_ks(y_true, pd_values):
    """
    Calculate KS statistic using predicted PD.
    """
    fpr, tpr, thresholds = roc_curve(y_true, pd_values)

    ks_values = np.abs(tpr - fpr)

    idx = np.argmax(ks_values)

    return {
        "ks": ks_values[idx],
        "threshold": thresholds[idx],
    }


def classification_metrics(y_true, pd_values, threshold=0.50):
    """
    Calculate classification metrics at a chosen PD threshold.
    """

    predictions = (pd_values >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(
        y_true,
        predictions,
        labels=[0, 1]
    ).ravel()

    precision = precision_score(
        y_true,
        predictions,
        zero_division=0
    )

    recall = recall_score(
        y_true,
        predictions,
        zero_division=0
    )

    specificity = (
        tn / (tn + fp)
        if (tn + fp) > 0
        else 0
    )

    fpr = (
        fp / (fp + tn)
        if (fp + tn) > 0
        else 0
    )

    return {
        "threshold": threshold,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "tp": tp,
        "accuracy": accuracy_score(y_true, predictions),
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "fpr": fpr,
        "f1": f1_score(
            y_true,
            predictions,
            zero_division=0
        ),
    }


# ============================================================
# LOAD ARTIFACTS
# ============================================================

print_section("LOADING ARTIFACTS")

print(f"Artifact directory: {ARTIFACT_DIR}")

if not os.path.exists(WOE_PATH):
    raise FileNotFoundError(f"Missing: {WOE_PATH}")

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Missing: {MODEL_PATH}")

if not os.path.exists(PD_PATH):
    raise FileNotFoundError(f"Missing: {PD_PATH}")


woe_data = joblib.load(WOE_PATH)
model = joblib.load(MODEL_PATH)
pd_data = joblib.load(PD_PATH)

print("Loaded:")
print("  - woe_datasets.pkl")
print("  - lr_model.pkl")
print("  - pd_output.pkl")


# ============================================================
# EXTRACT DATA
# ============================================================

X_train_woe = woe_data["X_train_woe"]
y_train = np.asarray(woe_data["y_train"])

X_test_woe = woe_data["X_test_woe"]
y_test = np.asarray(woe_data["y_test"])


# pd_output.pkl contains the stored test PD values
pd_test = np.asarray(pd_data["pd_values"])


# ============================================================
# SANITY CHECKS
# ============================================================

print_section("SANITY CHECKS")

print(f"Train observations : {len(y_train)}")
print(f"Test observations  : {len(y_test)}")

print(f"Train WOE shape    : {X_train_woe.shape}")
print(f"Test WOE shape     : {X_test_woe.shape}")

print(f"Features            : {FEATURES}")
print(f"Model classes       : {model.classes_}")

if len(y_test) != len(pd_test):
    raise ValueError(
        "Test labels and stored PD values have different lengths."
    )

print("Sanity checks: PASS")


# ============================================================
# 1. MODEL DISCRIMINATION
# ============================================================

print_section("1. MODEL DISCRIMINATION")


# Test predictions from the actual LR model
pd_train_model = model.predict_proba(X_train_woe)[:, 1]
pd_test_model = model.predict_proba(X_test_woe)[:, 1]


# Compare stored PD with model-generated PD
pd_difference = np.max(
    np.abs(pd_test_model - pd_test)
)

print(f"Maximum stored-vs-model PD difference: {pd_difference:.12f}")


# -----------------------------
# Train
# -----------------------------

train_auc = roc_auc_score(
    y_train,
    pd_train_model
)

train_gini = 2 * train_auc - 1

train_ks = calculate_ks(
    y_train,
    pd_train_model
)


# -----------------------------
# Test
# -----------------------------

test_auc = roc_auc_score(
    y_test,
    pd_test_model
)

test_gini = 2 * test_auc - 1

test_ks = calculate_ks(
    y_test,
    pd_test_model
)


print("\nTRAIN")
print(f"AUC  : {train_auc:.6f}")
print(f"Gini : {train_gini:.6f}")
print(f"KS   : {train_ks['ks']:.6f}")

print("\nTEST")
print(f"AUC  : {test_auc:.6f}")
print(f"Gini : {test_gini:.6f}")
print(f"KS   : {test_ks['ks']:.6f}")


auc_gap = train_auc - test_auc

print(f"\nTrain-Test AUC gap: {auc_gap:.6f}")


if auc_gap > 0.03:
    print("WARNING: Train-test AUC gap > 0.03")
else:
    print("Train-test AUC gap: acceptable under current audit rule")


# ============================================================
# 2. TEST CALIBRATION
# ============================================================

print_section("2. CALIBRATION")


brier = brier_score_loss(
    y_test,
    pd_test_model
)

print(f"Brier score: {brier:.6f}")

print(f"Actual default rate : {y_test.mean():.6f}")
print(f"Mean predicted PD   : {pd_test_model.mean():.6f}")

print(
    f"Overall PD gap      : "
    f"{pd_test_model.mean() - y_test.mean():+.6f}"
)


# ============================================================
# CALIBRATION BANDS
# ============================================================

print("\nCalibration by predicted PD band")

calibration_bins = [
    (0.00, 0.10),
    (0.10, 0.20),
    (0.20, 0.30),
    (0.30, 0.40),
    (0.40, 0.50),
    (0.50, 0.60),
    (0.60, 0.70),
    (0.70, 0.80),
    (0.80, 0.90),
    (0.90, 1.01),
]


calibration_results = []


for lower, upper in calibration_bins:

    mask = (
        (pd_test_model >= lower)
        & (pd_test_model < upper)
    )

    n = mask.sum()

    if n == 0:
        continue

    predicted = pd_test_model[mask].mean()
    actual = y_test[mask].mean()

    gap = predicted - actual

    calibration_results.append({
        "pd_band": f"{lower:.0%}-{min(upper, 1):.0%}",
        "n": n,
        "predicted_pd": predicted,
        "actual_default_rate": actual,
        "gap": gap,
    })

    print(
        f"{lower:.0%}-{min(upper, 1):.0%} | "
        f"n={n:4d} | "
        f"pred={predicted:.4f} | "
        f"actual={actual:.4f} | "
        f"gap={gap:+.4f}"
    )


calibration_df = pd.DataFrame(
    calibration_results
)


# ============================================================
# 3. RISK-TIER VALIDATION
# ============================================================

print_section("3. RISK-TIER VALIDATION")


risk_tiers = [
    ("LOW", 0.00, 0.20),
    ("MEDIUM", 0.20, 0.40),
    ("HIGH", 0.40, 0.70),
    ("VERY_HIGH", 0.70, 1.01),
]


tier_results = []


for tier, lower, upper in risk_tiers:

    mask = (
        (pd_test_model >= lower)
        & (pd_test_model < upper)
    )

    n = mask.sum()

    if n == 0:
        continue

    population_pct = n / len(y_test)

    avg_pd = pd_test_model[mask].mean()

    actual_default = y_test[mask].mean()

    gap = avg_pd - actual_default

    tier_results.append({
        "tier": tier,
        "n": n,
        "population_pct": population_pct,
        "average_predicted_pd": avg_pd,
        "actual_default_rate": actual_default,
        "gap": gap,
    })

    print(
        f"{tier:10s} | "
        f"n={n:4d} | "
        f"population={population_pct:.2%} | "
        f"pred_PD={avg_pd:.4f} | "
        f"actual={actual_default:.4f} | "
        f"gap={gap:+.4f}"
    )


tier_df = pd.DataFrame(
    tier_results
)


# ============================================================
# 4. THRESHOLD ANALYSIS
# ============================================================

print_section("4. THRESHOLD ANALYSIS")


thresholds = [
    0.20,
    0.25,
    0.30,
    0.35,
    0.40,
    0.45,
    0.50,
    0.55,
    0.60,
    0.65,
    0.70,
]


threshold_results = []


for threshold in thresholds:

    result = classification_metrics(
        y_test,
        pd_test_model,
        threshold
    )

    threshold_results.append(result)

    print(
        f"\nThreshold = {threshold:.2f}"
    )

    print(
        f"TN={result['tn']} "
        f"FP={result['fp']} "
        f"FN={result['fn']} "
        f"TP={result['tp']}"
    )

    print(
        f"Precision   : {result['precision']:.4f}"
    )

    print(
        f"Recall      : {result['recall']:.4f}"
    )

    print(
        f"Specificity : {result['specificity']:.4f}"
    )

    print(
        f"FPR         : {result['fpr']:.4f}"
    )

    print(
        f"F1          : {result['f1']:.4f}"
    )


threshold_df = pd.DataFrame(
    threshold_results
)


# ============================================================
# 5. FIND BEST F1 — FOR AUDIT ONLY
# ============================================================

print_section("5. THRESHOLD SUMMARY")


best_f1_row = threshold_df.loc[
    threshold_df["f1"].idxmax()
]

print(
    f"Highest F1 threshold: "
    f"{best_f1_row['threshold']:.2f}"
)

print(
    f"F1: "
    f"{best_f1_row['f1']:.4f}"
)

print(
    "\nIMPORTANT:"
    "\nThis does NOT mean the threshold should be changed."
    "\nThreshold selection must be based on lending/risk policy."
)


# ============================================================
# 6. SCORE / PD DISTRIBUTION
# ============================================================

print_section("6. PD DISTRIBUTION")


percentiles = [0, 10, 25, 50, 75, 90, 95, 99, 100]

values = np.percentile(
    pd_test_model,
    percentiles
)

for p, value in zip(percentiles, values):

    print(
        f"P{p:3d}: {value:.6f}"
    )


# ============================================================
# 7. MODEL COEFFICIENTS
# ============================================================

print_section("7. MODEL COEFFICIENTS")


coefficients = model.coef_[0]

coefficient_df = pd.DataFrame({
    "feature": FEATURES,
    "coefficient": coefficients,
    "absolute_coefficient": np.abs(coefficients),
})


print(
    coefficient_df.to_string(
        index=False
    )
)


# ============================================================
# 8. SAVE AUDIT OUTPUTS
# ============================================================

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__),
    "validation_results"
)

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


calibration_path = os.path.join(
    OUTPUT_DIR,
    "model_calibration.csv"
)

tiers_path = os.path.join(
    OUTPUT_DIR,
    "model_risk_tiers.csv"
)

threshold_path = os.path.join(
    OUTPUT_DIR,
    "model_threshold_analysis.csv"
)

coefficients_path = os.path.join(
    OUTPUT_DIR,
    "model_coefficients.csv"
)


calibration_df.to_csv(
    calibration_path,
    index=False
)

tier_df.to_csv(
    tiers_path,
    index=False
)

threshold_df.to_csv(
    threshold_path,
    index=False
)

coefficient_df.to_csv(
    coefficients_path,
    index=False
)


# ============================================================
# FINAL SUMMARY
# ============================================================

print_section("FINAL MODEL-LEVEL SUMMARY")

print(f"Test AUC             : {test_auc:.6f}")
print(f"Test Gini            : {test_gini:.6f}")
print(f"Test KS              : {test_ks['ks']:.6f}")
print(f"Brier score          : {brier:.6f}")

print(
    f"Actual default rate  : "
    f"{y_test.mean():.6%}"
)

print(
    f"Mean predicted PD    : "
    f"{pd_test_model.mean():.6%}"
)

print(
    f"Overall PD gap       : "
    f"{pd_test_model.mean() - y_test.mean():+.6%}"
)

print(
    f"Train-Test AUC gap   : "
    f"{auc_gap:.6f}"
)


print("\nOutput files:")
print(f"  {calibration_path}")
print(f"  {tiers_path}")
print(f"  {threshold_path}")
print(f"  {coefficients_path}")


print("\nNO MODEL OR ARTIFACT WAS MODIFIED.")