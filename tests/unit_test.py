import pytest
from backend.scoring import risk_scorer as engine


def _fixed_score(monkeypatch, raw_score):
    """Force _to_score to return a known value so we control the pre-cap score."""
    monkeypatch.setattr(engine, "_to_score", lambda log_odds: raw_score)


def test_score_capped_above_max_allowed(monkeypatch):
    # doc_coverage < 0.4 -> max_allowed_score = 500
    _fixed_score(monkeypatch, 650)
    result = engine.compute_risk_score(None, None, None)  # all docs missing -> low coverage
    assert result["risk_score"] == 500
    assert result["score_capped"] is True


def test_score_capped_below_min_score_not_flagged(monkeypatch):
    # min-score capping isn't handled by this flag at all (only max_allowed_score),
    # but a low raw score under max_allowed_score should never be flagged capped.
    _fixed_score(monkeypatch, 320)
    result = engine.compute_risk_score(None, None, None)  # max_allowed_score = 500
    assert result["risk_score"] == 320
    assert result["score_capped"] is False


def test_score_capped_exact_boundary_not_flagged(monkeypatch):
    # raw score exactly equal to max_allowed_score should NOT be flagged capped
    _fixed_score(monkeypatch, 500)
    result = engine.compute_risk_score(None, None, None)  # max_allowed_score = 500
    assert result["risk_score"] == 500
    assert result["score_capped"] is False


def test_score_capped_full_coverage_normal_range(monkeypatch):
    # full doc coverage -> max_allowed_score = 900, well above a normal raw score
    _fixed_score(monkeypatch, 640)
    bank    = {"credit_debit_ratio": 1.2, "cashflow_cv": 0.3, "min_balance_l3m": 15000}
    salary  = {"net_to_gross_ratio": 0.8}
    utility = {"utility_stability": 0.9}
    result = engine.compute_risk_score(bank, salary, utility)
    assert result["risk_score"] == 640
    assert result["score_capped"] is False