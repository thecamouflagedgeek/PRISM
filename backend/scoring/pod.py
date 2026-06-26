"""
PRISM — Stage 6: Probability of Default (PD) Estimation
=========================================================
Literature basis:
    Basel Committee (2004) — International Convergence of Capital Measurement
                             and Capital Standards (Basel II), Annex 5
    Bluhm, Overbeck & Wagner (2002) — Introduction to Credit Risk Modelling
    Merton (1974) — On the Pricing of Corporate Debt (structural model foundation)

What PD means in the scorecard context:
    PD = P(borrower defaults within 12 months | observed features)
       = σ(log-odds)
       = 1 / (1 + exp(-log_odds))

Where log_odds = β₀ + Σ(β_i × WoE_i) from the fitted LR model.

Key Basel II IRB requirements for PD:
    1. PD must be a long-run average default rate, not point-in-time.
       (Our synthetic data approximates this — real deployment needs
        through-the-cycle calibration.)
    2. PD estimates must be validated annually against observed default rates.
    3. Minimum PD floor: 0.03% for corporate/retail (Basel II Article 285).
    4. PD must be stress-tested under adverse economic scenarios.
"""

import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import LogisticRegression


PD_FLOOR = 0.0003   # Basel II minimum PD floor (0.03%)
PD_CAP   = 0.9999   # Practical upper cap


def compute_pd(
    model: LogisticRegression,
    X_woe: np.ndarray
) -> np.ndarray:
    """
    Compute Probability of Default from WoE-transformed features.

    PD = σ(log_odds) = 1 / (1 + exp(-log_odds))

    Applies Basel II floor and practical ceiling.

    Parameters
    ----------
    model : fitted LogisticRegression
    X_woe : np.ndarray of shape (n_samples, n_features), WoE-transformed

    Returns
    -------
    pd_values : np.ndarray of shape (n_samples,), values in [PD_FLOOR, PD_CAP]
    """
    raw_pd = model.predict_proba(X_woe)[:, 1]
    return np.clip(raw_pd, PD_FLOOR, PD_CAP)


def compute_log_odds(
    model: LogisticRegression,
    X_woe: np.ndarray
) -> np.ndarray:
    """
    Extract raw log-odds from the LR model.
    log_odds = β₀ + X_woe · β

    This is the intermediate quantity used in Stage 7 for score scaling.
    sklearn's decision_function returns exactly this.
    """
    return model.decision_function(X_woe)


def pd_to_odds(pd_value: float) -> float:
    """
    Convert PD to Odds (Good:Bad ratio).
    Odds = (1 - PD) / PD

    Used in PDO score scaling formula (Stage 7).
    A borrower with PD=0.05 has odds = 19:1 (19 good for every 1 bad).
    """
    pd_value = np.clip(pd_value, PD_FLOOR, PD_CAP)
    return (1 - pd_value) / pd_value


def pd_from_log_odds(log_odds: float) -> float:
    """
    Single-value PD from log-odds (for inference-time use in scorer.py).
    Equivalent to sklearn's predict_proba but for scalar input.
    """
    log_odds = max(min(log_odds, 500), -500)   # numerical safety
    return 1 / (1 + np.exp(-log_odds))


def assign_pd_band(pd_value: float) -> str:
    """
    Assign a PD band label per industry conventions.
    These bands are used in the risk tier output (Stage 10).

    Bands aligned with Moody's/S&P rating philosophy:
        AAA equivalent  : PD < 0.1%
        Investment grade: PD < 5%
        Sub-investment  : PD < 20%
        Speculative     : PD < 40%
        Distressed      : PD >= 40%
    """
    if pd_value < 0.001:
        return "AAA-equivalent  (< 0.1%)"
    elif pd_value < 0.05:
        return "Investment Grade (< 5%)"
    elif pd_value < 0.20:
        return "Sub-investment  (< 20%)"
    elif pd_value < 0.40:
        return "Speculative     (< 40%)"
    else:
        return "Distressed      (≥ 40%)"


def pd_validation_report(
    y_true: np.ndarray,
    pd_values: np.ndarray,
    n_buckets: int = 10
) -> pd.DataFrame:
    """
    Calibration validation: compare predicted PD vs actual default rate
    within each PD decile bucket.

    Basel II requires predicted PD ≈ observed default rate within each bucket.
    Significant divergence triggers a model recalibration requirement.

    Returns a DataFrame showing:
        bucket | avg_predicted_PD | observed_default_rate | difference
    """
    df = pd.DataFrame({"y": y_true, "pd": pd_values})
    df["bucket"] = pd.qcut(df["pd"], n_buckets, labels=False, duplicates="drop")

    report = df.groupby("bucket").agg(
        n                     = ("y", "count"),
        avg_predicted_pd      = ("pd", "mean"),
        observed_default_rate = ("y", "mean")
    ).reset_index(drop=True)

    report["difference"]    = (
        report["observed_default_rate"] - report["avg_predicted_pd"]
    ).round(4)

    report["calibrated"]    = report["difference"].abs().apply(
        lambda d: "✓" if d < 0.05 else "✗ Recalibrate"
    )

    return report.round(4)


# ── STANDALONE RUN ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Load artifacts
    model = joblib.load("artifacts/lr_model.pkl")
    data  = joblib.load("artifacts/woe_datasets.pkl")

    X_test_woe = data["X_test_woe"].values
    y_test     = data["y_test"].values

    print("Stage 6 — Computing PD on test set...")
    pd_values  = compute_pd(model, X_test_woe)
    log_odds   = compute_log_odds(model, X_test_woe)

    print(f"\n  PD descriptive stats:")
    print(f"    Mean PD : {pd_values.mean():.4f}")
    print(f"    Min PD  : {pd_values.min():.4f}")
    print(f"    Max PD  : {pd_values.max():.4f}")
    print(f"    PD > 40%: {(pd_values > 0.4).sum()} borrowers")

    print(f"\n  Sample PD bands (first 5 borrowers):")
    for i in range(5):
        band = assign_pd_band(pd_values[i])
        print(f"    Borrower {i+1}: PD={pd_values[i]:.4f}  →  {band}")

    print("\nStage 6 — PD Calibration Validation Report:")
    cal_report = pd_validation_report(y_test, pd_values)
    print(cal_report.to_string(index=False))

    # Save PD values for Stage 7
    joblib.dump({"log_odds": log_odds, "pd_values": pd_values},
                "artifacts/pd_output.pkl")

    print("\nStage 6 complete.")