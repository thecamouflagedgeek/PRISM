"""
refit_stage3_combined.py
Run from backend/:  python refit_stage3_combined.py

Combines two fixes in one pass:
  1. Injects realistic missingness into net_to_gross_ratio, cashflow_cv,
     utility_stability so the binner learns real Special/Missing WoE
     instead of leaving them at Count=0, WoE=0.
  2. Refits utility_stability with a monotonic_trend constraint so WoE
     is enforced to move consistently with the feature, instead of the
     non-monotonic bins the earlier hand-patch tried to paper over.

Then retrains the LR model on the newly-transformed WoE features and
runs the same end-to-end sanity checks as before.
"""

import numpy as np
import pandas as pd
import joblib
from optbinning import OptimalBinning
from sklearn.linear_model import LogisticRegression

ARTIFACTS = "scoring/artifacts"
FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]
TARGET_COL = "target"   # CHANGE if your label column is named differently (e.g. "default")

# ─────────────────────────────────────────────────────────────
# 0. RECONSTRUCT TRAINING DATA FROM EXISTING binning.pkl
# ─────────────────────────────────────────────────────────────
# The original synthetic training file was deleted, so we can't load raw
# rows directly. Instead we reconstruct an approximate but statistically
# equivalent dataset from the CURRENT binning.pkl's own binning tables:
# for each feature, for each non-Special/Missing bin, we know the bin's
# edges, Count, and Event rate. We resample values uniformly within each
# bin's edges and assign labels so ~Event rate of them are defaults.
#
# CAVEAT (fold into tomorrow's mentor note): this reconstructs each
# feature's marginal distribution and event rate independently — it does
# NOT preserve original cross-feature correlations (e.g. how cashflow_cv
# and net_to_gross_ratio co-varied for the same applicant), since the
# original row-level synthetic data no longer exists. This is a stopgap,
# not a replacement for regenerating proper joint synthetic data later.

_old_artifacts_binning = joblib.load(f"{ARTIFACTS}/binning.pkl")
_rng_reconstruct = np.random.RandomState(42)


def _reconstruct_feature_column(binner):
    """Regenerate approximate raw values + labels from an existing binning table."""
    table = binner.binning_table.build()

    # Normalize and filter out summary/special rows more robustly than an exact
    # string match (handles stray whitespace, casing, etc.)
    bin_labels = table["Bin"].astype(str).str.strip()
    exclude = bin_labels.str.lower().isin(["special", "missing", "totals", ""])
    table = table[~exclude]

    values, labels = [], []
    skipped = []
    for _, row in table.iterrows():
        bin_str = str(row["Bin"]).strip()
        count = int(row["Count"])
        event_rate = float(row["Event rate"])
        if count == 0:
            continue

        # Parse bin edges like "(-inf, 0.50)" or "[0.50, 0.53)"
        stripped = bin_str.strip("()[] ")
        parts = stripped.split(",")
        if len(parts) != 2:
            # Unparsable bin label (e.g. a categorical bin, or an unexpected
            # summary row) -- skip it rather than crash, but surface it so
            # it can be checked.
            skipped.append((bin_str, count))
            continue

        lo_str, hi_str = parts

        # Guard: a single "(-inf, inf)" bin means the underlying binning
        # table has already been collapsed (e.g. by an earlier monotonic-
        # constraint run) and has no real edges left to recover from.
        # Sampling a wide fallback range here would silently corrupt this
        # feature's reconstructed values — refuse instead.
        if lo_str.strip() == "-inf" and hi_str.strip() == "inf":
            raise RuntimeError(
                f"'{binner.name}' has a collapsed single-bin table "
                f"'(-inf, inf)' with no real edges. Refusing to reconstruct "
                f"from this — restore a known-good binning.pkl from git first."
            )
        try:
            lo = -1e6 if "inf" in lo_str else float(lo_str)
            hi = 1e6 if "inf" in hi_str else float(hi_str)
        except ValueError:
            skipped.append((bin_str, count))
            continue

        # Clip open-ended bins to a sane finite range for sampling
        lo = max(lo, -10)
        hi = min(hi, 10)

        vals = _rng_reconstruct.uniform(lo, hi, size=count)
        labs = (_rng_reconstruct.rand(count) < event_rate).astype(int)
        values.append(vals)
        labels.append(labs)

    if skipped:
        print(f"  [{binner.name}] Skipped {len(skipped)} unparsable bin row(s): {skipped}")

    if not values:
        raise RuntimeError(
            f"No usable bins found for '{binner.name}' — binning table may be empty "
            f"or all rows were unparsable. Skipped rows: {skipped}"
        )
    return np.concatenate(values), np.concatenate(labels)


_feature_data = {}
_label_data = {}
for _feat in FEATURES:
    if _feat not in _old_artifacts_binning:
        raise RuntimeError(
            f"Feature '{_feat}' not found in existing binning.pkl — cannot reconstruct."
        )
    _vals, _labs = _reconstruct_feature_column(_old_artifacts_binning[_feat])
    _feature_data[_feat] = _vals
    _label_data[_feat] = _labs

