"""
PRISM — Stage 7: Credit Score Scaling (PDO Method)
====================================================
Literature basis:
    Siddiqi (2006) — Credit Risk Scorecards, Chapter 10
    Anderson (2007) — The Credit Scoring Toolkit, Chapter 9
    Fair Isaac Corporation (1989) — Original PDO scorecard framework

PDO Scaling Formula (per Siddiqi):
    Score = Offset + Factor × log_odds
    where:
        Factor = PDO / ln(2)
        Offset = BaseScore - Factor × ln(BaseOdds)

Derivation:
    If Score doubles the odds, then:
        Score + PDO = Offset + Factor × ln(2 × Odds)
                    = Offset + Factor × (ln(Odds) + ln(2))
    Subtracting:
        PDO = Factor × ln(2)  →  Factor = PDO / ln(2)

    At BaseOdds, Score = BaseScore:
        BaseScore = Offset + Factor × ln(BaseOdds)
        Offset    = BaseScore - Factor × ln(BaseOdds)

Industry-standard parameters (per Siddiqi Table 10.1):
    PDO        = 50     (every 50 points doubles the odds of being good)
    BaseScore  = 600    (score at which BaseOdds applies)
    BaseOdds   = 1:20   (1 bad for every 20 good at the base score)
    Score range: 300–900 (mirrors FICO / CIBIL convention)

Individual feature point allocation:
    Per-feature score = (Factor × β_i × WoE_i) + (Offset/n_features)
    This lets you decompose total score into per-feature contributions —
    directly used in the reason codes of Stage 8.
"""

import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import LogisticRegression

# ── PDO PARAMETERS ────────────────────────────────────────────────────────────
PDO        = 50
BASE_SCORE = 600
BASE_ODDS  = 1 / 20    # 1 bad : 20 good
SCORE_MIN  = 300
SCORE_MAX  = 900

FACTOR = PDO / np.log(2)
OFFSET = BASE_SCORE - FACTOR * np.log(BASE_ODDS)

FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance"
]
# ──────────────────────────────────────────────────────────────────────────────


def log_odds_to_score(log_odds: np.ndarray) -> np.ndarray:
    """
    Convert log-odds to credit score using PDO scaling.
    Clips to [300, 900] per industry convention.

    Higher score = lower risk (higher log-odds = more good than bad).
    """
    raw_scores = OFFSET + FACTOR * log_odds
    return np.clip(raw_scores, SCORE_MIN, SCORE_MAX).astype(int)


def compute_feature_point_contributions(
    model: LogisticRegression,
    X_woe: np.ndarray,
    n_features: int = len(FEATURES)
) -> np.ndarray:
    """
    Decompose total score into per-feature point contributions.

    Per Siddiqi (2006), the scorecard points for feature i on a given borrower:
        Points_i = Factor × β_i × WoE_i(borrower) + Offset/n_features

    This gives an additive breakdown:
        Total Score = Σ Points_i  (within rounding)

    Shape: (n_samples, n_features)
    """
    coefs   = model.coef_[0]                        # shape: (n_features,)
    offset_per_feature = OFFSET / n_features

    # contribution of each feature per sample: Factor × β_i × WoE_ij
    contributions = FACTOR * (X_woe * coefs)         # shape: (n_samples, n_features)
    contributions += offset_per_feature              # distribute intercept evenly

    return contributions


def scorecard_table(
    model: LogisticRegression,
    binning_models: dict,
    features: list = FEATURES
) -> pd.DataFrame:
    """
    Generate a full scorecard table — the final artifact of the scorecard
    development process, required for regulator sign-off.

    For each feature × bin, shows:
        - WoE value
        - Score points allocated to that bin

    Per Siddiqi (2006): Points_bin = Factor × β_i × WoE_bin + Offset/n_features
    The scorecard table is what underwriters historically used to compute
    scores by hand — it makes the model fully transparent.
    """
    coefs   = model.coef_[0]
    n_feat  = len(features)
    rows    = []

    for i, col in enumerate(features):
        ob    = binning_models[col]
        table = ob.binning_table.build()
        table = table[table["Bin"] != "Totals"]

        for _, row in table.iterrows():
            try:
                woe_val = float(row["WoE"])
            except (ValueError, TypeError):
                continue   # skip Special / empty rows
            points    = FACTOR * coefs[i] * woe_val + OFFSET / n_feat

            rows.append({
                "feature": col,
                "bin"    : row["Bin"],
                "WoE"    : round(woe_val, 4),
                "β_i"    : round(coefs[i], 6),
                "points" : round(points, 1)
            })

    return pd.DataFrame(rows)


def score_distribution_report(scores: np.ndarray, pd_values: np.ndarray) -> pd.DataFrame:
    """
    Score band analysis — shows population distribution and default rates
    across score bands.

    This table is used to set approval cutoffs in production.
    """
    bands = [
        (300, 450, "Very Poor"),
        (450, 550, "Poor"),
        (550, 620, "Fair"),
        (620, 680, "Good"),
        (680, 750, "Very Good"),
        (750, 900, "Excellent")
    ]

    df = pd.DataFrame({"score": scores, "pd": pd_values})
    rows = []

    for lo, hi, label in bands:
        mask = (df["score"] >= lo) & (df["score"] < hi)
        subset = df[mask]

        if len(subset) == 0:
            continue

        rows.append({
            "band"      : f"{lo}–{hi}",
            "label"     : label,
            "count"     : len(subset),
            "pct"       : f"{100*len(subset)/len(df):.1f}%",
            "avg_score" : round(subset["score"].mean(), 1),
            "avg_pd"    : round(subset["pd"].mean(), 4),
        })

    return pd.DataFrame(rows)


# ── STANDALONE RUN ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    model          = joblib.load("artifacts/lr_model.pkl")
    binning_models = joblib.load("artifacts/binning_models.pkl")
    pd_out         = joblib.load("artifacts/pd_output.pkl")
    data           = joblib.load("artifacts/woe_datasets.pkl")

    log_odds   = pd_out["log_odds"]
    pd_values  = pd_out["pd_values"]
    X_test_woe = data["X_test_woe"].values

    print("Stage 7 — PDO Score Scaling Parameters:")
    print(f"  PDO        : {PDO}")
    print(f"  BaseScore  : {BASE_SCORE}")
    print(f"  BaseOdds   : 1:{int(1/BASE_ODDS)}")
    print(f"  Factor     : {FACTOR:.4f}")
    print(f"  Offset     : {OFFSET:.4f}")

    scores = log_odds_to_score(log_odds)

    print(f"\nStage 7 — Score distribution (test set):")
    print(f"  Mean score : {scores.mean():.1f}")
    print(f"  Min score  : {scores.min()}")
    print(f"  Max score  : {scores.max()}")
    print(f"  Std dev    : {scores.std():.1f}")

    print("\nStage 7 — Score Band Report:")
    band_report = score_distribution_report(scores, pd_values)
    print(band_report.to_string(index=False))

    print("\nStage 7 — Full Scorecard Table (per-bin points):")
    sc_table = scorecard_table(model, binning_models)
    print(sc_table.to_string(index=False))

    # Save scores
    joblib.dump({"scores": scores, "pd_values": pd_values,
                 "log_odds": log_odds, "X_test_woe": X_test_woe},
                "artifacts/scored_output.pkl")

    print("\nStage 7 complete.")