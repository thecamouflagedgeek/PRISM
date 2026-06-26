"""
PRISM — Stage 4: Weight of Evidence (WoE) Transformation
==========================================================
Literature basis:
    Siddiqi (2006) — Credit Risk Scorecards, Chapter 7
    Anderson (2007) — The Credit Scoring Toolkit

Formula:
    WoE_i = ln( P(Events in bin i) / P(Non-Events in bin i) )
           = ln( (n_bad_i / N_bad) / (n_good_i / N_good) )

Why WoE transformation before Logistic Regression:
    1. Normalises all features to a common scale, improving LR stability.
    2. Automatically handles non-linear relationships between features and
       the log-odds of default.
    3. Makes the LR model inherently interpretable — each coefficient acts
       on a comparable WoE scale.
    4. Missing values map to a designated "Special" bin with its own WoE,
       rather than requiring imputation.

Key literature constraint:
    WoE values MUST be monotonic across ordered bins. Non-monotonic WoE
    suggests the binning is capturing noise rather than a real risk gradient.
    This is enforced in Stage 3 via monotonic_trend="auto".
"""

import pandas as pd
import numpy as np
import joblib
from typing import Dict


FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance"
]


def apply_woe_transform(
    X: pd.DataFrame,
    binning_models: dict,
    features: list = FEATURES
) -> pd.DataFrame:
    """
    Transform raw feature values into WoE values using fitted binning models.

    Parameters
    ----------
    X              : DataFrame with raw feature columns
    binning_models : dict of {feature_name -> fitted OptimalBinning}
    features       : ordered list of features to transform

    Returns
    -------
    X_woe : DataFrame with same columns, now WoE-encoded
    """
    X_woe = pd.DataFrame(index=X.index)

    for col in features:
        ob = binning_models[col]
        X_woe[col] = ob.transform(X[col].values, metric="woe")

    return X_woe


def woe_for_single_record(
    record: dict,
    binning_models: dict,
    features: list = FEATURES
) -> np.ndarray:
    """
    Transform a single borrower's raw features into a WoE vector.
    Used at inference time in the FastAPI /assess endpoint.

    Parameters
    ----------
    record         : dict of {feature_name -> raw_value}
                     Missing features default to 0.0 (neutral WoE assumption)
    binning_models : fitted binning models from Stage 3
    features       : ordered feature list (must match LR model column order)

    Returns
    -------
    woe_vector : np.ndarray of shape (1, n_features)
    """
    woe_values = []

    for col in features:
        raw_val = record.get(col)

        if raw_val is None or (isinstance(raw_val, float) and np.isnan(raw_val)):
            # Literature approach: missing → Special bin WoE from OptimalBinning
            # Fallback: 0.0 (neutral, log-odds contribution = 0)
            woe_val = 0.0
        else:
            woe_val = binning_models[col].transform(
                np.array([raw_val]), metric="woe"
            )[0]

        woe_values.append(woe_val)

    return np.array(woe_values).reshape(1, -1)


def build_woe_reference_table(binning_models: dict) -> pd.DataFrame:
    """
    Build a human-readable WoE reference table for ALL features combined.
    This is what goes into the model documentation / scorecard audit pack.

    Per Basel II IRB requirements, every bin boundary and its WoE value
    must be documented and signed off before production deployment.
    """
    rows = []

    for col, ob in binning_models.items():
        table = ob.binning_table.build()

        # Drop the Totals row
        table = table[table["Bin"] != "Totals"]

        for _, row in table.iterrows():
            rows.append({
                "feature"   : col,
                "bin"       : row["Bin"],
                "n_events"  : row.get("Event", row.get("Count_1", 0)),
                "n_nonevents": row.get("Non-event", row.get("Count_0", 0)),
                "woe"       : round(row["WoE"], 4),
                "iv"        : round(row["IV"],  4),
            })

    return pd.DataFrame(rows)


def validate_woe_monotonicity(binning_models: dict) -> Dict[str, bool]:
    """
    Post-fit check: verify WoE is monotone across bins for each feature.
    Returns {feature: True if monotone, False if not}.
    A non-monotone feature should be investigated or dropped.
    """
    results = {}

    for col, ob in binning_models.items():
        table = ob.binning_table.build()
        table = table[table["Bin"] != "Totals"]
        woe_vals = table["WoE"].values

        increasing = all(woe_vals[i] <= woe_vals[i+1] for i in range(len(woe_vals)-1))
        decreasing = all(woe_vals[i] >= woe_vals[i+1] for i in range(len(woe_vals)-1))

        is_monotone = increasing or decreasing
        results[col] = is_monotone

        status = "✓ monotone" if is_monotone else "✗ NOT monotone — review binning"
        print(f"  {col:30s}: {status}")

    return results


# ── STANDALONE RUN ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(__file__))

    from sklearn.model_selection import train_test_split

    # Load binning models from Stage 3
    binning_models = joblib.load("artifacts/binning_models.pkl")

    # Recreate data
    np.random.seed(42)
    N = 10000
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

    train, test = train_test_split(df, test_size=0.2, random_state=42)

    print("Stage 4 — Applying WoE transformation...")
    X_train_woe = apply_woe_transform(train[FEATURES], binning_models)
    X_test_woe  = apply_woe_transform(test[FEATURES],  binning_models)

    print("\nStage 4 — WoE-transformed training set (first 5 rows):")
    print(X_train_woe.head().to_string())

    print("\nStage 4 — Checking WoE monotonicity:")
    validate_woe_monotonicity(binning_models)

    print("\nStage 4 — WoE Reference Table (for audit documentation):")
    ref_table = build_woe_reference_table(binning_models)
    print(ref_table.to_string(index=False))

    # Save for Stage 5
    joblib.dump({"X_train_woe": X_train_woe,
                 "y_train"    : train["default"],
                 "X_test_woe" : X_test_woe,
                 "y_test"     : test["default"]},
                "artifacts/woe_datasets.pkl")

    print("\nStage 4 complete.")