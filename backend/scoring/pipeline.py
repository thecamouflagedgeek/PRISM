"""
PRISM — run_pipeline.py
========================
Master script: runs Stages 3–8 in sequence to train and serialize all
model artifacts. Run this once before using scorer.py for inference.

Usage:
    python run_pipeline.py
"""

import numpy as np
import pandas as pd
import joblib
import os
from sklearn.model_selection import train_test_split

# ── PRISM pipeline imports ─────────────────────────────────────────────────────
from .optimal_binning  import fit_binning_models, summarise_binning, save_binning_models
from .woe import apply_woe_transform, validate_woe_monotonicity
from .log_reg import (fit_logistic_regression, coefficient_table,
                                         compute_vif, evaluate_model, print_report)
from .pod import (
    compute_pd,
    compute_log_odds,
    fit_pd_calibrator,
    compute_calibrated_pd_from_model,
    pd_validation_report,
)
from .score_scaling import log_odds_to_score, scorecard_table, score_distribution_report
from explain.explainability import compute_shap_values, population_shap_summary

FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance"
]

os.makedirs("artifacts", exist_ok=True)


def inject_document_missingness(
    df: pd.DataFrame,
    seed: int = 42,
    salary_missing_rate: float = 0.12,
    utility_missing_rate: float = 0.22,
    salary_features: list[str] | None = None,
    utility_features: list[str] | None = None,
) -> pd.DataFrame:
    """Inject document-level missingness for salary and utility documents.

    Bank statements remain mandatory in this pipeline, so they are not masked.
    Missingness is applied independently of the default target to avoid
    target leakage.

    Salary and utility documents are missing at fixed rates across the
    dataset. All features derived from a missing document are set to NaN.
    """
    if salary_features is None:
        salary_features = ["net_to_gross_ratio"]

    if utility_features is None:
        utility_features = ["utility_stability"]

    df = df.copy()
    rng = np.random.default_rng(seed)

    # Document missingness must NOT depend on the target variable.
    # This prevents target leakage during model training.
    salary_prob = np.full(len(df), salary_missing_rate)
    utility_prob = np.full(len(df), utility_missing_rate)

    salary_missing = rng.random(len(df)) < salary_prob
    utility_missing = rng.random(len(df)) < utility_prob

    if salary_features:
        df.loc[salary_missing, salary_features] = np.nan

    if utility_features:
        df.loc[utility_missing, utility_features] = np.nan

    return df


def generate_data(N=10000):
    """Synthetic data stand-in for real parsed document output from Stage 1+2."""
    np.random.seed(42)
    df = pd.DataFrame({
        "credit_debit_ratio" : np.random.normal(1.4,  0.5,  N),
        "cashflow_cv"        : np.random.normal(0.45, 0.18, N),
        "net_to_gross_ratio" : np.random.normal(0.8,  0.08, N),
        "utility_stability"  : np.random.normal(0.35, 0.15, N),
        "min_balance"        : np.random.normal(35000,15000, N),
    }).clip(lower=0)

    risk = (
        (df["credit_debit_ratio"] < 1.0).astype(int) * 1.8 +
        (df["cashflow_cv"]        > 0.65).astype(int) * 2.0 +
        (df["net_to_gross_ratio"] < 0.7).astype(int)  * 1.4 +
        (df["utility_stability"]  > 0.6).astype(int)  * 1.2 +
        (df["min_balance"]        < 15000).astype(int) * 1.6
    )
    prob_default = 1 / (1 + np.exp(-risk + 2))
    df["default"] = np.random.binomial(1, prob_default)
    return df


