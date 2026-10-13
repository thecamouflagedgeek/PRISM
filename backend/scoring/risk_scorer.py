"""Fail-closed runtime for the existing PRISM scorecard (artifacts unchanged)."""
import hashlib
import json
import os
from typing import Any, Dict, Optional

import joblib
import numpy as np
import pandas as pd

_BASE = os.path.dirname(os.path.abspath(__file__))
_ARTIFACTS = os.path.join(_BASE, "artifacts")
_MODEL_PATH = os.path.join(_ARTIFACTS, "lr_model.pkl")
_BINNING_PATH = os.path.join(_ARTIFACTS, "binning.pkl")
_MANIFEST_PATH = os.path.join(_ARTIFACTS, "manifest.json")
_FEATURES = ["credit_debit_ratio", "cashflow_cv", "net_to_gross_ratio", "utility_stability", "min_balance"]
_PDO, _BASE_SCORE, _BASE_ODDS = 50, 600, 20
_EXPECTED_MODEL_VERSION = "prism-scorecard-existing-2026-10-phase1"
_EXPECTED_VALIDATION_STATUS = "UNVERIFIED_REAL_WORLD"
_EXPECTED_PHASE_1_RUNTIME_STATUS = "VERIFIED"
_FACTOR = _PDO / np.log(2)
_OFFSET = _BASE_SCORE - _FACTOR * np.log(_BASE_ODDS)
SUFFICIENCY_CONFIG = {
    "minimum_feature_coverage": 1.0, "minimum_transactions": 6,
    "minimum_history_days": 90, "minimum_utility_observations": 3,
    "minimum_extraction_quality": 0.60,
    "maximum_document_age_days": 180,
    "feature_ranges": {"credit_debit_ratio": (0, 100), "cashflow_cv": (0, 100),
        "net_to_gross_ratio": (0, 1), "utility_stability": (0, 1), "min_balance": (-1e12, 1e12)},
}

for _path in (_MODEL_PATH, _BINNING_PATH, _MANIFEST_PATH):
    if not os.path.isfile(_path):
        raise RuntimeError(f"Active scorecard bundle is incomplete: {_path}")
with open(_MANIFEST_PATH, encoding="utf-8-sig") as _f:
    MODEL_MANIFEST = json.load(_f)
if MODEL_MANIFEST.get("model_version") != _EXPECTED_MODEL_VERSION:
    raise RuntimeError("Active model version does not match runtime expectation")
if MODEL_MANIFEST.get("model_validation_status") != _EXPECTED_VALIDATION_STATUS:
    raise RuntimeError("Active model validation status is missing or unsafe")
if MODEL_MANIFEST.get("phase_1_runtime_status") != _EXPECTED_PHASE_1_RUNTIME_STATUS:
    raise RuntimeError("Phase 1 runtime verification status is not VERIFIED")
if MODEL_MANIFEST.get("scorecard_constants") != {"pdo": _PDO, "base_score": _BASE_SCORE,
        "base_good_bad_odds": _BASE_ODDS, "minimum_score": 300, "maximum_score": 900}:
    raise RuntimeError("Active scorecard constants do not match runtime expectation")
for _name, _path in (("lr_model.pkl", _MODEL_PATH), ("binning.pkl", _BINNING_PATH)):
    with open(_path, "rb") as _f:
        _hash = hashlib.sha256(_f.read()).hexdigest()
    if MODEL_MANIFEST.get("artifacts", {}).get(_name) != _hash:
        raise RuntimeError(f"Active artifact hash mismatch: {_name}")
_model = joblib.load(_MODEL_PATH)
_binning_models = joblib.load(_BINNING_PATH)
if list(getattr(_model, "feature_names_in_", [])) != _FEATURES:
    raise RuntimeError("Model feature schema does not match runtime schema")
if MODEL_MANIFEST.get("feature_schema") != _FEATURES:
    raise RuntimeError("Manifest feature schema does not match runtime schema")
if set(_binning_models) != set(_FEATURES) or len(_model.coef_[0]) != len(_FEATURES):
    raise RuntimeError("Binning/model feature schema mismatch")