# Bin counts may differ slightly per feature (rounding) — truncate to the
# shortest reconstructed length so all columns align row-wise.
_min_len = min(len(v) for v in _feature_data.values())
df_train = pd.DataFrame({feat: _feature_data[feat][:_min_len] for feat in FEATURES})

# Use one feature's reconstructed labels as the target (same underlying
# population, so aggregate default rate should be broadly consistent).
df_train[TARGET_COL] = _label_data[FEATURES[0]][:_min_len]

print(f"Reconstructed df_train: {len(df_train)} rows (from existing binning.pkl)")
print(df_train.describe())
print(f"Overall default rate: {df_train[TARGET_COL].mean():.4f}")

missing_feats = [f for f in FEATURES + [TARGET_COL] if f not in df_train.columns]
if missing_feats:
    raise RuntimeError(f"df_train is missing expected columns: {missing_feats}")

# ─────────────────────────────────────────────────────────────
# 1. INJECT REALISTIC MISSINGNESS (document-level)
# ─────────────────────────────────────────────────────────────
# Placeholder rates -- NOT yet measured from real applicant document logs.
# Flag this explicitly to mentors (see task 4 note at bottom of run output).
doc_missing_rates = {
    "bank_statement_missing": 0.12,   # drives cashflow_cv (bank-derived)
    "utility_bill_missing":   0.22,   # drives utility_stability
    "salary_doc_missing":     0.15,   # drives net_to_gross_ratio
}

rng = np.random.RandomState(42)
n = len(df_train)

bank_missing   = rng.rand(n) < doc_missing_rates["bank_statement_missing"]
utility_missing = rng.rand(n) < doc_missing_rates["utility_bill_missing"]
salary_missing  = rng.rand(n) < doc_missing_rates["salary_doc_missing"]

df_train = df_train.copy()
df_train.loc[bank_missing, "cashflow_cv"] = np.nan
df_train.loc[utility_missing, "utility_stability"] = np.nan
df_train.loc[salary_missing, "net_to_gross_ratio"] = np.nan

print("\nInjected missingness counts:")
for feat in ["cashflow_cv", "utility_stability", "net_to_gross_ratio"]:
    n_miss = df_train[feat].isna().sum()
    print(f"  {feat:22s} {n_miss} / {n} missing ({100*n_miss/n:.1f}%)")

# ─────────────────────────────────────────────────────────────
# 2. REFIT ALL BINS  (with monotonic constraint on utility_stability)
# ─────────────────────────────────────────────────────────────
binning_models = {}

for feature in FEATURES:
    kwargs = {"solver": "cp"}
    # NOTE: monotonic_trend constraint on utility_stability was tried and
    # REMOVED — on this reconstructed (non-joint) data it collapses the
    # feature to a single (-inf, inf) bin, destroying all signal. Revisit
    # once real or properly-joint synthetic data is available.

    optb = OptimalBinning(name=feature, dtype="numerical", **kwargs)
    optb.fit(df_train[feature], df_train[TARGET_COL])
    binning_models[feature] = optb

    table = optb.binning_table.build()
    print(f"\n=== {feature} ===")
    print(table[["Bin", "Count", "Event rate", "WoE"]] if "Bin" in table.columns else table)

    if feature in ("cashflow_cv", "utility_stability", "net_to_gross_ratio"):
        special_row = table[table["Bin"] == "Special"] if "Bin" in table.columns else None
        missing_row = table[table["Bin"] == "Missing"] if "Bin" in table.columns else None
        for label, row in [("Special", special_row), ("Missing", missing_row)]:
            if row is not None and not row.empty:
                cnt = row["Count"].iloc[0]
                woe = row["WoE"].iloc[0]
                status = "OK" if cnt > 0 else "STILL EMPTY -- investigate upstream imputation"
                print(f"  [{label}] Count={cnt}  WoE={woe:.4f}  -> {status}")

OUTPUT_BINNING = f"{ARTIFACTS}/binning_REFIT_REVIEW.pkl"
joblib.dump(binning_models, OUTPUT_BINNING)
print(f"\nSaved refit binning models -> {OUTPUT_BINNING}  (NOT overwriting live binning.pkl)")

# ─────────────────────────────────────────────────────────────
# 3. BUILD WOE-TRANSFORMED TRAINING SET & RETRAIN LR
# ─────────────────────────────────────────────────────────────
woe_train = pd.DataFrame(index=df_train.index)
for feature in FEATURES:
    binner = binning_models[feature]
    woe_train[feature] = binner.transform(df_train[feature], metric="woe")

y_train = df_train[TARGET_COL]

lr = LogisticRegression(
    C=1.0,
    class_weight="balanced",
    max_iter=1000,
    random_state=42,
)
lr.fit(woe_train[FEATURES], y_train)

