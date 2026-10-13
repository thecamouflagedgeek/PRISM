"""
PRISM — Ground-Truth Calibration Audit
---------------------------------------

Purpose:
    Validate raw and calibrated PD against the actual test labels.

This script is READ-ONLY.
It does not retrain, recalibrate, modify, or overwrite any PRISM artifact.

Checks:
    1. Load current PD artifact
    2. Load ground-truth labels
    3. Validate observation counts
    4. Detect the target/default column
    5. Compare raw PD vs actual defaults
    6. Compare calibrated PD vs actual defaults
    7. Calculate AUC, Brier score, log loss
    8. Produce calibration-by-band statistics
    9. Check whether calibration improves probability accuracy
   10. Check rank preservation
"""

from pathlib import Path
import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    roc_auc_score,
    brier_score_loss,
    log_loss,
)


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PD_PATH = (
    PROJECT_ROOT
    / "backend"
    / "scoring"
    / "artifacts"
    / "pd_output.pkl"
)

GROUND_TRUTH_PATH = (
    PROJECT_ROOT
    / "tests"
    / "dataset"
    / "labels"
    / "ground_truth.csv"
)


# ============================================================
# HELPERS
# ============================================================

def load_pickle(path):
    with open(path, "rb") as f:
        return joblib.load(f)


def find_target_column(df):
    """
    Try to identify the binary default/target column.
    """

    preferred_names = [
        "default",
        "target",
        "label",
        "y",
        "bad",
        "is_default",
        "default_flag",
        "loan_default",
        "ground_truth",
    ]

    # Exact preferred names first
    for name in preferred_names:
        if name in df.columns:
            values = df[name].dropna().unique()

            if len(values) <= 2:
                return name

    # Case-insensitive matching
    lower_map = {
        str(col).lower(): col
        for col in df.columns
    }

    for name in preferred_names:
        if name in lower_map:
            col = lower_map[name]
            values = df[col].dropna().unique()

            if len(values) <= 2:
                return col

    # Fall back to any binary numeric column
    for col in df.columns:
        series = df[col].dropna()

        if len(series) == 0:
            continue

        unique_values = set(series.unique())

        if unique_values.issubset({0, 1}) and len(unique_values) == 2:
            return col

    return None


def evaluate_predictions(name, y_true, pd_values):
    """
    Calculate probability and ranking metrics.
    """

    pd_values = np.asarray(pd_values, dtype=float)
    y_true = np.asarray(y_true, dtype=int)

    # Safety clipping only for metric calculation.
    # Does NOT modify the stored artifact.
    clipped = np.clip(pd_values, 1e-6, 1 - 1e-6)

    auc = roc_auc_score(y_true, clipped)
    brier = brier_score_loss(y_true, clipped)
    logloss = log_loss(y_true, clipped)

    print(f"\n{name}")
    print("-" * 72)
    print(f"Mean PD        : {clipped.mean():.6f}")
    print(f"Actual default : {y_true.mean():.6f}")
    print(f"Mean PD gap    : {clipped.mean() - y_true.mean():+.6f}")
    print(f"AUC            : {auc:.6f}")
    print(f"Brier score    : {brier:.6f}")
    print(f"Log loss       : {logloss:.6f}")

    return {
        "mean_pd": clipped.mean(),
        "actual_rate": y_true.mean(),
        "pd_gap": clipped.mean() - y_true.mean(),
        "auc": auc,
        "brier": brier,
        "log_loss": logloss,
    }


def calibration_table(y_true, pd_values):
    """
    Group predictions into PD bands and compare predicted
    probability with observed default rate.
    """

    pd_values = np.asarray(pd_values, dtype=float)
    y_true = np.asarray(y_true, dtype=int)

    bins = np.array([
        0.0,
        0.10,
        0.20,
        0.30,
        0.40,
        0.50,
        0.60,
        0.70,
        0.80,
        0.90,
        1.00,
    ])

    labels = [
        "0-10%",
        "10-20%",
        "20-30%",
        "30-40%",
        "40-50%",
        "50-60%",
        "60-70%",
        "70-80%",
        "80-90%",
        "90-100%",
    ]

    band = pd.cut(
        pd_values,
        bins=bins,
        labels=labels,
        include_lowest=True,
        right=True,
    )

    rows = []

    for label in labels:

        mask = band == label

        count = int(mask.sum())

        if count == 0:
            continue

        predicted = pd_values[mask].mean()
        actual = y_true[mask].mean()
        gap = predicted - actual

        rows.append({
            "PD Band": label,
            "Count": count,
            "Predicted PD": predicted,
            "Actual Default Rate": actual,
            "Gap": gap,
        })

    return pd.DataFrame(rows)


# ============================================================
# MAIN AUDIT
# ============================================================

print("=" * 72)
print("PRISM — GROUND-TRUTH PD CALIBRATION AUDIT")
print("=" * 72)

print(f"\nProject root:")
print(PROJECT_ROOT)