def _safe(data, key):
    if not isinstance(data, dict) or data.get(key) is None:
        return None
    try:
        value = float(data[key])
        return value if np.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _build_feature_dict(bank=None, salary=None, utility=None):
    return {"credit_debit_ratio": _safe(bank, "credit_debit_ratio"),
        "cashflow_cv": _safe(bank, "cashflow_cv"), "net_to_gross_ratio": _safe(salary, "net_to_gross_ratio"),
        "utility_stability": _safe(utility, "utility_stability"), "min_balance": _safe(bank, "min_balance_l3m")}


def _feature_states(values, evidence):
    states = {}
    sources = (evidence or {}).get("feature_sources", {})
    for name in _FEATURES:
        value = values.get(name)
        lo, hi = SUFFICIENCY_CONFIG["feature_ranges"][name]
        available = value is not None and np.isfinite(float(value))
        valid = bool(available and lo <= float(value) <= hi)
        states[name] = {"value": float(value) if available else None, "available": bool(available),
            "source_evidence": sources.get(name), "validation_status": "VALID" if valid else
            ("UNAVAILABLE" if not available else "OUT_OF_RANGE"),
            "warning": None if valid else ("feature_unavailable" if not available else "feature_out_of_range")}
    return states


def assess_sufficiency(feature_dict, evidence=None):
    evidence = evidence or {}
    states = _feature_states(feature_dict, evidence)
    reasons = []
    coverage = sum(s["validation_status"] == "VALID" for s in states.values()) / len(_FEATURES)
    if coverage < SUFFICIENCY_CONFIG["minimum_feature_coverage"]:
        reasons.append("required_feature_coverage_below_threshold")
    for name, state in states.items():
        if state["validation_status"] != "VALID":
            reasons.append(f"feature_{name}_{state['validation_status'].lower()}")
    bank = evidence.get("bank", {})
    if int(bank.get("transaction_count", 0) or 0) < SUFFICIENCY_CONFIG["minimum_transactions"]:
        reasons.append("insufficient_transactions")
    if int(bank.get("history_days", 0) or 0) < SUFFICIENCY_CONFIG["minimum_history_days"]:
        reasons.append("insufficient_statement_history")
    utility_evidence = evidence.get("utility", {})
    if int(utility_evidence.get("observation_count", 0) or 0) < SUFFICIENCY_CONFIG["minimum_utility_observations"]:
        reasons.append("insufficient_utility_history")
    for source in ("bank", "salary", "utility"):
        doc = evidence.get(source, {})
        if not doc.get("available"):
            reasons.append(f"{source}_document_unavailable")
        if doc.get("extraction_status") != "SUCCESS":
            reasons.append(f"{source}_extraction_failed")
        quality = doc.get("quality_score")
        if quality is None or float(quality) < SUFFICIENCY_CONFIG["minimum_extraction_quality"]:
            reasons.append(f"{source}_extraction_quality_low")
        age = doc.get("age_days")
        if age is not None and float(age) > SUFFICIENCY_CONFIG["maximum_document_age_days"]:
            reasons.append(f"{source}_document_stale")
        if doc.get("future_dated"):
            reasons.append(f"{source}_document_date_invalid")
    reasons = sorted(set(reasons))
    qualities = [float(evidence.get(name, {}).get("quality_score") or 0.0) for name in ("bank", "salary", "utility")]
    tx_quality = min(1.0, int(bank.get("transaction_count", 0) or 0) / SUFFICIENCY_CONFIG["minimum_transactions"])
    history_quality = min(1.0, int(bank.get("history_days", 0) or 0) / SUFFICIENCY_CONFIG["minimum_history_days"])
    evidence_quality = float(np.mean(qualities) * tx_quality * history_quality)
    return {"sufficient": not reasons, "status": "READY" if not reasons else "INSUFFICIENT_DATA",
        "reasons": reasons, "feature_states": states, "feature_coverage": coverage,
        "confidence": {"type": "evidence_quality_index_not_probability", "score": round(evidence_quality, 4),
            "components": {"document_quality_mean": round(float(np.mean(qualities)), 4),
                "transaction_coverage": round(tx_quality, 4), "history_coverage": round(history_quality, 4)}}}


