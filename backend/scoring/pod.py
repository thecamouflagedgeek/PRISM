
"""
PRISM — Stage 6: Probability of Default (PD) Estimation
=========================================================

Stage 6 responsibilities:
    1. Convert Logistic Regression output into raw PD.
    2. Calibrate the PD using a separate calibration layer.
    3. Validate calibrated PD against observed defaults.
    4. Save the calibration model for inference-time scoring.

Architecture:

    WoE features
         ↓
    Logistic Regression
         ↓
    Raw log-odds
         ↓
    PD Calibration
         ↓
    Calibrated log-odds
         ↓
    Calibrated PD
         ↓
    Stage 7 score scaling

Important:
    The calibration layer does NOT retrain the credit-risk model.
    It only corrects systematic over/under-estimation of probabilities.
"""

import os
import numpy as np
import pandas as pd
import joblib

from sklearn.linear_model import LogisticRegression


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PD_FLOOR = 0.0003
PD_CAP = 0.9999

_ARTIFACTS = os.path.join(
    os.path.dirname(__file__),
    "artifacts"
)


# ---------------------------------------------------------------------------
# Basic PD functions
# ---------------------------------------------------------------------------

def compute_log_odds(
    model,
    X_woe: np.ndarray
) -> np.ndarray:
    """
    Extract raw Logistic Regression log-odds.

    log_odds = β0 + X_woe · β
    """
    return model.decision_function(X_woe)


def sigmoid(log_odds: np.ndarray) -> np.ndarray:
    """
    Numerically stable sigmoid transformation.
    """
    log_odds = np.clip(log_odds, -500, 500)

    return 1.0 / (1.0 + np.exp(-log_odds))


def compute_pd(
    model,
    X_woe: np.ndarray
) -> np.ndarray:
    """
    Compute raw Probability of Default from Logistic Regression.

    This is the uncalibrated PD.
    """
    log_odds = compute_log_odds(model, X_woe)
    raw_pd = sigmoid(log_odds)

    return np.clip(raw_pd, PD_FLOOR, PD_CAP)


# ---------------------------------------------------------------------------
# PD calibration
# ---------------------------------------------------------------------------

def fit_pd_calibrator(
    model,
    X_calibration_woe: np.ndarray,
    y_calibration: np.ndarray
):
    """
    Fit a logistic calibration layer on raw model log-odds.

    The calibration model learns:

        calibrated_PD =
            sigmoid(alpha + beta * raw_log_odds)

    This allows both:
        - intercept correction
        - slope correction

    The underlying WoE + Logistic Regression credit model is unchanged.
    """

    raw_log_odds = compute_log_odds(
        model,
        X_calibration_woe
    ).reshape(-1, 1)

    calibrator = LogisticRegression(
        solver="lbfgs",
        C=1.0,
        max_iter=1000
    )

    calibrator.fit(
        raw_log_odds,
        y_calibration
    )

    return calibrator


def calibrate_log_odds(
    calibrator,
    raw_log_odds: np.ndarray
) -> np.ndarray:
    """
    Convert raw model log-odds into calibrated log-odds.

    Because the calibration model is logistic regression:

        calibrated_log_odds =
            calibration_intercept
            + calibration_slope * raw_log_odds
    """

    slope = float(calibrator.coef_[0][0])
    intercept = float(calibrator.intercept_[0])

    return intercept + slope * raw_log_odds


def compute_calibrated_pd(
    calibrator,
    raw_log_odds: np.ndarray
) -> np.ndarray:
    """
    Convert raw model log-odds into calibrated PD.
    """

    calibrated_log_odds = calibrate_log_odds(
        calibrator,
        raw_log_odds
    )

    calibrated_pd = sigmoid(
        calibrated_log_odds
    )

    return np.clip(
        calibrated_pd,
        PD_FLOOR,
        PD_CAP
    )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def compute_calibrated_pd_from_model(
    model,
    calibrator,
    X_woe: np.ndarray
):
    """
    Compute raw and calibrated PD together.

    Returns
    -------
    raw_log_odds
    calibrated_log_odds
    raw_pd
    calibrated_pd
    """

    raw_log_odds = compute_log_odds(
        model,
        X_woe
    )

    raw_pd = np.clip(
        sigmoid(raw_log_odds),
        PD_FLOOR,
        PD_CAP
    )

    calibrated_log_odds = calibrate_log_odds(
        calibrator,
        raw_log_odds
    )

    calibrated_pd = np.clip(
        sigmoid(calibrated_log_odds),
        PD_FLOOR,
        PD_CAP
    )

    return (
        raw_log_odds,
        calibrated_log_odds,
        raw_pd,
        calibrated_pd
    )


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------

def pd_to_odds(pd_value: float) -> float:
    """
    Convert PD into Good:Bad odds.

    Odds = (1 - PD) / PD
    """

    pd_value = float(
        np.clip(
            pd_value,
            PD_FLOOR,
            PD_CAP
        )
    )

    return (1.0 - pd_value) / pd_value


def pd_from_log_odds(log_odds: float) -> float:
    """
    Convert a single log-odds value into PD.

    Used as a fallback utility.
    """

    log_odds = max(
        min(
            float(log_odds),
            500
        ),
        -500
    )

    pd_value = 1.0 / (
        1.0 + np.exp(-log_odds)
    )

    return float(
        np.clip(
            pd_value,
            PD_FLOOR,
            PD_CAP
        )
    )


# ---------------------------------------------------------------------------
# PD bands
# ---------------------------------------------------------------------------

