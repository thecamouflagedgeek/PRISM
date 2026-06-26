"""
PRISM — Stage 8: Explainability Layer (SHAP Reason Codes)
===========================================================
Literature basis:
    Lundberg & Lee (2017) — A Unified Approach to Interpreting Model Predictions
    CFPB (2013) — ECOA / Regulation B: Adverse Action Notice Requirements
    Siddiqi (2006) — Credit Risk Scorecards, Chapter 11 (Reason Codes)
    RBI (2023) — Fair Practices Code for Digital Lending

Regulatory requirement:
    Under ECOA (US) / RBI Fair Practices Code (India), any credit denial or
    adverse action MUST be accompanied by specific reasons. Vague outputs
    like "score too low" are not compliant.

SHAP for Logistic Regression on WoE features:
    Since our model is linear (LR on WoE), the SHAP values have a closed form:
        φ_i(borrower) = β_i × WoE_i(borrower) - β_i × E[WoE_i]

    where E[WoE_i] is the expected WoE across the population.

    In a linear model, SHAP values equal the coefficient × (feature - mean feature).
    This means SHAP decomposition is EXACT, not approximate, for LR.

    Total log-odds = φ_0 + Σ φ_i
    where φ_0 = β₀ + Σ β_i × E[WoE_i]  (the "base rate" expected log-odds)

Reason codes:
    Sort |φ_i| descending. Top 4 are the reason codes for adverse action notices.
    Convention: positive φ → factor helped the score, negative φ → factor hurt it.
"""

import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import LogisticRegression
from typing import List, Dict


FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance"
]

FEATURE_LABELS = {
    "credit_debit_ratio" : "Credit-to-Debit Ratio",
    "cashflow_cv"        : "Cashflow Stability",
    "net_to_gross_ratio" : "Net-to-Gross Salary Ratio",
    "utility_stability"  : "Utility Payment Stability",
    "min_balance"        : "Minimum Account Balance"
}


def compute_shap_values(
    model: LogisticRegression,
    X_woe: np.ndarray,
    X_train_woe: np.ndarray
) -> np.ndarray:
    """
    Compute exact SHAP values for LR on WoE features.

    φ_i = β_i × (WoE_i - E[WoE_i])

    where E[WoE_i] is estimated from the training set (background distribution).

    Parameters
    ----------
    model       : fitted LogisticRegression
    X_woe       : np.ndarray (n_samples, n_features) — test/inference WoE matrix
    X_train_woe : np.ndarray — used to compute background E[WoE_i]

    Returns
    -------
    shap_values : np.ndarray (n_samples, n_features)
    """
    coefs        = model.coef_[0]                     # β_i for each feature
    mean_woe     = X_train_woe.mean(axis=0)           # E[WoE_i] from training

    # φ_i(x) = β_i × (WoE_i(x) - E[WoE_i])
    shap_values  = coefs * (X_woe - mean_woe)

    return shap_values


def reason_codes_for_borrower(
    shap_values_row: np.ndarray,
    features: list = FEATURES,
    top_n: int = 4
) -> List[Dict]:
    """
    Generate ECOA-compliant reason codes for a single borrower.

    Returns the top_n factors by absolute SHAP value, with direction.
    Adverse action notices typically list the top 4 negative factors.

    Per CFPB / RBI guidance: reasons must be specific and actionable.
    """
    reasons = []
    for i, col in enumerate(features):
        shap_val = shap_values_row[i]
        reasons.append({
            "feature"      : col,
            "label"        : FEATURE_LABELS[col],
            "shap_value"   : round(float(shap_val), 4),
            "direction"    : "positive" if shap_val > 0 else "negative",
            "abs_impact"   : abs(shap_val)
        })

    # Sort by absolute impact, descending
    reasons.sort(key=lambda r: r["abs_impact"], reverse=True)

    return reasons[:top_n]


def adverse_action_notice(reason_codes: List[Dict]) -> str:
    """
    Generate a human-readable adverse action notice from reason codes.
    Required under ECOA / RBI Fair Practices Code for any credit decline.
    """
    negatives = [r for r in reason_codes if r["direction"] == "negative"]
    lines = ["Your credit assessment was affected by the following factors:"]

    for i, r in enumerate(negatives, 1):
        lines.append(f"  {i}. {r['label']} (impact: {r['shap_value']:.4f})")

    if not negatives:
        lines.append("  No adverse factors identified — all signals are positive.")

    return "\n".join(lines)


def population_shap_summary(shap_values: np.ndarray) -> pd.DataFrame:
    """
    Population-level feature importance from mean absolute SHAP values.
    Used for model documentation, periodic review, and feature selection.

    This is the SHAP bar chart summary for the full scorecard.
    """
    mean_abs_shap = np.abs(shap_values).mean(axis=0)

    df = pd.DataFrame({
        "feature"         : FEATURES,
        "label"           : [FEATURE_LABELS[f] for f in FEATURES],
        "mean_abs_shap"   : mean_abs_shap.round(4),
        "mean_shap"       : shap_values.mean(axis=0).round(4),
    }).sort_values("mean_abs_shap", ascending=False)

    df["rank"] = range(1, len(df) + 1)

    return df


# ── STANDALONE RUN ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    model  = joblib.load("artifacts/lr_model.pkl")
    data   = joblib.load("artifacts/woe_datasets.pkl")
    scored = joblib.load("artifacts/scored_output.pkl")

    X_train_woe = data["X_train_woe"].values
    X_test_woe  = scored["X_test_woe"]

    print("Stage 8 — Computing SHAP values (exact, LR closed-form)...")
    shap_values = compute_shap_values(model, X_test_woe, X_train_woe)

    print("\nStage 8 — Population SHAP Feature Importance:")
    pop_summary = population_shap_summary(shap_values)
    print(pop_summary.to_string(index=False))

    print("\nStage 8 — Sample Borrower Reason Codes (first 3 borrowers):")
    for idx in range(3):
        score = scored["scores"][idx]
        pd_v  = scored["pd_values"][idx]
        rc    = reason_codes_for_borrower(shap_values[idx])
        notice= adverse_action_notice(rc)

        print(f"\n  Borrower {idx+1}  |  Score: {score}  |  PD: {pd_v:.4f}")
        print(f"  {'-'*50}")
        print(f"  Reason Codes:")
        for r in rc:
            bar = "▓" * int(abs(r["shap_value"]) * 20)
            sign = "+" if r["direction"] == "positive" else "-"
            print(f"    {r['label']:35s}: {sign}{abs(r['shap_value']):.4f}  {bar}")
        print(f"\n  Adverse Action Notice:\n  {notice}")

    # Save SHAP for Stage 9/10
    joblib.dump({"shap_values": shap_values}, "artifacts/shap_output.pkl")

    print("\nStage 8 complete.")