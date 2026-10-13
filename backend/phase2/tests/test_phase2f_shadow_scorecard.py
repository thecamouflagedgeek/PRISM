"""Phase 2F tests are inference-only: no model fitting or artifact learning."""
from dataclasses import replace
from pathlib import Path
import json
import math
import pandas as pd
import pytest

from phase2.shadow_scorecard.artifacts import load_scorecard, FEATURE_ORDER, RECOVERED
from phase2.shadow_scorecard.binning import assign_bin, UnmappableFrozenBin
from phase2.shadow_scorecard.scorer import score_validated_result, ShadowScoreError
from phase2.shadow_scorecard.score_scaling import score_from_good_bad_odds
from phase2.shadow_scorecard.trace import independently_reconstruct
from phase2.credit_parser.fixtures import (statement_payloads, repayment_payloads, consent,
    AT, CUTOFF, BORROWER)
from phase2.credit_parser.normalizer import run_equivalence_path
from phase2.credit_evidence.consent import SCOPE_CARD_STATEMENTS
from phase2.credit_evidence.eligibility import assess_eligibility

PHASE2 = Path(__file__).parents[1]
ART = load_scorecard()


def run(stmts=None, history=None, cons=None):
    return run_equivalence_path(statement_payloads() if stmts is None else stmts,
        repayment_payloads() if history is None else history,
        consent=cons or consent(), prediction_cutoff_month=CUTOFF,
        borrower_reference=BORROWER, at=AT)


def test_frozen_artifact_type_hash_and_feature_order():
    assert ART["source_status"] == "PHASE_2B6_INCONCLUSIVE"
    assert ART["feature_order"] == FEATURE_ORDER
    assert ART["logistic_regression"]["feature_order"] == FEATURE_ORDER
    assert ART["artifact_sha256"] == "A8F64F289D76DBA2B766F85739CEA9B59AC0D8285C7F0531B387ADBBA1EEF6EC"


def test_exact_frozen_bins_woe_coefficients_and_intercept_loaded():
    expected_beta = {"recent_delinquency_level": -0.718481742041798,
        "months_with_delinquency": -0.6450690745928691,
        "payment_to_statement_ratio": -0.6990225651079325,
        "mean_statement_balance": -2.995212789975563}
    expected_edges = {"recent_delinquency_level": ["-Infinity", 1.0, "Infinity"],
        "months_with_delinquency": ["-Infinity", 1.0, "Infinity"],
        "payment_to_statement_ratio": ["-Infinity", 0.03970137750280616, 0.06032254575963966,
            0.2040156495459412, 0.7971475131053173, "Infinity"],
        "mean_statement_balance": ["-Infinity", 2857.2000000000003, 72616.93333333335, "Infinity"]}
    for f in FEATURE_ORDER:
        assert ART["features"][f]["edges"] == expected_edges[f]
        assert ART["features"][f]["woe_mapping"]
        assert ART["logistic_regression"]["coefficients"][f] == expected_beta[f]
    assert ART["logistic_regression"]["intercept"] == pytest.approx(-1.248440883572674, abs=0)


def test_interval_closure_every_frozen_boundary_below_exactly_above():
    checked = 0
    for f in FEATURE_ORDER:
        spec = ART["features"][f]
        for edge in spec["edges"][1:-1]:
            boundary = float(edge)
            below, above = math.nextafter(boundary, -math.inf), math.nextafter(boundary, math.inf)
            at_bin = assign_bin(boundary, spec)
            assert assign_bin(below, spec) == at_bin
            assert assign_bin(above, spec) == at_bin + 1
            checked += 1
    assert checked > 0


def test_out_of_range_extremes_map_to_frozen_outer_bins_without_clipping():
    for f in FEATURE_ORDER:
        spec = ART["features"][f]
        n = len([k for k in spec["woe_mapping"] if int(k) >= 0])
        assert assign_bin(-1e100, spec) == 0
        assert assign_bin(1e100, spec) == n - 1


def test_missing_invalid_and_unmappable_bin_fail_closed():
    spec = ART["features"]["recent_delinquency_level"]
    with pytest.raises(UnmappableFrozenBin): assign_bin(None, spec)
    with pytest.raises(UnmappableFrozenBin): assign_bin(float("nan"), spec)
    with pytest.raises(UnmappableFrozenBin): assign_bin(float("inf"), spec)
    with pytest.raises(UnmappableFrozenBin): assign_bin("invalid", spec)