def _apply_woe(feature_dict):
    row, bin_indices = {}, {}
    for feature in _FEATURES:
        value = feature_dict.get(feature)
        if value is None or not np.isfinite(float(value)):
            raise ValueError(f"WoE input unavailable: {feature}")
        binning = _binning_models[feature]
        woe = float(binning.transform([value], metric="woe")[0])
        bin_indices[feature] = int(binning.transform([value], metric="indices")[0])
        if not np.isfinite(woe):
            raise ValueError(f"Non-finite fitted WoE for {feature}")
        # Runtime uses only the fitted training bins/WoE; out-of-range values map
        # to the fitted endpoint bin, with an explicit trace warning.
        row[feature] = woe
    return pd.DataFrame([row], columns=_FEATURES), bin_indices


def _risk_tier(pd_value):
    return "Low" if pd_value < .2 else "Medium" if pd_value < .4 else "High" if pd_value < .7 else "Very High"


def _compute_pd(log_odds):
    if log_odds >= 0:
        e = np.exp(-log_odds)
        return float(1 / (1 + e))
    e = np.exp(log_odds)
    return float(e / (1 + e))


def _score_trace(log_odds):
    raw = float(_OFFSET - _FACTOR * log_odds)
    return {"raw_score_unclipped": raw, "display_score": int(np.clip(raw, 300, 900)),
        "clipping_occurred": bool(raw < 300 or raw > 900)}


def score_borrower(bank: Optional[Dict[str, Any]] = None, salary: Optional[Dict[str, Any]] = None,
                   utility: Optional[Dict[str, Any]] = None, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    features = _build_feature_dict(bank, salary, utility)
    gate = assess_sufficiency(features, evidence)
    common = {"features": features, "feature_states": gate["feature_states"], "data_sufficiency": gate,
        "model_validation_status": MODEL_MANIFEST["model_validation_status"], "pd_type": "raw_model_pd_uncalibrated",
        "phase_1_runtime_status": MODEL_MANIFEST["phase_1_runtime_status"],
        "confidence": gate["confidence"], "warnings": list(gate["reasons"])}
    if not gate["sufficient"]:
        return {**common, "status": "INSUFFICIENT_DATA", "display_score": None, "pd": None, "raw_pd": None,
            "risk_tier": None, "reason_codes": []}
    woe_df, bin_indices = _apply_woe(features)
    woe = woe_df.iloc[0].to_dict()
    logit = float(_model.intercept_[0] + np.dot(np.asarray(_model.coef_[0]), woe_df[_FEATURES].to_numpy(float).reshape(-1)))
    pd_value = _compute_pd(logit)
    trace = _score_trace(logit)
    contributions = {name: float(-_FACTOR * coef * woe[name]) for name, coef in zip(_FEATURES, _model.coef_[0])}
    reasons = [{"feature": name, "contribution": round(value, 2),
        "direction": "increases risk" if value < 0 else "reduces risk"}
        for name, value in sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:4]]
    raw_score_reconstructed = float(_OFFSET - _FACTOR * (float(_model.intercept_[0]) +
        sum(float(c) * float(woe[n]) for n, c in zip(_FEATURES, _model.coef_[0]))))
    good_bad_odds = ((1-pd_value)/pd_value) if 0.0 < pd_value < 1.0 else None
    return {**common, "status": "SCORED", **trace,
        "pd": round(pd_value, 6), "raw_pd": pd_value, "log_odds": logit, "risk_tier": _risk_tier(pd_value),
        "risk_tier_type": "descriptive_only",
        "woe_features": {k: float(v) for k, v in woe.items()}, "feature_contributions": contributions,
        "bin_indices": bin_indices,
        "reason_codes": reasons, "confidence": gate["confidence"],
        "score_calculation": {"good_bad_odds": good_bad_odds, "odds_saturated": good_bad_odds is None, "pdo": _PDO,
            "base_score": _BASE_SCORE, "base_good_bad_odds": _BASE_ODDS,
            "formula": "score = base_score + PDO/ln(2) * ln(((1-PD)/PD)/base_good_bad_odds)",
            "reconstructed_raw_score": raw_score_reconstructed}}


def risk_score(bank=None, salary=None, utility=None, evidence=None):
    return score_borrower(bank, salary, utility, evidence)


__all__ = ["score_borrower", "risk_score", "assess_sufficiency", "SUFFICIENCY_CONFIG", "MODEL_MANIFEST"]