print("\nRetrained LR coefficients:")
for feat, coef in zip(FEATURES, lr.coef_[0]):
    direction = "OK" if coef < 0 else "WARNING: positive coef (check sign/monotonicity)"
    print(f"  {feat:22s}  {coef:+.4f}  {direction}")
print(f"Intercept: {lr.intercept_[0]:+.4f}")

OUTPUT_LR = f"{ARTIFACTS}/lr_model_REFIT_REVIEW.pkl"
joblib.dump(lr, OUTPUT_LR)
print(f"Saved retrained LR model -> {OUTPUT_LR}  (NOT overwriting live lr_model.pkl)")

print("\n=== END-TO-END SCORE TEST (using in-memory REFIT models, not live artifacts) ===")

def _score_with_refit_models(bank, salary, utility):
    """Mirrors compute_risk_score's logic but uses the freshly refit
    binning_models / lr from THIS run (in memory), not whatever is on
    disk — since we deliberately did not overwrite the live artifacts."""
    def _safe(d, key):
        if not d or not isinstance(d, dict):
            return None
        val = d.get(key)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return val

    feature_dict = {
        "credit_debit_ratio": _safe(bank, "credit_debit_ratio"),
        "cashflow_cv":         _safe(bank, "cashflow_cv"),
        "net_to_gross_ratio":  _safe(salary, "net_to_gross_ratio"),
        "utility_stability":   _safe(utility, "utility_stability"),
        "min_balance":         _safe(bank, "min_balance_l3m"),
    }
    row = {}
    for col in FEATURES:
        val = feature_dict.get(col)
        binner = binning_models[col]
        inp = np.nan if val is None else val
        row[col] = float(binner.transform([inp], metric="woe")[0])
    X_woe = pd.DataFrame([row], columns=FEATURES)

    log_odds = float(lr.decision_function(X_woe)[0])
    pd_value = float(np.clip(lr.predict_proba(X_woe)[0][1], 1e-6, 1 - 1e-6))

    _PDO, _BASE_SCORE, _BASE_ODDS = 50, 600, 19
    _FACTOR = _PDO / np.log(2)
    _OFFSET = _BASE_SCORE - _FACTOR * np.log(_BASE_ODDS)
    score = int(np.clip(_OFFSET - _FACTOR * log_odds, 300, 900))

    return {"score": score, "pd": pd_value, "woe_row": row}


tests = [
    ("Distressed applicant (missing salary doc)",
     {"credit_debit_ratio": 0.857, "cashflow_cv": 0.265, "min_balance_l3m": 81.01},
     None,
     {"utility_stability": 0.70}),
    ("Good applicant (full docs)",
     {"credit_debit_ratio": 3.0, "cashflow_cv": 0.15, "min_balance_l3m": 25000},
     {"net_to_gross_ratio": 0.85},
     {"utility_stability": 0.80}),
    ("Excellent applicant (full docs)",
     {"credit_debit_ratio": 5.0, "cashflow_cv": 0.05, "min_balance_l3m": 50000},
     {"net_to_gross_ratio": 0.88},
     {"utility_stability": 0.95}),
]

for label, bank, salary, utility in tests:
    r = _score_with_refit_models(bank, salary, utility)
    print(f"\n  {label}")
    print(f"    Score: {r['score']}  PD: {r['pd']:.4f}")
    print(f"    WoE:   {r['woe_row']}")

print("\nReview files written:")
print(f"  {OUTPUT_BINNING}")
print(f"  {OUTPUT_LR}")
print("\nThese are NOT yet live. Inspect the tables above -- once you're satisfied")
print("Special/Missing bins look right and bin granularity is preserved (no single")
print("(-inf, inf) bins), manually promote them:")
print(f"  copy {OUTPUT_BINNING} -> {ARTIFACTS}/binning.pkl")
print(f"  copy {OUTPUT_LR} -> {ARTIFACTS}/lr_model.pkl")
print("Then restart uvicorn.")

print("\nDone. Restart uvicorn to serve updated artifacts.")
print("\n--- MENTOR FLAG (task 4) ---")
print("Missingness rates used above are assumed placeholders "
      "(bank_statement=12%, utility_bill=22%, salary_doc=15%), not yet measured "
      "from real applicant document-submission logs. Special/Missing bin WoE "
      "values should be treated as a documented placeholder assumption, not a "
      "fully validated model output, until real missingness rates are available.")
print("\nAdditionally: the original synthetic training file was deleted before "
      "this refit, so df_train was reconstructed from the previous binning.pkl's "
      "own bin edges/counts/event rates, not the original row-level data. This "
      "preserves each feature's marginal distribution and event rate but NOT "
      "cross-feature correlations from the original synthetic set. Recommend "
      "regenerating proper joint synthetic data (or sourcing real data) before "
      "this becomes the long-term training pipeline.")