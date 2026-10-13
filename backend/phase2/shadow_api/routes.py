"""Evidence-first experimental endpoint, isolated from the production /assess router."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any
import math

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/experimental", tags=["Experimental Shadow Scoring"])
PHASE2 = Path(__file__).resolve().parents[1]
GOLDEN_PATH = PHASE2 / "outputs" / "phase2e" / "golden_fixture.json"
FROZEN_SCORECARD_PATH = PHASE2 / "outputs" / "phase2f" / "frozen_shadow_scorecard.json"
MODEL_STATUS = "PHASE_2B6_INCONCLUSIVE"
LIMITATIONS = ["NOT_EXTERNALLY_VALIDATED", "NOT_CURRENT_MARKET_VALIDATED",
               "NOT_INDIAN_MARKET_VALIDATED", "NOT_PRODUCTION_APPROVED"]
REQUIRED_SCOPES = {"CREDIT_CARD_STATEMENTS", "BUREAU_REPAYMENT_HISTORY"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceMetadata(StrictModel):
    source_document_id: str | None = Field(default=None, max_length=100)
    extraction_method: str | None = Field(default=None, max_length=80)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    account_link_confidence: float | None = Field(default=None, ge=0, le=1)
    authenticated: bool | None = None


class StatementEvidence(StrictModel):
    account_reference: str | None = Field(default=None, max_length=100)
    product_type: str | None = Field(default=None, max_length=40)
    provider: str | None = Field(default=None, max_length=100)
    masked_account_number: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, max_length=3)
    statement_month: str | None = Field(default=None, max_length=20)
    statement_balance: str | None = Field(default=None, max_length=40)
    payment_amount: str | None = Field(default=None, max_length=40)
    repayment_status: dict[str, Any] | str | None = None
    source_metadata: EvidenceMetadata | None = None


class RepaymentEvidence(StrictModel):
    account_reference: str | None = Field(default=None, max_length=100)
    product_type: str | None = Field(default=None, max_length=40)
    provider: str | None = Field(default=None, max_length=100)
    month: str | None = Field(default=None, max_length=20)
    repayment_status: str | None = Field(default=None, max_length=40)
    delinquency_severity: int | None = Field(default=None, ge=0, le=9)
    source_code: str | None = Field(default=None, max_length=100)
    source_metadata: EvidenceMetadata | None = None


class ConsentEvidence(StrictModel):
    state: str = Field(max_length=30)
    scopes: list[str] = Field(default_factory=list, max_length=10)
    granted_at: datetime | None = None
    expires_at: datetime | None = None
    withdrawn_at: datetime | None = None


class ShadowAssessmentRequest(StrictModel):
    borrower_reference: str = Field(min_length=1, max_length=100)
    prediction_cutoff_month: str = Field(min_length=7, max_length=10)
    statements: list[StatementEvidence] = Field(default_factory=list, max_length=12)
    repayment_history: list[RepaymentEvidence] = Field(default_factory=list, max_length=12)
    consent: ConsentEvidence | None = None
    borrower_account_count: int = Field(default=1, ge=1, le=100)


class FrozenFeatureVector(StrictModel):
    recent_delinquency_level: float
    months_with_delinquency: float
    payment_to_statement_ratio: float
    mean_statement_balance: float


class ShadowSimulationRequest(StrictModel):
    baseline: FrozenFeatureVector
    scenario: FrozenFeatureVector


def _score_feature_vector(values: dict[str, float]) -> dict[str, Any]:
    """Run the supplied vector through the existing immutable Phase 2F card."""
    _require_enabled()
    from scipy.special import expit
    from ..shadow_scorecard.artifacts import FEATURE_ORDER, load_scorecard
    from ..shadow_scorecard.score_scaling import score_from_pd
    from ..shadow_scorecard.woe import transform_feature
    from ..shadow_scorecard.reason_codes import REASONS
    artifact = load_scorecard(FROZEN_SCORECARD_PATH)
    if set(values) != set(FEATURE_ORDER):
        raise HTTPException(status_code=422, detail="Exactly the four frozen model features are required")
    feature_trace, contributions = {}, {}
    for feature in FEATURE_ORDER:
        value = float(values[feature])
        if not math.isfinite(value):
            raise HTTPException(status_code=422, detail=f"{feature} must be finite")
        if feature == "recent_delinquency_level" and (not value.is_integer() or not 0 <= value <= 9):
            raise HTTPException(status_code=422, detail="recent_delinquency_level must be an integer from 0 to 9")
        if feature == "months_with_delinquency" and (not value.is_integer() or not 0 <= value <= 6):
            raise HTTPException(status_code=422, detail="months_with_delinquency must be an integer from 0 to 6")
        try:
            bin_id, woe = transform_feature(value, artifact["features"][feature])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"{feature} is outside the frozen model's supported bins") from exc
        coefficient = float(artifact["logistic_regression"]["coefficients"][feature])
        contribution = coefficient * woe
        contributions[feature] = contribution
        bins = artifact["features"][feature]["bins"]
        feature_trace[feature] = {
            "value": value, "bin_id": bin_id,
            "bin": next((b for b in bins if int(b["bin_id"]) == bin_id), {"bin_id": bin_id}),
            "woe": woe, "coefficient": coefficient, "logit_contribution": contribution,
            "direction": "increases default log-odds" if contribution > 0 else "decreases default log-odds" if contribution < 0 else "no log-odds effect",
        }
    lr = artifact["logistic_regression"]
    logit = float(lr["intercept"]) + math.fsum(contributions[name] for name in FEATURE_ORDER)
    pd = float(expit(logit))
    odds, score = score_from_pd(pd)
    reasons = sorted(
        (item for item in feature_trace.items() if item[1]["logit_contribution"] > 0),
        key=lambda item: (-item[1]["logit_contribution"], FEATURE_ORDER.index(item[0])),
    )
    return {
        "features": {name: float(values[name]) for name in FEATURE_ORDER},
        "scorecard": {"logit": logit, "raw_pd": pd, "good_bad_odds": odds,
                      "experimental_shadow_score": score, "score_label": "Experimental Shadow Score",
                      "pdo_presentation_only": True},
        "feature_trace": feature_trace,
        "feature_contributions": contributions,
        "reason_codes": [{"code": name, "label": REASONS[name],
                           "direction": "increases_default_logit", "contribution": trace["logit_contribution"]}
                          for name, trace in reasons],
        "artifact_sha256": artifact["artifact_sha256"],
        "model_status": MODEL_STATUS,
        "decision_use": "NOT_FOR_CREDIT_DECISION",
    }


def enabled() -> bool:
    return os.getenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "false").strip().lower() in {"1", "true", "yes", "on"}


def _require_enabled():
    if not enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EXPERIMENTAL_FEATURE_DISABLED", "message": "Experimental shadow scoring is disabled."})


def _trace_id(payload: ShadowAssessmentRequest) -> str:
    stable = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    return sha256(stable).hexdigest()[:24]


def _blocked(trace_id: str, reasons: list[str], *, warnings=None, evidence=None):
    return {
        "status": "INSUFFICIENT_EXPERIMENTAL_EVIDENCE",
        "assessment_id": trace_id,
        "assessment_status": "INSUFFICIENT_EVIDENCE",
        "model_version": None,
        "score": None,
        "probability_of_default": None,
        "risk_tier": None,
        "feature_coverage": 0.0,
        "feature_values": None,
        "woe_values": None,
        "feature_contributions": None,
        "improvement_recommendations": [],
        "document_findings": evidence or {},
        "fraud_findings": None,
        "assessment_timestamp": datetime.now(timezone.utc).isoformat(),
        "decision_use": "NOT_FOR_CREDIT_DECISION",
        "eligibility": {"eligible": False, "blocking_reasons": list(dict.fromkeys(reasons)), "warnings": warnings or []},
        "evidence": evidence or {}, "features": None, "scorecard": None, "reason_codes": [],
        "trace_id": trace_id, "model_status": MODEL_STATUS,
        "validation_scope": ["ENGINEERING_VERIFIED", "MATHEMATICALLY_RECONSTRUCTED"],
        "limitations": LIMITATIONS,
    }


def _mapped_reasons(result) -> list[str]:
    blockers = list(getattr(result, "issues", ()))
    if result.validation:
        blockers.extend(result.validation.blockers)
    if result.eligibility:
        blockers.extend(result.eligibility.blocking_reasons)
    if result.features:
        blockers.extend(result.features.blockers)
    mapped = []
    for reason in blockers:
        if reason in {"MISSING_REPAYMENT_STATUS", "MISSING_REPAYMENT_STATUS_EVIDENCE"}:
            mapped.append("MISSING_REPAYMENT_STATUS_EVIDENCE")
        elif reason in {"UNSUPPORTED_PRODUCT", "MODEL_PRODUCT_COMPATIBILITY_UNESTABLISHED"}:
            mapped.append("UNSUPPORTED_PRODUCT")
        elif reason == "CONFLICTING_EVIDENCE":
            mapped.append(reason)
        else:
            mapped.append(reason)
    return mapped or [result.state or "EVIDENCE_NOT_ELIGIBLE"]


def _to_consent(consent_value, *, require_bureau_history: bool):
    from ..credit_evidence.models import Consent, ConsentState
    if consent_value is None:
        return None, "CONSENT_REQUIRED"
    try:
        state = ConsentState(consent_value.state.strip().upper())
    except ValueError:
        return None, "CONSENT_REQUIRED"
    now = datetime.now(timezone.utc)
    if consent_value.granted_at is not None and consent_value.granted_at.tzinfo is None:
        return None, "CONSENT_REQUIRED"
    if consent_value.expires_at is not None and consent_value.expires_at.tzinfo is None:
        return None, "CONSENT_REQUIRED"
    if consent_value.withdrawn_at is not None and consent_value.withdrawn_at.tzinfo is None:
        return None, "CONSENT_REQUIRED"
    if state.value == "WITHDRAWN" or (consent_value.withdrawn_at and consent_value.withdrawn_at <= now):
        return None, "CONSENT_WITHDRAWN"
    if state.value != "GRANTED":
        return None, "CONSENT_REQUIRED"
    required_scopes = {"CREDIT_CARD_STATEMENTS"}
    if require_bureau_history:
        required_scopes.add("BUREAU_REPAYMENT_HISTORY")
    if not required_scopes.issubset(set(consent_value.scopes)):
        return None, "CONSENT_REQUIRED"
    if consent_value.granted_at is None or consent_value.granted_at > now:
        return None, "CONSENT_REQUIRED"
    if consent_value.expires_at and consent_value.expires_at <= now:
        return None, "CONSENT_REQUIRED"
    return Consent(state, frozenset(consent_value.scopes), consent_value.granted_at,
                   consent_value.expires_at, consent_value.withdrawn_at), None


def _build_response(payload: ShadowAssessmentRequest, *, debug: bool):
    _require_enabled()
    trace_id = _trace_id(payload)
    consent_obj, consent_error = _to_consent(payload.consent,
        require_bureau_history=bool(payload.repayment_history))
    evidence_info = {"account_reference": None, "prediction_cutoff": payload.prediction_cutoff_month,
                     "months_validated": 0, "product_type": None, "provider": None,
                     "repayment_history_source_available": bool(payload.repayment_history)}
    if consent_error:
        return _blocked(trace_id, [consent_error], evidence=evidence_info)
    account_refs = {x.account_reference for x in payload.statements if x.account_reference}
    account_refs.update(x.account_reference for x in payload.repayment_history if x.account_reference)
    if payload.borrower_account_count > 1 or len(account_refs) > 1:
        return _blocked(trace_id, ["MULTI_ACCOUNT_AGGREGATION_UNRESOLVED"], evidence=evidence_info)
    from ..credit_parser.normalizer import run_equivalence_path
    statements = [x.model_dump(mode="json", exclude_none=True) for x in payload.statements]
    repayment = [x.model_dump(mode="json", exclude_none=True) for x in payload.repayment_history]
    result = run_equivalence_path(statements, repayment, consent=consent_obj,
        prediction_cutoff_month=payload.prediction_cutoff_month,
        borrower_reference=payload.borrower_reference, at=datetime.now(timezone.utc))
    if not result.eligibility or not result.eligibility.eligible_for_phase2b6_scorecard:
        response = _blocked(trace_id, _mapped_reasons(result),
            warnings=list(result.eligibility.warnings) if result.eligibility else [], evidence=evidence_info)
        if debug:
            response["trace"] = {"assembly_state": result.state, "validation": result.validation,
                "eligibility": result.eligibility, "feature_state": result.features.state if result.features else None}
        return response
    from ..shadow_scorecard.artifacts import load_scorecard
    from ..shadow_scorecard.scorer import score_validated_result
    # Phase 2G consumes the immutable Phase 2F specification, never production artifacts.
    frozen_shadow_scorecard = load_scorecard(FROZEN_SCORECARD_PATH)
    scored = score_validated_result(result, artifact=frozen_shadow_scorecard)
    evidence_info.update({"account_reference": result.account.account_reference,
        "prediction_cutoff": result.account.prediction_cutoff_month,
        "months_validated": len(result.account.monthly_records),
        "product_type": result.account.product_type.value,
        "provider": result.account.provider_name,
        "masked_account_number": result.account.masked_account_number})
    response = {
        "status": "EXPERIMENTAL_SHADOW_SCORE", "decision_use": "NOT_FOR_CREDIT_DECISION",
        "assessment_id": trace_id,
        "assessment_status": "SCORED",
        "model_version": frozen_shadow_scorecard["artifact_sha256"],
        "score": scored["score"],
        "probability_of_default": scored["pd"],
        "risk_tier": None,
        "feature_coverage": 1.0,
        "feature_values": {k: float(v) for k, v in scored["feature_values"].items()},
        "woe_values": {k: float(v["woe"]) for k, v in scored["feature_trace"].items()},
        "feature_contributions": {k: float(v["contribution"]) for k, v in scored["feature_trace"].items()},
        "feature_trace": scored["feature_trace"],
        "improvement_recommendations": [
            {"reason_code": item["code"], "feature": item["code"],
             "message": {
                 "recent_delinquency_level": "Review recent repayment records and aim to make upcoming payments on time.",
                 "months_with_delinquency": "Build a consistent on-time repayment history across future statement cycles.",
                 "payment_to_statement_ratio": "Where affordable, pay a larger share of statement balances by the due date.",
                 "mean_statement_balance": "Review outstanding statement balances and repay amounts that are manageable.",
             }[item["code"]],
             "causality_claim": False}
            for item in scored["reason_codes"]
        ],
        "document_findings": evidence_info,
        "fraud_findings": None,
        "assessment_timestamp": datetime.now(timezone.utc).isoformat(),
        "eligibility": {"eligible": True, "blocking_reasons": [],
            "warnings": list(result.eligibility.warnings)},
        "evidence": evidence_info,
        "features": {k: float(v) for k, v in scored["feature_values"].items()},
        "scorecard": {"logit": scored["logit"], "raw_pd": scored["pd"],
            "good_bad_odds": scored["good_bad_odds"],
            "experimental_shadow_score": scored["score"],
            "score_label": "Experimental Shadow Score",
            "pdo_presentation_only": True},
        "reason_codes": [{"code": x["code"], "label": x["label"],
            "direction": x["direction"], "contribution": x["contribution"]}
            for x in scored["reason_codes"]],
        "trace_id": trace_id, "model_status": MODEL_STATUS,
        "validation_scope": ["ENGINEERING_VERIFIED", "MATHEMATICALLY_RECONSTRUCTED"],
        "limitations": LIMITATIONS,
    }
    if debug:
        response["trace"] = scored
    return response


@router.get("/shadow-golden-request")
def shadow_golden_request():
    _require_enabled()
    fixture = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return {
        "borrower_reference": fixture["borrower_reference"],
        "prediction_cutoff_month": fixture["prediction_cutoff_month"],
        "statements": fixture["source_statements"],
        "repayment_history": fixture["source_repayment_history"],
        "consent": {"state": "GRANTED", "scopes": sorted(REQUIRED_SCOPES),
            "granted_at": "2026-01-01T00:00:00Z"},
        "borrower_account_count": 1,
    }


@router.post("/shadow-assess")
def shadow_assess(payload: ShadowAssessmentRequest):
    return _build_response(payload, debug=False)


@router.post("/shadow-assess/debug")
def shadow_assess_debug(payload: ShadowAssessmentRequest):
    return _build_response(payload, debug=True)


@router.post("/shadow-simulate")
def shadow_simulate(payload: ShadowSimulationRequest):
    """Compare baseline and hypothetical outputs without persisting either one."""
    _require_enabled()
    baseline = _score_feature_vector(payload.baseline.model_dump())
    scenario = _score_feature_vector(payload.scenario.model_dump())
    base_score = baseline["scorecard"]["experimental_shadow_score"]
    scenario_score = scenario["scorecard"]["experimental_shadow_score"]
    base_pd = baseline["scorecard"]["raw_pd"]
    scenario_pd = scenario["scorecard"]["raw_pd"]
    return {
        "status": "HYPOTHETICAL_ONLY",
        "decision_use": "NOT_FOR_CREDIT_DECISION",
        "baseline": baseline,
        "scenario": scenario,
        "delta": {
            "score": scenario_score - base_score,
            "raw_pd": scenario_pd - base_pd,
        },
        "persisted": False,
        "disclaimer": "What-if scenarios are hypothetical model outputs, not guaranteed future credit scores or lending decisions.",
    }
