import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phase2.phase2b import (
    FEATURES, FORBIDDEN, _fit_binner, _fit_logistic, _metrics, _predict,
    _transform, assert_corrected_cohorts, assert_canonical_windows,
    assert_monthly_history_windows,
    score_from_pd, sha256,
    stratified_indices,
)

BACKEND = Path(__file__).resolve().parents[2]


def test_corrected_phase2a_cohorts_and_membership_match():
    audit = BACKEND / "phase2" / "outputs" / "berka_audit"
    frame = pd.read_csv(audit / "candidate_features_by_loan.csv")
    recon = pd.read_csv(audit / "window_reconciliation.csv")
    result = assert_corrected_cohorts(frame, recon)
    assert result["3m"]["n"] == 231
    assert result["3m"]["defaults"] == 31
    assert result["3m"]["nondefaults"] == 200
    assert result["6m"]["n"] == 187
    assert result["6m"]["defaults"] == 19
    assert result["6m"]["nondefaults"] == 168


def test_cohort_mismatch_stops_before_fit():
    audit = BACKEND / "phase2" / "outputs" / "berka_audit"
    frame = pd.read_csv(audit / "candidate_features_by_loan.csv")
    recon = pd.read_csv(audit / "window_reconciliation.csv")
    recon.loc[(recon.window == "3m") & (recon.loan_id == 5314), "new_calendar_eligible"] = False
    with pytest.raises(RuntimeError, match="membership differs"):
        assert_corrected_cohorts(frame, recon)


def test_phase2a_monthly_history_exactly_spans_complete_window():
    audit = BACKEND / "phase2" / "outputs" / "berka_audit"
    frame = pd.read_csv(audit / "candidate_features_by_loan.csv")
    monthly = pd.read_csv(audit / "monthly_histories.csv")
    assert_monthly_history_windows(frame, monthly)
    monthly.loc[0, "month"] = "1900-01"
    with pytest.raises(RuntimeError, match="does not exactly span"):
        assert_monthly_history_windows(frame, monthly)


def test_raw_loan_account_dates_reproduce_corrected_phase2a_membership():
    audit = BACKEND / "phase2" / "outputs" / "berka_audit"
    frame = pd.read_csv(audit / "candidate_features_by_loan.csv")
    assert_canonical_windows(frame)


def test_stratified_split_is_reproducible_disjoint_and_preserves_classes():
    y = np.array([0] * 40 + [1] * 6)
    a, b = stratified_indices(y, 0.2, 123)
    aa, bb = stratified_indices(y, 0.2, 123)
    assert np.array_equal(a, aa) and np.array_equal(b, bb)
    assert not set(a).intersection(b)
    assert set(a).union(b) == set(range(len(y)))
    assert y[b].sum() == 1


def test_training_only_binner_maps_missing_and_unseen_values_explicitly():
    train_x = np.array([1.0, 2.0, 3.0, 4.0, np.nan, np.nan])
    train_y = np.array([0, 0, 0, 1, 0, 1])
    binner = _fit_binner(train_x, train_y)
    val = _transform(np.array([-100.0, 100.0, np.nan]), binner)
    assert np.isfinite(val).all()
    assert "fallback_policy" in binner
    assert val[0] == binner["woe"][0]
    assert val[1] == binner["woe"][1]
    assert val[2] == binner["woe"][-1]


def test_woe_convention_gives_positive_value_to_lower_risk_bin():
    binner = _fit_binner(np.array([0, 0, 1, 1]), np.array([0, 0, 1, 1]))
    assert binner["woe"][0] > 0
    assert binner["woe"][1] < 0


def test_logistic_probability_formula_matches_manual_logit():
    X = np.array([[-1.0], [-0.5], [0.5], [1.0]] * 8)
    y = np.array([0, 0, 1, 1] * 8)
    beta, converged, _ = _fit_logistic(X, y)
    z, p = _predict(X, beta)
    assert converged
    assert np.allclose(p, 1 / (1 + np.exp(-z)))


def test_score_anchors_direction_and_unclipped_output():
    pd_values = np.array([1/41, 1/21, 1/11, 0.999])
    scores = score_from_pd(pd_values)
    assert scores[0] == pytest.approx(650.0)
    assert scores[1] == pytest.approx(600.0)
    assert scores[2] == pytest.approx(550.0)
    assert scores[3] < 300
    assert np.all(np.diff(scores) < 0)


def test_score_contribution_reconstruction_identity():
    factor = 50 / math.log(2)
    intercept, beta, woe = -0.4, np.array([0.3, -0.2]), np.array([1.1, -0.7])
    z = intercept + beta @ woe
    p = 1 / (1 + math.exp(-z))
    base = 600 - factor * math.log(20) - factor * intercept
    contributions = -factor * beta * woe
    assert base + contributions.sum() == pytest.approx(float(score_from_pd(np.array([p]))[0]))


def test_forbidden_outcome_and_demographic_fields_are_not_candidates():
    assert not FORBIDDEN.intersection(FEATURES)
    assert not {"loan_amount", "loan_duration", "district", "age", "sex", "status"}.intersection(FEATURES)


def test_active_production_artifact_hashes_remain_unchanged():
    scoring = BACKEND / "scoring" / "artifacts"
    manifest = scoring / "manifest.json"
    import json
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["model_validation_status"] == "UNVERIFIED_REAL_WORLD"
    assert data["phase_1_runtime_status"] == "VERIFIED"
    assert sha256(scoring / "lr_model.pkl") == data["artifacts"]["lr_model.pkl"]
    assert sha256(scoring / "binning.pkl") == data["artifacts"]["binning.pkl"]
    assert sha256(manifest) == "b7acf498dc2523cb11fffefe2b12e5ee58e55bcab54c231b39768dd671e11148"