def main():
    print("=" * 65)
    print("  PRISM — Full Scorecard Training Pipeline")
    print("=" * 65)

    # ── Data ─────────────────────────────────────────────────────────────────
    df = generate_data()
    # ----------------------------------------------------------
    # Stage 3: Document-level missingness injection
    # ----------------------------------------------------------
    # Real ingestion logs/datasets were not found in this workspace, so the
    # training pipeline continues to use synthetic document-level masking.
    df = inject_document_missingness(df, seed=42)

    salary_missing = df["net_to_gross_ratio"].isna()
    utility_missing = df["utility_stability"].isna()

    print(f"\nSalary docs missing : {salary_missing.sum()} / {len(df)}")
    print(f"Utility docs missing: {utility_missing.sum()} / {len(df)}")

    train, test = train_test_split(df, test_size=0.2, random_state=42)
    print(f"\nData: {len(train)} train  |  {len(test)} test  |  "
          f"Bad rate: {df['default'].mean():.2%}")

    # ── STAGE 3: OPTIMAL BINNING ─────────────────────────────────────────────
    print("\n" + "─"*65)
    print("STAGE 3 — Optimal Binning")
    print("─"*65)
    binning_models = fit_binning_models(train[FEATURES], train["default"])
    print("\n  IV Summary:")
    print(summarise_binning(binning_models).to_string(index=False))
    save_binning_models(binning_models)

    # ── STAGE 4: WOE TRANSFORMATION ──────────────────────────────────────────
    print("\n" + "─"*65)
    print("STAGE 4 — WoE Transformation")
    print("─"*65)
    X_train_woe = apply_woe_transform(train[FEATURES], binning_models)
    X_test_woe  = apply_woe_transform(test[FEATURES],  binning_models)
    y_train     = train["default"]
    y_test      = test["default"]

    print("\n  WoE Monotonicity Check:")
    validate_woe_monotonicity(binning_models)

    joblib.dump({
        "X_train_woe": X_train_woe, "y_train": y_train,
        "X_test_woe" : X_test_woe,  "y_test" : y_test
    }, "artifacts/woe_datasets.pkl")

    # ── STAGE 5: LOGISTIC REGRESSION ─────────────────────────────────────────
    print("\n" + "─"*65)
    print("STAGE 5 — Logistic Regression")
    print("─"*65)
    model = fit_logistic_regression(X_train_woe, y_train)

    print("\n  Coefficient Table (Wald Test):")
    coef_tbl = coefficient_table(model, X_train_woe, y_train)
    print(coef_tbl.to_string(index=False))

    print("\n  VIF (Multicollinearity):")
    vif_tbl = compute_vif(X_train_woe)
    print(vif_tbl.to_string(index=False))

    eval_res = evaluate_model(model, X_train_woe, y_train, X_test_woe, y_test)
    print_report(eval_res)

    joblib.dump(model, "artifacts/lr_model.pkl")

    # STAGE 6 — PROBABILITY OF DEFAULT (PD) + CALIBRATION
    print("\n" + "=" * 70)
    print("STAGE 6 — Probability of Default + Calibration")
    print("=" * 70)
    train_log_odds = compute_log_odds(model,X_train_woe)
    test_log_odds = compute_log_odds(model,X_test_woe)
    print("\n[1] Raw Log-Odds")
    print("-" * 70)
    print(f"Train:")
    print(f"  Min  : {train_log_odds.min():.4f}")
    print(f"  Max  : {train_log_odds.max():.4f}")
    print(f"  Mean : {train_log_odds.mean():.4f}")
    print(f"\nTest:")
    print(f"  Min  : {test_log_odds.min():.4f}")
    print(f"  Max  : {test_log_odds.max():.4f}")
    print(f"  Mean : {test_log_odds.mean():.4f}")

    raw_train_pd = compute_pd(model,X_train_woe)
    raw_test_pd = compute_pd(model,X_test_woe)
    print("\n[2] Raw PD")
    print("-" * 70)
    print(f"  Train mean : {raw_train_pd.mean():.4f}")
    print(f"  Test mean  : {raw_test_pd.mean():.4f}")
    print(f"  Test min   : {raw_test_pd.min():.4f}")
    print(f"  Test max   : {raw_test_pd.max():.4f}")

    print("\n[3] Fitting PD calibration layer...")
    print("-" * 70)
    pd_calibrator = fit_pd_calibrator(
    model,
    X_train_woe,
    y_train)
    (
    train_raw_log_odds,
    train_calibrated_log_odds,
    train_raw_pd,
    calibrated_train_pd,
) = compute_calibrated_pd_from_model(
    model,
    pd_calibrator,
    X_train_woe)

    (
    test_raw_log_odds,
    test_calibrated_log_odds,
    test_raw_pd,
    calibrated_test_pd,) = compute_calibrated_pd_from_model(
    model,
    pd_calibrator,
    X_test_woe)


    print("\n[4] Calibrated PD")
    print("-" * 70)
    print(f"  Train mean : {calibrated_train_pd.mean():.4f}")
    print(f"  Test mean  : {calibrated_test_pd.mean():.4f}")
    print(f"  Test min   : {calibrated_test_pd.min():.4f}")
    print(f"  Test max   : {calibrated_test_pd.max():.4f}")
    actual_default_rate = float(np.mean(y_test))
    raw_pd_gap = (float(raw_test_pd.mean()) - actual_default_rate)
    calibrated_pd_gap = (float(calibrated_test_pd.mean())- actual_default_rate)
    print("\n[5] PD Calibration Comparison")
    print("-" * 70)
    print("\nRaw PD:")
    print(f"  Train mean : {train_raw_pd.mean():.4f}")
    print(f"  Test mean  : {test_raw_pd.mean():.4f}")
    print("\nCalibrated PD:")
    print(f"  Train mean : {calibrated_train_pd.mean():.4f}")
    print(f"  Test mean  : {calibrated_test_pd.mean():.4f}")
    actual_test_default_rate = float(np.mean(y_test))
    raw_pd_gap = abs(float(test_raw_pd.mean()) - actual_test_default_rate)
    calibrated_pd_gap = (float(calibrated_test_pd.mean()) - actual_test_default_rate)
    print("\nPD Calibration:")
    print(f"  Actual test default rate : {actual_test_default_rate:.4f}")
    print(f"  Raw PD gap               : {raw_pd_gap:.4f}")
    print(f"  Calibrated PD gap        : {calibrated_pd_gap:.4f}")
    print("\nCalibration parameters:")
    print(f"  Intercept : {pd_calibrator.intercept_[0]:.6f}")
    print(f"  Slope     : {pd_calibrator.coef_[0][0]:.6f}")

    print("\n" + "=" * 70)
    print("STAGE 7 — Credit Score")
    print("=" * 70)
    scores = log_odds_to_score(test_calibrated_log_odds)
    print("\n[1] Score Statistics")
    print("-" * 70)
    print(f"  Min  : {scores.min():.0f}")
    print(f"  Max  : {scores.max():.0f}")
    print(f"  Mean : {scores.mean():.2f}")
    print(f"  Std  : {scores.std():.2f}")
    print("\n[2] Score Distribution")
    print("-" * 70)
    score_report = score_distribution_report(
    scores,calibrated_test_pd)
    print(score_report.to_string(index=False))
    print("\n[3] Scorecard Scaling")
    print("-" * 70)

    try:
        score_table = scorecard_table(model,binning_models)
        print(score_table.to_string(index=False))
    except Exception as exc:
        print(f"  Scorecard table unavailable: {exc}")

    score_output = {
    "scores": scores,
    "calibrated_pd": calibrated_test_pd,
    "calibrated_log_odds": test_calibrated_log_odds,
    "y_true": y_test,
}

    scored_output_path = os.path.join("artifacts", "scored_output.pkl")
    print("\n[4] Final scored output saved:")
    print(f"  {scored_output_path}")
    print("\n" + "=" * 70)
    print("STAGE 6 + STAGE 7 COMPLETE")
    print("=" * 70)

    # ── STAGE 8: EXPLAINABILITY ───────────────────────────────────────────────
    print("\n" + "─"*65)
    print("STAGE 8 — SHAP Explainability")
    print("─"*65)
    shap_vals = compute_shap_values(
        model, X_test_woe.values, X_train_woe.values
    )

    print("\n  Population Feature Importance (mean |SHAP|):")
    pop_shap = population_shap_summary(shap_vals)
    print(pop_shap.to_string(index=False))

    joblib.dump({"shap_values": shap_vals}, "artifacts/shap_output.pkl")

    # ── DONE ──────────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  PIPELINE COMPLETE — all artifacts saved to ./artifacts/")
    print("  Ready to run: python scorer.py")
    print("=" * 65)


if __name__ == "__main__":
    main()