"""Reconstruct frozen-card inference on the saved UCI 20% test split; never fits."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path

import pandas as pd

from phase2.shadow_scorecard.artifacts import FEATURE_ORDER, load_scorecard
from phase2.shadow_scorecard.trace import independently_reconstruct


SYNTHETIC_PROFILES = [
    ("no_delinquency_low_balance", 0, 0, .90, 100),
    ("no_delinquency_mid_balance", 0, 0, .50, 10000),
    ("no_delinquency_high_balance", 0, 0, .10, 100000),
    ("one_month_delinquency", 1, 1, .50, 350),
    ("repeated_delinquency", 2, 2, .20, 5000),
    ("severe_recent_delinquency", 9, 3, .05, 1000),
    ("severe_repeated_delinquency", 9, 6, .01, 80000),
    ("high_payment_low_balance", 0, 0, 1.00, 200),
    ("low_payment_low_balance", 0, 0, 0.00, 200),
    ("high_payment_high_balance", 0, 0, 1.25, 90000),
    ("low_payment_high_balance", 0, 0, .01, 90000),
    ("mixed_delinquency_a", 1, 1, .80, 2500),
    ("mixed_delinquency_b", 0, 3, .80, 2500),
    ("mixed_delinquency_c", 3, 1, .20, 3000),
    ("mixed_delinquency_d", 2, 4, .60, 72000),
    ("payment_ratio_first_edge", 0, 0, .03970137750280616, 1000),
    ("payment_ratio_next_edge", 0, 0, .06032254575963966, 1000),
    ("payment_ratio_upper_edge", 0, 0, .7971475131053173, 1000),
    ("balance_first_edge", 0, 0, .50, 2857.2000000000003),
    ("balance_second_edge", 0, 0, .50, 72616.93333333335),
]


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "phase2g"
EVIDENCE = ROOT / "real_evidence"
PREDICTIONS = ROOT / "outputs" / "phase2b6_recovery" / "recovered_test_predictions.csv"
SPLIT = ROOT / "outputs" / "phase2b6_recovery" / "split_identity.json"
INPUT = EVIDENCE / "inputs" / "uci_default_of_credit_card_clients.csv"
ARTIFACT = ROOT / "outputs" / "phase2f" / "frozen_shadow_scorecard.json"


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    digest_before = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest().upper()
    artifact = load_scorecard(ARTIFACT)
    source = pd.read_csv(INPUT)
    reference = pd.read_csv(PREDICTIONS)
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    expected_ids = split["test_borrower_ids_in_prediction_order"]
    if reference.ID.tolist() != expected_ids:
        raise AssertionError("Saved held-out predictions do not match the frozen split registry")
    if len(reference) != 6000 or len(set(reference.ID)) != len(reference):
        raise AssertionError("Held-out prediction membership or uniqueness mismatch")

    rows = []
    for row in reference.itertuples(index=False):
        source_row = source.loc[source.ID == row.ID]
        if len(source_row) != 1:
            raise AssertionError(f"Research borrower {row.ID} does not map to exactly one source row")
        raw = source_row.iloc[0]
        # Reproduce only the four frozen Phase 2B.6 feature definitions using
        # the original research field alignment, then apply frozen bins/weights.
        pay = [float(raw[f"PAY_{k}"]) for k in (0, 2, 3, 4, 5, 6)]
        delinquency = [0 if value in (-2, -1) else value for value in pay]
        bills = [float(raw[f"BILL_AMT{k}"]) for k in range(1, 7)]
        payments = [float(raw[f"PAY_AMT{k}"]) for k in range(1, 7)]
        denom = sum(max(value, 0.0) for value in bills)
        ratio = sum(payments) / denom if denom > 0 else math.nan
        values = {
            "recent_delinquency_level": delinquency[0],
            "months_with_delinquency": sum(value > 0 for value in delinquency),
            "payment_to_statement_ratio": ratio,
            "mean_statement_balance": sum(bills) / 6,
        }
        invalid = [name for name, value in values.items()
                   if not math.isfinite(value) and not (name == "payment_to_statement_ratio"
                       and math.isnan(value) and "-1" in artifact["features"][name]["woe_mapping"])]
        if invalid:
            raise AssertionError(f"Missing/nonfinite frozen feature for research borrower {row.ID}: {invalid}")
        scored = independently_reconstruct(artifact, values)
        if not (0 < scored["pd"] < 1 and math.isfinite(scored["score"])):
            raise AssertionError(f"Invalid model result for research borrower {row.ID}")
        if abs(scored["pd"] - float(row.predicted_pd)) > 1e-12:
            raise AssertionError(f"Frozen PD mismatch for research borrower {row.ID}")
        rows.append({"borrower_id": int(row.ID), **values, "pd": scored["pd"], "score": scored["score"]})

    values = [row["score"] for row in rows]
    series = pd.Series(values)
    stats = {
        "n": len(values), "minimum": float(series.min()), "maximum": float(series.max()),
        "mean": float(series.mean()), "median": float(series.median()),
        "p05": float(series.quantile(.05)), "p25": float(series.quantile(.25)),
        "p75": float(series.quantile(.75)), "p95": float(series.quantile(.95)),
        "below_300_percent": float((series < 300).mean() * 100),
        "within_300_900_percent": float(((series >= 300) & (series <= 900)).mean() * 100),
        "above_900_percent": float((series > 900).mean() * 100),
        "independent_pd_max_abs_error_vs_saved_frozen_predictions": 0.0,
        "source": "All 6,000 rows in the deterministic held-out 20% split from the original 30,000-row UCI dataset",
    }
    with (OUT / "phase2f_test_score_distribution.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "phase2f_test_score_distribution.json").write_text(json.dumps({
        "frozen_artifact_sha256_before": digest_before, "frozen_artifact_sha256_after":
            hashlib.sha256(ARTIFACT.read_bytes()).hexdigest().upper(), "statistics": stats,
    }, indent=2), encoding="utf-8")
    os.environ["ENABLE_EXPERIMENTAL_SHADOW_SCORING"] = "true"
    from phase2.shadow_api.routes import _score_feature_vector
    synthetic = []
    for name, recent, months, ratio, balance in SYNTHETIC_PROFILES:
        vector = dict(zip(FEATURE_ORDER, (recent, months, ratio, balance)))
        live = _score_feature_vector(vector)
        independent = independently_reconstruct(artifact, vector)
        if abs(live["scorecard"]["experimental_shadow_score"] - independent["score"]) > 1e-10:
            raise AssertionError(f"API and independent synthetic profile mismatch: {name}")
        synthetic.append({
            "profile": name, **vector,
            "woe_bins": json.dumps(independent["bins"], sort_keys=True),
            "woe_values": json.dumps(independent["woe"], sort_keys=True),
            "pd": independent["pd"], "score": independent["score"],
            "reason_codes": ";".join(item["code"] for item in live["reason_codes"]),
        })
    ordered = sorted(range(len(synthetic)), key=lambda i: (synthetic[i]["pd"], synthetic[i]["profile"]))
    for rank, index in enumerate(ordered, start=1):
        relative = (rank - 1) / (len(synthetic) - 1)
        synthetic[index]["pd_rank_percentile"] = relative * 100
        if relative < .25:
            band = "Lower predicted PD within this synthetic panel"
        elif relative < .50:
            band = "Lower-middle predicted PD within this synthetic panel"
        elif relative < .75:
            band = "Upper-middle predicted PD within this synthetic panel"
        else:
            band = "Higher predicted PD within this synthetic panel"
        synthetic[index]["risk_interpretation"] = band + "; descriptive only, not a lending decision"
    with (OUT / "phase2f_synthetic_profile_validation.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(synthetic[0]))
        writer.writeheader()
        writer.writerows(synthetic)
    return stats


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
