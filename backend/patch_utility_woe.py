"""
patch_utility_woe.py  (final)
Run from backend/:  python patch_utility_woe.py
"""

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

ARTIFACTS = "scoring/artifacts"
FEATURES  = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]

# ── 1. Load ───────────────────────────────────────────────────────────────────
binning      = joblib.load(f"{ARTIFACTS}/binning.pkl")
woe_datasets = joblib.load(f"{ARTIFACTS}/woe_datasets.pkl")
b            = binning["utility_stability"]
bt           = b.binning_table

# ── 2. Show current _woe array ───────────────────────────────────────────────
print("_woe array (one value per bin row incl. Special/Missing):")
print(bt._woe)
print(f"Length: {len(bt._woe)}")

df_table = bt.build()
print("\nBEFORE patch:")
print(df_table[["Bin", "Count", "Event rate", "WoE"]])

# ── 3. Patch _woe ─────────────────────────────────────────────────────────────
# From the binning table:
#   index 0  (-inf, 0.23)  WoE = -0.0718
#   index 1  [0.23, 0.26)  WoE = +0.3880
#   index 2  [0.26, 0.29)  WoE = +0.1825
#   index 3  [0.29, 0.53)  WoE = +0.0485
#   index 4  [0.53, 0.59)  WoE = -0.0902  ← mild inversion, patch to +0.05
#   index 5  [0.59, inf)   WoE = -0.7139  ← strong inversion, patch to +0.15
#   index 6  Special       WoE =  0.0     ← leave
#   index 7  Missing       WoE =  0.0     ← leave
#
# Corrected values enforce monotonic: higher stability → lower event rate → higher WoE
# We only fix the two violating bins (4 and 5).

CORRECTED = {
    4: 0.05,   # [0.53, 0.59)  was -0.090
    5: 0.15,   # [0.59, inf)   was -0.714
}

for idx, new_woe in CORRECTED.items():
    old = bt._woe[idx]
    bt._woe[idx] = new_woe
    print(f"\nPatched bin {idx}: WoE {old:.4f} → {new_woe:.4f}")

# Also patch _iv_values to stay consistent (set to 0 for patched bins —
# IV recalculation requires event counts which we don't recompute here)
if hasattr(bt, '_iv_values') and bt._iv_values is not None:
    for idx in CORRECTED:
        if idx < len(bt._iv_values):
            bt._iv_values[idx] = 0.0

print("\nAFTER patch:")
df_after = bt.build()
print(df_after[["Bin", "Count", "Event rate", "WoE"]])

# ── 4. Sanity check: transform test values ────────────────────────────────────
print("\nWoE transform sanity check:")
test_vals = [0.1, 0.25, 0.40, 0.55, 0.70, 0.95]
for v in test_vals:
    woe = b.transform([v], metric="woe")[0]
    print(f"  utility_stability={v:.2f}  →  WoE={woe:+.4f}")

# ── 5. Save patched binning ───────────────────────────────────────────────────
binning["utility_stability"] = b
joblib.dump(binning, f"{ARTIFACTS}/binning.pkl")
print(f"\nSaved patched binning → {ARTIFACTS}/binning.pkl")

# ── 6. Retrain LR on corrected WoE dataset ───────────────────────────────────
print("\n=== RETRAINING LOGISTIC REGRESSION ===")
print(f"woe_datasets type: {type(woe_datasets)}")

if isinstance(woe_datasets, dict):
    print(f"Keys: {list(woe_datasets.keys())}")

# Detect structure
X_train = y_train = X_test = y_test = None

if isinstance(woe_datasets, dict):
    # Try common key patterns
    for xk in ("X_train", "train_X", "train", "X"):
        if xk in woe_datasets:
            X_train = woe_datasets[xk]
            break
    for yk in ("y_train", "train_y", "y", "target"):
        if yk in woe_datasets:
            y_train = woe_datasets[yk]
            break
    for xk in ("X_test", "test_X", "test"):
        if xk in woe_datasets:
            X_test = woe_datasets[xk]
            break
    for yk in ("y_test", "test_y"):
        if yk in woe_datasets:
            y_test = woe_datasets[yk]
            break