print("\nCurrent PD artifact:")
print(PD_PATH)

print("\nGround-truth labels:")
print(GROUND_TRUTH_PATH)


# ============================================================
# 1. FILE VALIDATION
# ============================================================

print("\n" + "=" * 72)
print("1. FILE VALIDATION")
print("=" * 72)

if not PD_PATH.exists():
    raise FileNotFoundError(
        f"PD artifact not found:\n{PD_PATH}"
    )

if not GROUND_TRUTH_PATH.exists():
    raise FileNotFoundError(
        f"Ground-truth file not found:\n{GROUND_TRUTH_PATH}"
    )

print("PASS: PD artifact found.")
print("PASS: Ground-truth CSV found.")


# ============================================================
# 2. LOAD PD ARTIFACT
# ============================================================

print("\n" + "=" * 72)
print("2. PD ARTIFACT")
print("=" * 72)

pd_artifact = load_pickle(PD_PATH)

print("Keys:")
print(list(pd_artifact.keys()))

required_keys = [
    "raw_pd_values",
    "pd_values",
]

for key in required_keys:

    if key not in pd_artifact:
        raise KeyError(
            f"Required key '{key}' missing from PD artifact."
        )

raw_pd = np.asarray(
    pd_artifact["raw_pd_values"],
    dtype=float,
)

calibrated_pd = np.asarray(
    pd_artifact["pd_values"],
    dtype=float,
)

print(f"\nRaw PD observations        : {len(raw_pd)}")
print(f"Calibrated PD observations : {len(calibrated_pd)}")

if len(raw_pd) != len(calibrated_pd):
    raise ValueError(
        "Raw and calibrated PD arrays have different lengths."
    )

print("PASS: raw/calibrated observation counts match.")


# ============================================================
# 3. LOAD GROUND TRUTH
# ============================================================

print("\n" + "=" * 72)
print("3. GROUND TRUTH")
print("=" * 72)

ground_truth = pd.read_csv(GROUND_TRUTH_PATH)

print("Columns:")
print(list(ground_truth.columns))

print(f"\nRows: {len(ground_truth)}")

target_column = find_target_column(ground_truth)

if target_column is None:
    raise ValueError(
        "Could not identify a binary target/default column."
    )

print(f"Detected target column: {target_column}")

y_true = ground_truth[target_column].to_numpy()

# Convert boolean/string representations if necessary
if y_true.dtype == bool:
    y_true = y_true.astype(int)

else:

    try:
        y_true = y_true.astype(float).astype(int)
    except Exception as exc:
        raise ValueError(
            f"Could not convert target column '{target_column}' "
            f"to binary 0/1 values."
        ) from exc


unique_targets = sorted(np.unique(y_true).tolist())

print(f"Target values: {unique_targets}")

if not set(unique_targets).issubset({0, 1}):
    raise ValueError(
        f"Ground truth is not binary 0/1. "
        f"Found values: {unique_targets}"
    )

print(f"Actual defaults : {int(y_true.sum())}")
print(f"Actual default rate : {y_true.mean():.6f}")


# ============================================================
# 4. OBSERVATION ALIGNMENT
# ============================================================

print("\n" + "=" * 72)
print("4. OBSERVATION ALIGNMENT")
print("=" * 72)

print(f"PD observations       : {len(raw_pd)}")
print(f"Ground-truth rows     : {len(y_true)}")

if len(raw_pd) != len(y_true):

    raise ValueError(
        "\nObservation count mismatch.\n"
        "The PD artifact and ground-truth labels cannot be safely "
        "compared until their row alignment is established."
    )

print("PASS: observation counts match.")

print(
    "\nIMPORTANT:"
    "\nThis audit assumes the ground_truth.csv row order corresponds "
    "to the test observations used to generate pd_output.pkl."
)


# ============================================================
# 5. RAW PD EVALUATION
# ============================================================

raw_metrics = evaluate_predictions(
    "RAW PD",
    y_true,
    raw_pd,
)


# ============================================================
# 6. CALIBRATED PD EVALUATION
# ============================================================

calibrated_metrics = evaluate_predictions(
    "CALIBRATED PD",
    y_true,
    calibrated_pd,
)


# ============================================================
# 7. CALIBRATION IMPROVEMENT
# ============================================================

print("\n" + "=" * 72)
print("7. CALIBRATION IMPACT")
print("=" * 72)

brier_change = (
    calibrated_metrics["brier"]
    - raw_metrics["brier"]
)

logloss_change = (
    calibrated_metrics["log_loss"]
    - raw_metrics["log_loss"]
)

gap_raw = abs(raw_metrics["pd_gap"])
gap_cal = abs(calibrated_metrics["pd_gap"])

print(f"Raw mean-PD gap        : {gap_raw:.6f}")
print(f"Calibrated mean-PD gap : {gap_cal:.6f}")

print(
    f"\nBrier score change     : {brier_change:+.6f}"
)

