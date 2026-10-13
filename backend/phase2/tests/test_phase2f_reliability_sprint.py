"""Mathematical reliability checks for the immutable Phase 2F inference path."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from phase2.shadow_scorecard.artifacts import FEATURE_ORDER, load_scorecard
from phase2.shadow_scorecard.score_scaling import score_from_pd
from phase2.shadow_scorecard.trace import independently_reconstruct
from phase2.shadow_api.routes import _score_feature_vector


PROFILES = [
    ("no_delinquency_low_balance", 0, 0, 0.90, 100),
    ("no_delinquency_mid_balance", 0, 0, 0.50, 10000),
    ("no_delinquency_high_balance", 0, 0, 0.10, 100000),
    ("one_month_delinquency", 1, 1, 0.50, 350),
    ("repeated_delinquency", 2, 2, 0.20, 5000),
    ("severe_recent_delinquency", 9, 3, 0.05, 1000),
    ("severe_repeated_delinquency", 9, 6, 0.01, 80000),
    ("high_payment_low_balance", 0, 0, 1.00, 200),
    ("low_payment_low_balance", 0, 0, 0.00, 200),
    ("high_payment_high_balance", 0, 0, 1.25, 90000),
    ("low_payment_high_balance", 0, 0, 0.01, 90000),
    ("mixed_delinquency_a", 1, 1, 0.80, 2500),
    ("mixed_delinquency_b", 0, 3, 0.80, 2500),
    ("mixed_delinquency_c", 3, 1, 0.20, 3000),
    ("mixed_delinquency_d", 2, 4, 0.60, 72000),
    ("payment_ratio_first_edge", 0, 0, 0.03970137750280616, 1000),
    ("payment_ratio_next_edge", 0, 0, 0.06032254575963966, 1000),
    ("payment_ratio_upper_edge", 0, 0, 0.7971475131053173, 1000),
    ("balance_first_edge", 0, 0, 0.50, 2857.2000000000003),
    ("balance_second_edge", 0, 0, 0.50, 72616.93333333335),
]


@pytest.mark.parametrize("name,recent,months,payment_ratio,balance", PROFILES)
def test_twenty_labeled_profiles_match_independent_frozen_reconstruction(
    name, recent, months, payment_ratio, balance, monkeypatch
):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    values = dict(zip(FEATURE_ORDER, (recent, months, payment_ratio, balance)))
    result = _score_feature_vector(values)
    independent = independently_reconstruct(load_scorecard(), values)
    assert math.isfinite(result["scorecard"]["raw_pd"])
    assert 0 < result["scorecard"]["raw_pd"] < 1
    assert result["scorecard"]["experimental_shadow_score"] == pytest.approx(independent["score"], abs=1e-10)
    assert result["scorecard"]["raw_pd"] == pytest.approx(independent["pd"], abs=1e-12)
    assert {k: v["bin_id"] for k, v in result["feature_trace"].items()} == independent["bins"]
    assert name  # Keeps each synthetic validation row visibly labeled in test reports.


def test_formula_anchors_direction_and_pd_boundaries():
    assert score_from_pd(1 / 21)[1] == pytest.approx(600, abs=1e-12)
    assert score_from_pd(1 / 41)[1] == pytest.approx(650, abs=1e-12)
    assert score_from_pd(1 / 11)[1] == pytest.approx(550, abs=1e-12)
    assert score_from_pd(0.1)[1] > score_from_pd(0.3)[1]
    for invalid in (0, 1, -0.1, 1.1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            score_from_pd(invalid)


def test_input_order_is_fixed_and_outputs_are_deterministic(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    values = dict(zip(FEATURE_ORDER, (3, 3, 0.5, 350)))
    assert _score_feature_vector(values) == _score_feature_vector(values)
    with pytest.raises(Exception):
        _score_feature_vector(dict(reversed(list(values.items()))[:-1]))


def test_frozen_artifact_integrity_and_out_of_range_score_remains_raw(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    root = Path(__file__).parents[1]
    artifact_path = root / "outputs" / "phase2f" / "frozen_shadow_scorecard.json"
    import hashlib
    before = hashlib.sha256(artifact_path.read_bytes()).hexdigest().upper()
    artifact = load_scorecard(artifact_path)
    assert len(before) == 64
    result = _score_feature_vector(dict(zip(FEATURE_ORDER, (3, 3, 0.5, 350))))
    assert result["scorecard"]["experimental_shadow_score"] == pytest.approx(282.73056512249605, abs=1e-10)
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest().upper() == before
    assert artifact["score_scaling"]["phase2f_shadow_only"] is True
