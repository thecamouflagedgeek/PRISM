"""Integrity tests for the Phase 3S.2 coverage benchmark; no model fitting."""
import hashlib
import itertools
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "backend/phase3/outputs/phase3s2"
S3 = ROOT / "backend/phase3/outputs/phase3s"
CARD = ROOT / "backend/phase2/outputs/phase2f/frozen_shadow_scorecard.json"


def readj(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_phase3s_source_hashes_unchanged():
    old = json.loads((S3 / "dataset_hashes.json").read_text())
    recorded = readj("dataset_hashes.json")["phase3s_source_hashes_unchanged"]
    assert recorded == {name: old[name] for name in old if name.endswith(".csv")}
    for name, digest in old.items():
        if name.endswith(".csv"):
            assert hashlib.sha256((S3 / name).read_bytes()).hexdigest().upper() == digest


def test_frozen_scorecard_sha_matches_phase3s_generator_manifest():
    manifest = json.loads((S3 / "generator_manifest.json").read_text())
    assert hashlib.sha256(CARD.read_bytes()).hexdigest().upper() == manifest["phase2f_frozen_spec_sha256"]
    assert readj("reproducibility.json")["frozen_scorecard_sha256"] == manifest["phase2f_frozen_spec_sha256"]


def test_all_72_theoretical_signatures_enumerated():
    assert readj("phase3s2_summary.json")["theoretical_signatures"] == 72
    assert len(pd.read_csv(OUT / "feasibility_matrix.csv")) == 72


def test_60_signatures_are_contract_feasible_and_12_fail_closed():
    s = readj("phase3s2_summary.json")
    assert s["contract_feasible_signatures"] == 60
    assert s["infeasible_signatures"] == 12


def test_every_feasible_uci_signature_is_covered():
    s = readj("phase3s2_summary.json")
    assert s["feasible_uci_signatures_covered"] == s["feasible_uci_observed_signatures"] == 54


def test_dataset_rows_and_manifest_reconcile():
    e = pd.read_csv(OUT / "synthetic_credit_evidence.csv")
    m = pd.read_csv(OUT / "synthetic_borrower_manifest.csv")
    r = pd.read_csv(OUT / "synthetic_shadow_results.csv")
    assert len(e) == 6 * len(m) == 648
    assert len(m) == len(r) == 108
    assert m.synthetic_borrower_id.nunique() == 108


def test_target_signatures_reproduce_frozen_score_bin_assignments():
    r = pd.read_csv(OUT / "synthetic_shadow_results.csv")
    assert (r["target_signature"] == r["bin_assignments_json"].map(lambda x: json.dumps([json.loads(x)[k] for k in ["recent_delinquency_level", "months_with_delinquency", "payment_to_statement_ratio", "mean_statement_balance"]]))).all()


def test_every_generated_row_is_scoreable_and_has_frozen_model_identity():
    r = pd.read_csv(OUT / "synthetic_shadow_results.csv")
    assert r.scoreable.all()
    assert r.artifact_sha256.nunique() == 1


def test_counterfactual_and_pdo_arithmetic_reconstruct():
    c = readj("counterfactual_consistency.json")
    s = readj("phase3s2_summary.json")
    assert c["all_logit_deltas_reconstruct"] and c["all_score_directions_consistent"]
    assert max(s["max_reconstruction_error"].values()) < 1e-10


def test_six_negative_cases_fail_closed_without_scores():
    f = pd.read_csv(OUT / "fail_closed_results.csv")
    assert len(f) == 6 and f.blocked.all() and not f.scoreable.any()


def test_per_feature_occupancy_sums_to_generated_histories():
    x = pd.read_csv(OUT / "per_feature_bin_occupancy.csv")
    assert all(int(g["count"].sum()) == 108 for _, g in x.groupby("feature"))


def test_archetype_coverage_reconciles():
    x = pd.read_csv(OUT / "archetype_coverage.csv")
    assert int(x.histories.sum()) == 108


def test_no_model_fit_calibration_or_synthetic_labels():
    t = readj("phase3s2_test_results.json")
    assert t["model_fit_calls"] == t["calibration_calls"] == 0
    assert t["synthetic_labels_added"] is False


def test_hashes_are_reproducible_and_seed_is_fixed():
    d = readj("dataset_hashes.json")
    p = readj("reproducibility.json")
    assert d["seed"] == p["seed"] == 20261008
    for name, digest in d["files"].items():
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest().upper() == digest