def test_missing_nan_only_maps_to_explicit_learned_missing_bin():
    spec = ART["features"]["payment_to_statement_ratio"]
    assert assign_bin(float("nan"), spec) == -1
    assert "-1" in spec["woe_mapping"]


def test_golden_validated_feature_path_and_full_trace():
    output = score_validated_result(run(), artifact=ART)
    assert output["result_type"] == "EXPERIMENTAL_SHADOW_SCORE"
    assert output["use_label"] == "NOT_FOR_CREDIT_DECISION"
    assert output["feature_values"] == {"recent_delinquency_level": "3", "months_with_delinquency": "3",
        "payment_to_statement_ratio": "0.5", "mean_statement_balance": "350"}
    assert output["bin_assignments"] == {"recent_delinquency_level": 1, "months_with_delinquency": 1,
        "payment_to_statement_ratio": 3, "mean_statement_balance": 0}
    assert output["woe_values"] == {"recent_delinquency_level": -2.0895984742813423,
        "months_with_delinquency": -1.3538771425779765, "payment_to_statement_ratio": 0.40889681863656524,
        "mean_statement_balance": -0.18768027859219305}
    assert output["feature_states"] == {f: "VALID" for f in FEATURE_ORDER}
    assert set(output["feature_trace"]) == set(FEATURE_ORDER)
    assert all(output["feature_trace"][f]["feature_provenance"]["source_record_ids"] for f in FEATURE_ORDER)


def test_feature_to_bin_bin_to_woe_and_woe_to_contribution_trace():
    output = score_validated_result(run(), artifact=ART)
    for f in FEATURE_ORDER:
        row = output["feature_trace"][f]
        assert row["bin_id"] == output["bin_assignments"][f]
        assert row["woe"] == output["woe_values"][f]
        assert row["contribution"] == pytest.approx(row["coefficient"] * row["woe"], abs=1e-15)


def test_contributions_logit_and_pd_reconstruct():
    output = score_validated_result(run(), artifact=ART)
    assert output["logit"] == pytest.approx(output["intercept"] + math.fsum(output["feature_contributions"].values()), abs=1e-15)
    assert output["pd"] == pytest.approx(1 / (1 + math.exp(-output["logit"])), abs=1e-15)
    assert output["good_bad_odds"] == pytest.approx((1-output["pd"])/output["pd"], abs=1e-15)


def test_independent_reconstruction_does_not_call_main_scorer():
    output = score_validated_result(run(), artifact=ART)
    independent = independently_reconstruct(ART, output["feature_values"])
    assert independent["bins"] == output["bin_assignments"]
    assert independent["woe"] == output["woe_values"]
    assert independent["logit"] == pytest.approx(output["logit"], abs=1e-12)
    assert independent["pd"] == pytest.approx(output["pd"], abs=1e-12)
    assert independent["score"] == pytest.approx(output["score"], abs=1e-12)


def test_pdo_anchors_and_score_direction():
    assert score_from_good_bad_odds(20) == pytest.approx(600, abs=1e-12)
    assert score_from_good_bad_odds(40) == pytest.approx(650, abs=1e-12)
    assert score_from_good_bad_odds(10) == pytest.approx(550, abs=1e-12)
    low_pd = (1 - .1) / .1
    high_pd = (1 - .3) / .3
    assert score_from_good_bad_odds(low_pd) > score_from_good_bad_odds(high_pd)


def test_reason_codes_rank_positive_default_logit_contributions_and_trace_sources():
    output = score_validated_result(run(), artifact=ART)
    reasons = output["reason_codes"]
    assert reasons
    assert all(r["direction"] == "increases_default_logit" and r["contribution"] > 0 for r in reasons)
    assert [r["contribution"] for r in reasons] == sorted([r["contribution"] for r in reasons], reverse=True)
    assert all(r["trace"]["feature_provenance"]["source_record_ids"] for r in reasons)


def test_no_arbitrary_tier_calibration_or_fraud_combination():
    output = score_validated_result(run(), artifact=ART)
    assert output["risk_tier"] is None
    assert output["calibration_applied"] is False
    assert output["fraud_score_combined"] is False
    assert ART["score_scaling"]["used_in_original_phase2b6"] is False


def test_arbitrary_dictionary_input_is_rejected():
    with pytest.raises(ShadowScoreError, match="SHADOW_SCORE_INELIGIBLE"):
        score_validated_result({"feature_values": {f: 0 for f in FEATURE_ORDER}}, artifact=ART)


