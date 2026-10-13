"""Integration assertions over the Phase 3S generated artifact package."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

OUT = Path(__file__).parents[1] / "outputs" / "phase3s"

def read_json(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))

def read_csv(name):
    with (OUT / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def test_required_phase3s_artifacts_exist():
    required = [
        "synthetic_credit_evidence.csv", "synthetic_borrower_manifest.csv", "generation_config.json",
        "generation_rules.md", "generator_manifest.json", "dataset_hashes.json", "synthetic_shadow_results.csv",
        "archetype_analysis.csv", "score_distribution.json", "bin_occupancy.csv", "reason_code_analysis.csv",
        "counterfactual_results.csv", "boundary_results.csv", "extreme_case_results.csv",
        "temporal_order_results.csv", "behavioral_collision_analysis.json", "negative_evidence_cases.json",
        "negative_case_results.json", "reconstruction_results.json", "reproducibility_results.json",
        "protected_hashes_before.json", "protected_hashes_after.json", "phase3s_test_results.json",
        "phase3s_summary.json", "phase3s_report.md",
    ]
    assert all((OUT / name).is_file() for name in required)

def test_primary_dataset_size_months_and_synthetic_ids():
    manifest = read_csv("synthetic_borrower_manifest.csv")
    evidence = read_csv("synthetic_credit_evidence.csv")
    assert len(manifest) == 10000
    assert len(evidence) == 60000
    assert len({x["synthetic_borrower_id"] for x in manifest}) == 10000
    assert len({x["synthetic_account_id"] for x in manifest}) == 10000
    assert all(x["synthetic_borrower_id"].startswith("SYN_") for x in manifest)
    assert all(x["synthetic_account_id"].startswith("SYN_") for x in manifest)
    groups = {}
    for row in evidence:
        groups.setdefault(row["synthetic_borrower_id"], []).append(row["statement_month"])
    assert all(v == ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"] for v in groups.values())

def test_frozen_pipeline_reconstruction_and_explanations():
    rows = read_csv("synthetic_shadow_results.csv")
    assert len(rows) == 10000 and all(x["scoreable"] == "True" for x in rows)
    for row in rows:
        c = json.loads(row["contributions_json"])
        assert abs(float(row["logit"]) - (-1.248440883572674 + sum(c.values()))) < 1e-10
        assert all(float(v) < 0 for v in json.loads(row["favorable_contributions_json"]).values())
        reasons = json.loads(row["adverse_reason_trace_json"])
        vals = [float(x["contribution"]) for x in reasons]
        assert all(v > 0 for v in vals)
        assert vals == sorted(vals, reverse=True)
    rec = read_json("reconstruction_results.json")
    assert max(rec["max_abs_error"].values()) < 1e-9
    assert rec["woe_mapping_max_abs_error"] < 1e-12
    assert rec["contribution_max_abs_error"] < 1e-12

def test_boundary_sweeps_follow_frozen_right_closed_bins():
    rows = read_csv("boundary_results.csv")
    tested = [r for r in rows if r.get("expected_right_closed_bin")]
    assert len(tested) >= 12
    assert all(r["bin_id"] == r["expected_right_closed_bin"] for r in tested)
    assert all(not r["error"] for r in tested)

def test_invalid_evidence_is_fail_closed_and_valid_controls_remain_distinct():
    result = read_json("negative_case_results.json")
    assert result["invalid_cases"] > 0
    assert result["invalid_cases_scored"] == 0
    cases = {x["case_id"]: x for x in result["results"]}
    assert cases["zero_denominator_non_scoreable"]["scored"] is False
    assert cases["zero_payment_valid_control"]["scored"] is True
    assert cases["negative_balance_valid_control"]["scored"] is True

def test_reproducibility_and_protected_hashes():
    rep = read_json("reproducibility_results.json")
    assert rep["byte_identical"] is True
    hashes = read_json("dataset_hashes.json")
    for name in ("synthetic_credit_evidence.csv", "synthetic_borrower_manifest.csv"):
        actual = hashlib.sha256((OUT / name).read_bytes()).hexdigest().upper()
        assert actual == hashes[name]
    after = read_json("protected_hashes_after.json")
    assert after["changed_count"] == 0

def test_phase3s_check_ledger_and_claim_boundaries():
    ledger = read_json("phase3s_test_results.json")
    assert ledger["failed"] == 0
    assert ledger["invalid_cases_scored"] == 0
    assert ledger["model_fitting_calls"] == 0
    assert ledger["calibration_calls"] == 0
    assert ledger["production_scorer_calls"] == 0
    assert ledger["external_auc_computed"] is False
    summary = read_json("phase3s_summary.json")
    assert summary["phase3a_status"] == "PHASE_3A_EXTERNAL_DATA_REQUIRED"
    assert summary["phase3a_status_changed"] is False
    assert summary["external_validity_established"] is False