def assign_pd_band(pd_value: float) -> str:
    """
    Assign a descriptive PD band.

    These are descriptive bands used by PRISM.
    They are not external credit ratings.
    """

    if pd_value < 0.001:
        return "Very Low (< 0.1%)"

    elif pd_value < 0.05:
        return "Low (< 5%)"

    elif pd_value < 0.20:
        return "Moderate (< 20%)"

    elif pd_value < 0.40:
        return "High (< 40%)"

    else:
        return "Very High (>= 40%)"


# ---------------------------------------------------------------------------
# Calibration validation
# ---------------------------------------------------------------------------

def pd_validation_report(
    y_true: np.ndarray,
    pd_values: np.ndarray,
    n_buckets: int = 10
) -> pd.DataFrame:
    """
    Compare predicted PD with observed default rate
    across PD decile buckets.
    """

    df = pd.DataFrame({
        "y": np.asarray(y_true),
        "pd": np.asarray(pd_values)
    })

    df["bucket"] = pd.qcut(
        df["pd"],
        n_buckets,
        labels=False,
        duplicates="drop"
    )

    report = (
        df.groupby("bucket")
        .agg(
            n=("y", "count"),
            avg_predicted_pd=("pd", "mean"),
            observed_default_rate=("y", "mean")
        )
        .reset_index(drop=True)
    )

    report["difference"] = (
        report["observed_default_rate"]
        - report["avg_predicted_pd"]
    )

    report["calibrated"] = report["difference"].abs().apply(
        lambda d: "✓" if d < 0.05 else "✗ Recalibrate"
    )

    return report.round(4)


# ---------------------------------------------------------------------------
# Standalone Stage 6
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    print("=" * 65)
    print("PRISM — Stage 6: PD Estimation + Calibration")
    print("=" * 65)

    # -----------------------------------------------------------------------
    # Load model and WoE datasets
    # -----------------------------------------------------------------------

    model_path = os.path.join(
        _ARTIFACTS,
        "lr_model.pkl"
    )

    data_path = os.path.join(
        _ARTIFACTS,
        "woe_datasets.pkl"
    )

    model = joblib.load(model_path)
    data = joblib.load(data_path)

    X_train_woe = data["X_train_woe"].values
    y_train = data["y_train"].values

    X_test_woe = data["X_test_woe"].values
    y_test = data["y_test"].values

    # -----------------------------------------------------------------------
    # Fit calibration layer
    # -----------------------------------------------------------------------

    print("\n[1] Fitting PD calibration layer...")

    calibrator = fit_pd_calibrator(
        model,
        X_train_woe,
        y_train
    )

    calibration_intercept = float(
        calibrator.intercept_[0]
    )

    calibration_slope = float(
        calibrator.coef_[0][0]
    )

    print(
        f"  Calibration intercept : "
        f"{calibration_intercept:.6f}"
    )

    print(
        f"  Calibration slope     : "
        f"{calibration_slope:.6f}"
    )

    # -----------------------------------------------------------------------
    # Compute test PDs
    # -----------------------------------------------------------------------

    (
        raw_log_odds,
        calibrated_log_odds,
        raw_pd,
        calibrated_pd
    ) = compute_calibrated_pd_from_model(
        model,
        calibrator,
        X_test_woe
    )

    # -----------------------------------------------------------------------
    # Basic statistics
    # -----------------------------------------------------------------------

    print("\n[2] Raw PD statistics")

    print(
        f"  Mean : {raw_pd.mean():.4f}"
    )

    print(
        f"  Min  : {raw_pd.min():.4f}"
    )

    print(
        f"  Max  : {raw_pd.max():.4f}"
    )

    print("\n[3] Calibrated PD statistics")

    print(
        f"  Mean : {calibrated_pd.mean():.4f}"
    )

    print(
        f"  Min  : {calibrated_pd.min():.4f}"
    )

    print(
        f"  Max  : {calibrated_pd.max():.4f}"
    )

    print(
        f"\n  Actual test default rate : "
        f"{y_test.mean():.4f}"
    )

    print(
        f"  Raw PD gap               : "
        f"{raw_pd.mean() - y_test.mean():.4f}"
    )

    print(
        f"  Calibrated PD gap        : "
        f"{calibrated_pd.mean() - y_test.mean():.4f}"
    )

    # -----------------------------------------------------------------------
    # Calibration report
    # -----------------------------------------------------------------------

    print("\n[4] Raw PD Calibration Report")
    print("-" * 65)

    raw_report = pd_validation_report(
        y_test,
        raw_pd
    )

    print(
        raw_report.to_string(index=False)
    )

    print("\n[5] Calibrated PD Calibration Report")
    print("-" * 65)

    calibrated_report = pd_validation_report(
        y_test,
        calibrated_pd
    )

    print(
        calibrated_report.to_string(index=False)
    )

    # -----------------------------------------------------------------------
    # Save calibrator
    # -----------------------------------------------------------------------

    calibrator_path = os.path.join(
        _ARTIFACTS,
        "pd_calibrator.pkl"
    )

    joblib.dump(
        calibrator,
        calibrator_path
    )

    print(
        f"\n[6] Calibration model saved:"
        f"\n    {calibrator_path}"
    )

    # -----------------------------------------------------------------------
    # Save calibrated PD output
    # -----------------------------------------------------------------------

    pd_output = {
        "raw_log_odds": raw_log_odds,
        "calibrated_log_odds": calibrated_log_odds,
        "raw_pd_values": raw_pd,
        "pd_values": calibrated_pd,
    }

    pd_output_path = os.path.join(
        _ARTIFACTS,
        "pd_output.pkl"
    )

    joblib.dump(
        pd_output,
        pd_output_path
    )

    print(
        f"\n[7] PD output saved:"
        f"\n    {pd_output_path}"
    )

    print("\n" + "=" * 65)
    print("STAGE 6 COMPLETE")
    print("=" * 65)
