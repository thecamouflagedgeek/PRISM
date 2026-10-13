"""Integrity-only assertions for the frozen Phase 3S.1 diagnostic outputs."""
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
OUT = BACKEND / "phase3/outputs/phase3s1"
S3 = BACKEND / "phase3/outputs/phase3s"
CARD = BACKEND / "phase2/outputs/phase2f/frozen_shadow_scorecard.json"


def j(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_phase3s_dataset_hashes_match_recorded_hashes():
    expected = json.loads((S3 / "dataset_hashes.json").read_text())
    for name in ("synthetic_credit_evidence.csv", "synthetic_borrower_manifest.csv"):
        assert hashlib.sha256((S3 / name).read_bytes()).hexdigest().upper() == expected[name]


def test_frozen_scorecard_hash_matches_manifest():
    manifest = json.loads((S3 / "generator_manifest.json").read_text())
    assert hashlib.sha256(CARD.read_bytes()).hexdigest().upper() == manifest["phase2f_frozen_spec_sha256"]


def test_exactly_10000_histories_and_60000_records():
    assert len(pd.read_csv(S3 / "synthetic_shadow_results.csv")) == 10000
    assert len(pd.read_csv(S3 / "synthetic_credit_evidence.csv")) == 60000


def test_raw_feature_vectors_are_extracted():
    d = j("compression_analysis.json")
    assert d["unique_raw_feature_vectors_exact"] == 10000


def test_bin_assignments_reproduce_saved_phase3s_results():
    assert j("phase3s1_test_results.json")["checks"]["bin_assignments_reproduce_phase3s"]


def test_woe_vectors_reproduce_saved_phase3s_results():
    assert j("phase3s1_test_results.json")["checks"]["woe_vectors_reproduce_phase3s"]


def test_contributions_reproduce_saved_phase3s_results():
    assert j("phase3s1_test_results.json")["checks"]["contributions_reproduce_phase3s"]


def test_logits_reproduce_saved_phase3s_results():
    assert j("phase3s1_test_results.json")["checks"]["logits_reproduce_phase3s"]


def test_pds_reproduce_saved_phase3s_results():
    assert j("phase3s1_test_results.json")["checks"]["pds_reproduce_phase3s"]


def test_no_model_fitting_or_calibration_was_performed():
    r = j("phase3s1_test_results.json")
    assert r["model_fit_calls"] == 0 and r["calibration_calls"] == 0


def test_generator_was_not_executed():
    assert not j("phase3s1_test_results.json")["generator_executed"]


def test_scorecard_was_not_modified():
    assert j("phase3s1_test_results.json")["checks"]["scorecard_not_modified"]


def test_feature_bin_occupancy_sums_to_histories():
    x = pd.read_csv(OUT / "bin_occupancy.csv")
    assert all(int(g.phase3s_count.sum()) == 10000 for _, g in x.groupby("feature"))


def test_joint_signature_counts_sum_to_histories():
    x = pd.read_csv(OUT / "joint_signature_analysis.csv")
    assert int(x["count"].sum()) == 10000


def test_archetype_counts_reconcile():
    x = pd.read_csv(S3 / "synthetic_borrower_manifest.csv")
    assert int(x["archetype"].value_counts().sum()) == 10000


def test_balance_contributions_equal_coefficient_times_woe():
    x = pd.read_csv(OUT / "balance_bin_diagnostics.csv")
    assert ((x.coefficient_times_woe - x.lr_coefficient * x.woe).abs() < 1e-14).all()


def test_uci_comparison_is_descriptive_and_uses_development_rows():
    x = pd.read_csv(OUT / "uci_vs_synthetic_bin_occupancy.csv")
    assert x.uci_development_count.sum() == 24000 * 4


def test_protected_hashes_unchanged():
    assert j("protected_hashes_after.json")["unchanged"]


def test_joint_signature_counts_and_theoretical_space_are_consistent():
    d = j("compression_analysis.json")
    x = pd.read_csv(OUT / "joint_signature_analysis.csv")
    assert len(x) == d["unique_bin_signatures"] <= d["theoretical_joint_signatures"]


def test_phase3a_status_remains_external_data_required():
    assert j("root_cause_attribution.json")["phase3a_status_unchanged"] == "PHASE_3A_EXTERNAL_DATA_REQUIRED"
