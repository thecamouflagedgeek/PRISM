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
from .pod import compute_pd, compute_log_odds, pd_validation_report
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
    Missingness is applied at the document level by setting all features derived
    from a missing salary/utility document to NaN together.
    """
    if salary_features is None:
        salary_features = ["net_to_gross_ratio"]
    if utility_features is None:
        utility_features = ["utility_stability"]

    df = df.copy()
    rng = np.random.default_rng(seed)

    if "default" in df.columns:
        default_mask = df["default"].astype(int).to_numpy()
        salary_prob = np.where(
            default_mask == 1,
            np.clip(salary_missing_rate + 0.08, 0.0, 1.0),
            np.clip(salary_missing_rate - 0.03, 0.0, 1.0),
        )
        utility_prob = np.where(
            default_mask == 1,
            np.clip(utility_missing_rate + 0.08, 0.0, 1.0),
            np.clip(utility_missing_rate - 0.03, 0.0, 1.0),
        )
    else:
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

    # ── STAGE 6: PROBABILITY OF DEFAULT ──────────────────────────────────────
    print("\n" + "─"*65)
    print("STAGE 6 — Probability of Default")
    print("─"*65)
    log_odds_test = compute_log_odds(model, X_test_woe.values)
    pd_test       = compute_pd(model, X_test_woe.values)

    print(f"\n  PD stats  →  mean: {pd_test.mean():.4f}  "
          f"min: {pd_test.min():.4f}  max: {pd_test.max():.4f}")

    print("\n  PD Calibration Report:")
    cal = pd_validation_report(y_test.values, pd_test)
    print(cal.to_string(index=False))

    joblib.dump({"log_odds": log_odds_test, "pd_values": pd_test},
                "artifacts/pd_output.pkl")

    # ── STAGE 7: SCORE SCALING ────────────────────────────────────────────────
    print("\n" + "─"*65)
    print("STAGE 7 — PDO Score Scaling")
    print("─"*65)
    scores = log_odds_to_score(log_odds_test)

    print(f"\n  Score stats  →  mean: {scores.mean():.1f}  "
          f"min: {scores.min()}  max: {scores.max()}")

    print("\n  Score Band Distribution:")
    band_rep = score_distribution_report(scores, pd_test)
    print(band_rep.to_string(index=False))

    print("\n  Full Scorecard Table:")
    sc_tbl = scorecard_table(model, binning_models)
    print(sc_tbl.to_string(index=False))

    joblib.dump({
        "scores": scores, "pd_values": pd_test,
        "log_odds": log_odds_test, "X_test_woe": X_test_woe.values
    }, "artifacts/scored_output.pkl")

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