def test_missing_feature_and_incomplete_provenance_fail_closed():
    good = run()
    missing = replace(good.features, values={k: v for k, v in good.features.values.items() if k != FEATURE_ORDER[0]})
    with pytest.raises(ShadowScoreError): score_validated_result(replace(good, features=missing), artifact=ART)
    no_prov = replace(good.features, provenance={})
    with pytest.raises(ShadowScoreError, match="SHADOW_SCORE_INELIGIBLE"):
        score_validated_result(replace(good, features=no_prov), artifact=ART)


def test_phase2e_negative_fixtures_fail_closed_catalog():
    result = json.loads((PHASE2 / "outputs/phase2e/negative_fixture_results.json").read_text())
    assert result["scenario_count"] >= 15
    assert result["all_fail_closed"] is True
    for case in result["scenarios"].values():
        assert case["eligible"] is False and case["feature_vector_returned"] is False


def test_selected_real_phase2e_negative_inputs_never_produce_score():
    base = statement_payloads()
    hist = repayment_payloads()
    missing_payment = [dict(row) for row in base]; missing_payment[0].pop("payment_amount")
    missing_balance = [dict(row) for row in base]; missing_balance[0].pop("statement_balance")
    mixed = [dict(row) for row in base]; mixed[-1]["account_reference"] = "different"
    future = [dict(row) for row in base]; future[-1]["statement_month"] = "2026-07"
    invalid_numeric = [dict(row) for row in base]; invalid_numeric[0]["statement_balance"] = "not-money"
    conflict_history = repayment_payloads(levels=(0, 0, 0, 0, 0, 0))
    loans = [dict(row) for row in base]; loan_history = [dict(row) for row in hist]
    for row in loans: row["product_type"] = "PERSONAL_LOAN"
    for row in loan_history: row["product_type"] = "PERSONAL_LOAN"
    zero_balance = [dict(row) for row in base]
    for row in zero_balance: row["statement_balance"] = "0"
    cases = [run(base[:-1], hist), run(base, []), run(missing_payment, hist), run(missing_balance, hist),
             run(mixed, hist), run(base, hist, consent(scopes={SCOPE_CARD_STATEMENTS})),
             run(base, hist, consent(withdrawn_at=AT)), run(base, repayment_payloads(confidence=.90)),
             run(statement_payloads(status_in_statements=True), conflict_history), run(loans, loan_history),
             run(zero_balance, hist), run(future, hist), run(invalid_numeric, hist)]
    good = run()
    eligibility = assess_eligibility(good.account, borrower_account_count=2, at=AT)
    cases.append(replace(good, eligibility=eligibility))
    for invalid in cases:
        with pytest.raises(ShadowScoreError): score_validated_result(invalid, artifact=ART)


def test_no_training_or_calibration_apis_in_shadow_implementation():
    root = Path(__file__).parents[1] / "shadow_scorecard"
    source = "\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
    assert ".fit(" not in source
    assert "sklearn" not in source.lower()
    assert "calibration_applied\": False" in (root / "scorer.py").read_text(encoding="utf-8")


def test_reference_phase2b6_test_predictions_reproduced_without_fitting():
    evidence = PHASE2 / "real_evidence"
    import sys
    sys.path.insert(0, str(evidence))
    import run_phase2b5r as base
    predictions = pd.read_csv(PHASE2 / "outputs/phase2b6_recovery/recovered_test_predictions.csv").head(10)
    df = pd.read_csv(base.INPUT)
    x = base.derive(df)
    for row in predictions.itertuples(index=False):
        pos = int(df.index[df.ID == row.ID][0])
        features = {f: float(x.iloc[pos][f]) for f in FEATURE_ORDER}
        expected = independently_reconstruct(ART, features)
        assert expected["pd"] == pytest.approx(float(row.predicted_pd), abs=1e-12)


def test_phase2f_implementation_is_not_imported_by_production():
    roots = [Path(__file__).parents[2] / "scoring", Path(__file__).parents[2] / "routes"]
    code = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for root in roots if root.exists() for p in root.rglob("*.py"))
    assert "phase2.shadow_scorecard" not in code


def test_phase2f_spec_provenance_and_source_hash_are_present():
    import hashlib
    actual = hashlib.sha256(RECOVERED.read_bytes()).hexdigest().upper()
    assert actual == ART["artifact_sha256"]
    assert ART["provenance"]["runner_sha256"]
