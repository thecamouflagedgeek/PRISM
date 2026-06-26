"""
Optimal Binning + WoE Transformation Module
Siddiqi (2006) + Thomas et al. (2002) aligned implementation

Key Features:
- Supervised monotonic binning using OptBinning
- Information Value (IV) evaluation
- WoE transformation pipeline
- Reject inference ready hooks
- Production-safe serialization
"""

import os
import numpy as np
import pandas as pd
import joblib
from optbinning import OptimalBinning


# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

DEFAULT_FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance"
]

MIN_BIN_SIZE = 0.05
MAX_N_BINS = 6
IV_DROP_THRESHOLD = 0.02


# ─────────────────────────────────────────────────────────────
# FIT BINNING MODELS
# ─────────────────────────────────────────────────────────────

def fit_binning_models(
    X: pd.DataFrame,
    y: pd.Series,
    features: list = DEFAULT_FEATURES,
    monotonic: str = "auto"
) -> dict:
    """
    Fit OptimalBinning models per feature.

    Returns:
        dict: feature -> fitted OptimalBinning object
    """

    binning_models = {}

    for col in features:
        if col not in X.columns:
            raise ValueError(f"Feature {col} not found in input data")

        ob = OptimalBinning(
            name=col,
            dtype="numerical",
            min_bin_size=MIN_BIN_SIZE,
            max_n_bins=MAX_N_BINS,
            monotonic_trend=monotonic
        )

        ob.fit(X[col].values, y.values)

        iv = ob.binning_table.build()["IV"].sum()

        if iv < IV_DROP_THRESHOLD:
            print(f"[WARN] {col}: IV={iv:.4f} (weak predictor)")

        binning_models[col] = ob

    return binning_models


# ─────────────────────────────────────────────────────────────
# WOE TRANSFORMER (PRODUCTION CORE)
# ─────────────────────────────────────────────────────────────

class WOETransformer:
    """
    Converts raw features → WoE encoded features using fitted binning models.
    """

    def __init__(self, binning_models: dict):
        self.models = binning_models

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X_woe = pd.DataFrame(index=X.index)

        for col, model in self.models.items():
            X_woe[col + "_woe"] = model.transform(X[col].values, metric="woe")

        return X_woe

    def fit_transform(self, X: pd.DataFrame, y: pd.Series):
        raise NotImplementedError("Fit handled externally via fit_binning_models")


# ─────────────────────────────────────────────────────────────
# SUMMARY (SIDDQI STYLE IV REPORT)
# ─────────────────────────────────────────────────────────────

def summarise_binning(binning_models: dict) -> pd.DataFrame:
    """
    IV interpretation per Siddiqi (2006)
    """

    rows = []

    for col, model in binning_models.items():
        table = model.binning_table.build()
        iv = table["IV"].sum()

        n_bins = len(table) - 2  # exclude special + total

        if iv < 0.02:
            strength = "Useless"
        elif iv < 0.1:
            strength = "Weak"
        elif iv < 0.3:
            strength = "Medium"
        else:
            strength = "Strong"

        rows.append({
            "feature": col,
            "iv": round(iv, 4),
            "n_bins": n_bins,
            "strength": strength
        })

    return pd.DataFrame(rows).sort_values("iv", ascending=False)


# ─────────────────────────────────────────────────────────────
# REJECT INFERENCE HOOK (CONTROLLED FRAMEWORK)
# ─────────────────────────────────────────────────────────────

def augment_with_reject_inference(
    X_labeled: pd.DataFrame,
    y_labeled: pd.Series,
    X_unlabeled: pd.DataFrame,
    strategy: str = "parceling"
):
    """
    Placeholder for reject inference strategies.

    Supported (extendable):
    - parceling
    - fuzzy labeling
    - augmentation via score distribution

    Returns:
        augmented X, y
    """

    if X_unlabeled is None or len(X_unlabeled) == 0:
        return X_labeled, y_labeled

    if strategy == "parceling":
        # simple conservative assumption: assign probabilistic labels later
        X_aug = pd.concat([X_labeled, X_unlabeled], axis=0)
        y_aug = pd.concat([y_labeled, pd.Series([-1] * len(X_unlabeled))], axis=0)

        return X_aug, y_aug

    raise ValueError(f"Unknown reject inference strategy: {strategy}")


# ─────────────────────────────────────────────────────────────
# SAVE / LOAD
# ─────────────────────────────────────────────────────────────

def save_binning_models(models: dict, path: str = "artifacts/binning.pkl"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(models, path)


def load_binning_models(path: str = "artifacts/binning.pkl") -> dict:
    return joblib.load(path)


# ─────────────────────────────────────────────────────────────
# FULL PIPELINE HELPERS
# ─────────────────────────────────────────────────────────────

def build_scorecard_features(
    X: pd.DataFrame,
    y: pd.Series,
    features: list = DEFAULT_FEATURES
):
    """
    End-to-end binning + WoE pipeline
    """

    models = fit_binning_models(X, y, features)
    woe = WOETransformer(models)
    X_woe = woe.transform(X)

    return models, X_woe


# ─────────────────────────────────────────────────────────────
# OPTIONAL DEBUG RUN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from sklearn.model_selection import train_test_split

    np.random.seed(42)
    n = 5000

    df = pd.DataFrame({
        "credit_debit_ratio": np.random.normal(1.4, 0.5, n),
        "cashflow_cv": np.random.normal(0.45, 0.18, n),
        "net_to_gross_ratio": np.random.normal(0.8, 0.08, n),
        "utility_stability": np.random.normal(0.35, 0.15, n),
        "min_balance": np.random.normal(35000, 15000, n),
    }).clip(lower=0)

    risk = (
        (df["credit_debit_ratio"] < 1.0).astype(int) * 1.8 +
        (df["cashflow_cv"] > 0.65).astype(int) * 2.0 +
        (df["net_to_gross_ratio"] < 0.7).astype(int) * 1.4 +
        (df["utility_stability"] > 0.6).astype(int) * 1.2 +
        (df["min_balance"] < 15000).astype(int) * 1.6
    )

    prob = 1 / (1 + np.exp(-risk + 2))
    df["default"] = np.random.binomial(1, prob)

    train, test = train_test_split(df, test_size=0.2)

    models, X_woe = build_scorecard_features(
        train[DEFAULT_FEATURES],
        train["default"]
    )

    print(summarise_binning(models))