print(
    f"Log-loss change        : {logloss_change:+.6f}"
)

if gap_cal < gap_raw:
    print(
        "\nPASS: calibration moves the overall mean PD "
        "closer to the observed default rate."
    )
else:
    print(
        "\nWARNING: calibration does not reduce the overall "
        "mean-PD gap."
    )

if calibrated_metrics["brier"] < raw_metrics["brier"]:
    print(
        "PASS: calibrated PD has a lower Brier score."
    )
else:
    print(
        "WARNING: calibrated PD does not improve Brier score."
    )

if calibrated_metrics["log_loss"] < raw_metrics["log_loss"]:
    print(
        "PASS: calibrated PD has a lower log loss."
    )
else:
    print(
        "WARNING: calibrated PD does not improve log loss."
    )


# ============================================================
# 8. RANK PRESERVATION
# ============================================================

print("\n" + "=" * 72)
print("8. RANK PRESERVATION")
print("=" * 72)

raw_order = np.argsort(raw_pd)
calibrated_order = np.argsort(calibrated_pd)

same_order = np.array_equal(
    raw_order,
    calibrated_order,
)

if same_order:
    print(
        "PASS: calibration preserves the exact ordering "
        "of borrowers."
    )
else:
    print(
        "WARNING: calibration changes borrower ordering."
    )


# ============================================================
# 9. CALIBRATION TABLE — RAW
# ============================================================

print("\n" + "=" * 72)
print("9. RAW PD CALIBRATION TABLE")
print("=" * 72)

raw_table = calibration_table(
    y_true,
    raw_pd,
)

print(
    raw_table.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)


# ============================================================
# 10. CALIBRATION TABLE — CALIBRATED
# ============================================================

print("\n" + "=" * 72)
print("10. CALIBRATED PD CALIBRATION TABLE")
print("=" * 72)

calibrated_table = calibration_table(
    y_true,
    calibrated_pd,
)

print(
    calibrated_table.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)


# ============================================================
# 11. CALIBRATION ERROR
# ============================================================

print("\n" + "=" * 72)
print("11. CALIBRATION ERROR")
print("=" * 72)

raw_table_error = (
    raw_table["Gap"].abs().mean()
)

calibrated_table_error = (
    calibrated_table["Gap"].abs().mean()
)

print(
    f"Mean absolute band gap — Raw        : "
    f"{raw_table_error:.6f}"
)

print(
    f"Mean absolute band gap — Calibrated : "
    f"{calibrated_table_error:.6f}"
)

if calibrated_table_error < raw_table_error:
    print(
        "\nPASS: calibration reduces mean absolute "
        "band-level calibration error."
    )
else:
    print(
        "\nWARNING: calibration does not reduce "
        "mean absolute band-level calibration error."
    )


# ============================================================
# 12. FINAL INTERPRETATION
# ============================================================

print("\n" + "=" * 72)
print("12. FINAL AUDIT SUMMARY")
print("=" * 72)

print(
    f"\nRaw PD mean        : "
    f"{raw_metrics['mean_pd']:.6f}"
)

print(
    f"Calibrated PD mean : "
    f"{calibrated_metrics['mean_pd']:.6f}"
)

print(
    f"Actual default rate: "
    f"{raw_metrics['actual_rate']:.6f}"
)

print(
    f"\nRaw AUC            : "
    f"{raw_metrics['auc']:.6f}"
)

print(
    f"Calibrated AUC     : "
    f"{calibrated_metrics['auc']:.6f}"
)

print(
    f"\nRaw Brier          : "
    f"{raw_metrics['brier']:.6f}"
)

print(
    f"Calibrated Brier   : "
    f"{calibrated_metrics['brier']:.6f}"
)

print(
    f"\nRaw Log Loss       : "
    f"{raw_metrics['log_loss']:.6f}"
)

print(
    f"Calibrated Log Loss: "
    f"{calibrated_metrics['log_loss']:.6f}"
)

print("\n" + "-" * 72)

if (
    calibrated_metrics["brier"] < raw_metrics["brier"]
    and calibrated_metrics["log_loss"] < raw_metrics["log_loss"]
    and calibrated_table_error < raw_table_error
):
    print(
        "OVERALL: CALIBRATION IMPROVES PROBABILITY QUALITY."
    )

elif (
    calibrated_metrics["brier"] > raw_metrics["brier"]
    and calibrated_metrics["log_loss"] > raw_metrics["log_loss"]
):
    print(
        "OVERALL: CALIBRATION DOES NOT IMPROVE PROBABILITY QUALITY."
    )

else:
    print(
        "OVERALL: MIXED CALIBRATION RESULT — "
        "inspect the detailed metrics and calibration tables."
    )

print("\nNO MODEL OR ARTIFACTS WERE MODIFIED.")

print("\n" + "=" * 72)
print("GROUND-TRUTH CALIBRATION AUDIT COMPLETE")
print("=" * 72)