"""Fail-closed score calculation from validated Phase 2E output only."""
from __future__ import annotations
import math
from scipy.special import expit
from .artifacts import load_scorecard, FEATURE_ORDER
from .woe import transform_feature
from .score_scaling import score_from_pd
from .reason_codes import rank_reasons


class ShadowScoreError(ValueError):
    def __init__(self, code: str, reasons=()):
        self.code = code
        self.reasons = tuple(reasons)
        super().__init__(f"{code}: {', '.join(self.reasons)}")


def score_validated_result(result, *, artifact=None) -> dict:
    """Accept AssemblyResult from Phase 2E parser→Phase 2D validation path."""
    if not (hasattr(result, "eligibility") and hasattr(result, "features") and hasattr(result, "account") and hasattr(result, "validation")):
        raise ShadowScoreError("SHADOW_SCORE_INELIGIBLE", ("UNVALIDATED_INPUT_TYPE",))
    eligibility, features = result.eligibility, result.features
    if result.account is None or result.validation is None or not result.validation.valid:
        blockers = getattr(result.validation, "blockers", ()) if result.validation else ()
        raise ShadowScoreError("SHADOW_SCORE_INELIGIBLE", blockers or ("PHASE2D_VALIDATION_REQUIRED",))
    if not eligibility or not eligibility.eligible_for_phase2b6_scorecard:
        raise ShadowScoreError("SHADOW_SCORE_INELIGIBLE", getattr(eligibility, "blocking_reasons", ()) or ("NOT_ELIGIBLE",))
    if not features or features.state != "COMPUTABLE" or features.values is None or features.provenance is None:
        raise ShadowScoreError("SHADOW_SCORE_INELIGIBLE", getattr(features, "blockers", ()) or ("FEATURES_NOT_COMPUTABLE",))
    values = features.values
    if tuple(k for k in FEATURE_ORDER if k in values) != tuple(FEATURE_ORDER) or set(values) != set(FEATURE_ORDER):
        raise ShadowScoreError("SHADOW_SCORE_INELIGIBLE", ("FEATURE_SET_OR_ORDER_INVALID",))
    if set(features.provenance) != set(FEATURE_ORDER) or any(not features.provenance[k] for k in FEATURE_ORDER):
        raise ShadowScoreError("SHADOW_SCORE_INELIGIBLE", ("PROVENANCE_INCOMPLETE",))
    artifact = artifact or load_scorecard()
    trace = {}
    woe = {}
    try:
        for feature in FEATURE_ORDER:
            bin_id, value = transform_feature(values[feature], artifact["features"][feature])
            woe[feature] = value
            trace[feature] = {
                "raw_feature_value": str(values[feature]),
                "bin_id": bin_id,
                "bin": next(b for b in artifact["features"][feature]["bins"] if b["bin_id"] == bin_id),
                "woe": value,
                "coefficient": float(artifact["logistic_regression"]["coefficients"][feature]),
                "contribution": float(artifact["logistic_regression"]["coefficients"][feature]) * value,
                "feature_provenance": features.provenance[feature],
            }
    except (ValueError, TypeError, StopIteration) as exc:
        raise ShadowScoreError("UNMAPPABLE_FROZEN_BIN", (str(exc),)) from exc
    lr = artifact["logistic_regression"]
    intercept = float(lr["intercept"])
    contributions = {f: trace[f]["contribution"] for f in FEATURE_ORDER}
    logit = intercept + math.fsum(contributions[f] for f in FEATURE_ORDER)
    pd = float(expit(logit))
    odds, score = score_from_pd(pd)
    account = result.account
    return {
        "result_type": "EXPERIMENTAL_SHADOW_SCORE",
        "use_label": "NOT_FOR_CREDIT_DECISION",
        "source_phase": "Phase 2B.6 frozen raw LR PD; Phase 2F shadow-only PDO presentation",
        "artifact_sha256": artifact["artifact_sha256"],
        "borrower_reference": account.borrower_reference,
        "account_reference": account.account_reference,
        "prediction_cutoff": account.prediction_cutoff_month,
        "source_records": [s.source_document_id for s in account.evidence_sources],
        "normalized_months": [{
            "month": r.statement_month,
            "statement_balance": str(r.statement_balance.value),
            "payment_amount": str(r.payment_amount.value),
            "repayment_status": r.repayment_status.status.value if r.repayment_status.status else None,
            "delinquency_level": r.repayment_status.delinquency_level,
            "source_record_ids": list(r.source_document_ids),
        } for r in account.monthly_records],
        "feature_values": {k: str(values[k]) for k in FEATURE_ORDER},
        "feature_states": {k: "VALID" for k in FEATURE_ORDER},
        "feature_provenance": features.provenance,
        "bin_assignments": {k: trace[k]["bin_id"] for k in FEATURE_ORDER},
        "woe_values": woe,
        "intercept": intercept,
        "coefficients": {k: float(lr["coefficients"][k]) for k in FEATURE_ORDER},
        "feature_contributions": contributions,
        "logit": logit,
        "pd": pd,
        "good_bad_odds": odds,
        "score": score,
        "reason_codes": rank_reasons(contributions, trace),
        "feature_trace": trace,
        "eligibility": {"eligible": True, "blocking_reasons": []},
        "risk_tier": None,
        "calibration_applied": False,
        "fraud_score_combined": False,
    }