elif isinstance(woe_datasets, pd.DataFrame):
    # Single DataFrame — last column is probably target
    if "target" in woe_datasets.columns:
        y_train = woe_datasets["target"]
        X_train = woe_datasets[FEATURES]
    elif "default" in woe_datasets.columns:
        y_train = woe_datasets["default"]
        X_train = woe_datasets[FEATURES]
    else:
        # Assume last column is target
        y_train = woe_datasets.iloc[:, -1]
        X_train = woe_datasets[FEATURES]

if X_train is None:
    print("Could not detect X_train from woe_datasets.")
    print("Keys/columns:", list(woe_datasets.keys()) if isinstance(woe_datasets, dict) else list(woe_datasets.columns))
    print("Skipping retrain. Patched binning saved — restart uvicorn.")
else:
    # Re-transform utility_stability with patched binning
    if isinstance(X_train, pd.DataFrame) and "utility_stability" in X_train.columns:
        # The WoE dataset already has WoE values — we need original feature values.
        # Check if values look like WoE (small floats) or raw features (0-1 range for utility)
        sample = X_train["utility_stability"].dropna().head(20).values
        looks_like_woe = np.all(np.abs(sample) < 3.0) and np.any(sample < 0)
        print(f"\nX_train utility_stability sample: {sample[:5]}")
        print(f"Looks like WoE values already: {looks_like_woe}")

        if looks_like_woe:
            # Dataset already contains WoE — patch the stored WoE values directly
            # Map old WoE → new WoE for the two patched bins
            woe_map = {-0.090244: 0.05, -0.713887: 0.15}
            patched_col = X_train["utility_stability"].copy()
            for old_woe, new_woe in woe_map.items():
                mask = np.isclose(patched_col, old_woe, atol=1e-4)
                n_replaced = mask.sum()
                patched_col[mask] = new_woe
                print(f"  Replaced {n_replaced} rows: WoE {old_woe:.4f} → {new_woe:.4f}")
            X_train = X_train.copy()
            X_train["utility_stability"] = patched_col

            if X_test is not None and "utility_stability" in X_test.columns:
                patched_test = X_test["utility_stability"].copy()
                for old_woe, new_woe in woe_map.items():
                    mask = np.isclose(patched_test, old_woe, atol=1e-4)
                    patched_test[mask] = new_woe
                X_test = X_test.copy()
                X_test["utility_stability"] = patched_test

    # Fit LR
    X_fit = X_train[FEATURES] if isinstance(X_train, pd.DataFrame) else X_train
    lr = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        max_iter=1000,
        random_state=42,
    )
    lr.fit(X_fit, y_train)

    print("\nRetrained LR coefficients:")
    for feat, coef in zip(FEATURES, lr.coef_[0]):
        direction = "✓" if coef < 0 else "✗ WARNING: positive coef"
        print(f"  {feat:30s}  {coef:+.4f}  {direction}")

    print(f"\nIntercept: {lr.intercept_[0]:+.4f}")

    # Save
    joblib.dump(lr, f"{ARTIFACTS}/lr_model.pkl")
    print(f"Saved retrained model → {ARTIFACTS}/lr_model.pkl")

# ── 7. Final end-to-end test ──────────────────────────────────────────────────
print("\n=== END-TO-END SCORE TEST ===")
import importlib, sys

# Force reload scoring module so it picks up new artifacts
for mod in list(sys.modules.keys()):
    if "risk_scorer" in mod or "scoring_engine" in mod:
        del sys.modules[mod]

from scoring.risk_scorer import compute_risk_score

tests = [
    ("Distressed (your test PDF)",
     {"credit_debit_ratio": 0.857, "cashflow_cv": 0.265, "min_balance_l3m": 81.01},
     {"net_to_gross_ratio": 0.828},
     {"utility_stability": 0.70}),
    ("Good applicant",
     {"credit_debit_ratio": 3.0,  "cashflow_cv": 0.15,  "min_balance_l3m": 25000},
     {"net_to_gross_ratio": 0.85},
     {"utility_stability": 0.80}),
    ("Excellent applicant",
     {"credit_debit_ratio": 5.0,  "cashflow_cv": 0.05,  "min_balance_l3m": 50000},
     {"net_to_gross_ratio": 0.88},
     {"utility_stability": 0.95}),
]

for label, bank, salary, utility in tests:
    r = compute_risk_score(bank, salary, utility)
    print(f"\n  {label}")
    print(f"    Score: {r['risk_score']}  PD: {r['probability_of_default']:.4f}  Tier: {r['risk_tier']}")

print("\nDone. Restart uvicorn to serve updated artifacts.")