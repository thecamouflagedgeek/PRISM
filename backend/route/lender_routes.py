from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.db import get_db
from core.session_store import get_session
from database.models import (
    Application,
    AssessmentDetail,
    Document,
    ExtractedFeature,
    RiskScore,
    SHAPExplanation,
    User,
    Consent,
    AuditEvent,
    ExperimentalAssessment,
    BankCashflowAssessment,
)
from route.experimental_assessment_routes import _assessment_payload

router = APIRouter(prefix="/lender", tags=["Lender"])
FROZEN_MODEL_NAME = "PRISM_PHASE2F_FROZEN"
class LenderCaseUpdate(BaseModel):
    action: Literal["assign_to_me", "set_status", "add_note", "request_information"]
    review_status: Literal["NEW", "IN_REVIEW", "AWAITING_DOCUMENTS", "COMPLETED"] | None = None
    note: str = Field(default="", max_length=4000)
    requested_information: list[str] = Field(default_factory=list, max_length=20)


def _case_review_events(db, application_id: int):
    return (db.query(AuditEvent)
        .filter(AuditEvent.application_id == application_id,
                AuditEvent.action.in_(["lender_case_updated", "lender_application_viewed"]))
        .order_by(AuditEvent.event_timestamp.desc(), AuditEvent.event_id.desc())
        .limit(100).all())


def _case_snapshot(db, application_id: int):
    events = [event for event in _case_review_events(db, application_id)
              if event.action == "lender_case_updated"]
    latest = events[0] if events else None
    details = latest.details or {} if latest else {}
    return {
        "review_status": details.get("review_status", "NEW"),
        "assigned_to": details.get("assigned_to"),
        "requested_information": details.get("requested_information", []),
        "updated_at": latest.event_timestamp.isoformat() if latest else None,
        "updated_by": details.get("performed_by"),
        "note_count": sum(bool((event.details or {}).get("note")) for event in events),
    }


def _is_frozen_shadow_score(score):
    return bool(score and score.model_name == FROZEN_MODEL_NAME
                and score.score_status == "EXPERIMENTAL_SHADOW_SCORE")

def require_lender(session_id: str | None = Header(None)):
    if not session_id:
        raise HTTPException(status_code=401, detail="Lender session required")
    session = get_session(session_id)
    if session is None or not session.is_authenticated:
        raise HTTPException(status_code=401, detail="Lender session required")
    if getattr(session, "role", "borrower") != "lender":
        raise HTTPException(status_code=403, detail="Lender role required")
    return session


def _latest_score_subquery():
    return (
        select(func.max(RiskScore.score_id))
        .where(RiskScore.application_id == Application.application_id)
        .where(RiskScore.model_name == FROZEN_MODEL_NAME)
        .where(RiskScore.score_status == "EXPERIMENTAL_SHADOW_SCORE")
        .correlate(Application)
        .scalar_subquery()
    )


def _application_summary(application, user, score, document_count, db=None):
    result = {
        "application_id": application.application_id,
        "application_date": application.application_date,
        "application_status": application.application_status,
        "borrower_phone": user.phone,
        "risk_score": score.credit_score if _is_frozen_shadow_score(score) else None,
        "probability_of_default": score.probability_default if _is_frozen_shadow_score(score) else None,
        "risk_tier": None,
        "assessment_status": "SCORED" if _is_frozen_shadow_score(score) else "INSUFFICIENT_EVIDENCE",
        "document_count": document_count,
    }
    experimental = None
    if db is not None:
        experimental = (db.query(ExperimentalAssessment)
            .filter(ExperimentalAssessment.application_id == application.application_id)
            .order_by(ExperimentalAssessment.created_at.desc()).first())
    if experimental:
        payload = _assessment_payload(experimental)
        result.update({
            "assessment_id": experimental.assessment_id,
            "assessment_status": experimental.assessment_status,
            "risk_score": payload["score"],
            "probability_of_default": payload["probability_of_default"],
            "model_version": experimental.model_version,
            "risk_tier": None,
        })
    if db is not None:
        bank = db.query(BankCashflowAssessment).filter_by(application_id=application.application_id).order_by(BankCashflowAssessment.score.isnot(None).desc(), BankCashflowAssessment.created_at.desc(), BankCashflowAssessment.assessment_id.desc()).first()
        result['bank_health_index'] = bank.score if bank else None
        result['bank_assessment_id'] = bank.assessment_id if bank else None
        result['bank_methodology'] = bank.model_version if bank else None
        bank_payload = bank.result_json or {} if bank else {}
        fraud = bank_payload.get("fraud_findings") or {}
        result["bank_assessment_status"] = bank.assessment_status if bank else None
        result["bank_assessment_timestamp"] = bank.created_at.isoformat() if bank and bank.created_at else None
        result["bank_months_observed"] = bank_payload.get("months_observed", 0)
        result["bank_transaction_count"] = bank_payload.get("transaction_count", 0)
        result["bank_fraud_status"] = fraud.get("fraud_status")
        result["bank_fraud_flag_count"] = len(fraud.get("flags") or [])
        result["review"] = _case_snapshot(db, application.application_id)
    return result


@router.get("/applications")
def list_applications(db: Session = Depends(get_db), _session=Depends(require_lender)):
    latest_score = _latest_score_subquery()
    document_count = (
        db.query(func.count(Document.document_id))
        .filter(Document.application_id == Application.application_id)
        .correlate(Application)
        .scalar_subquery()
    )
    rows = (
        db.query(Application, User, RiskScore, document_count.label("document_count"))
        .join(User, User.user_id == Application.user_id)
        .outerjoin(RiskScore, RiskScore.score_id == latest_score)
        .order_by(Application.application_date.desc())
        .all()
    )
    return {"applications": [_application_summary(*row, db=db) for row in rows]}


@router.get("/applications/{application_id}")
def get_application_assessment(application_id: int, db: Session = Depends(get_db), _session=Depends(require_lender)):
    application_row = (
        db.query(Application, User)
        .join(User, User.user_id == Application.user_id)
        .filter(Application.application_id == application_id)
        .first()
    )
    if application_row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    application, user = application_row
    db.add(AuditEvent(application_id=application_id, action="lender_application_viewed",
        entity="application", status="success", event_timestamp=datetime.utcnow(),
        details={"performed_by": _session.phone_number, "access_scope": "borrower_application_review"}))
    db.commit()
    score = (
        db.query(RiskScore)
        .filter(RiskScore.application_id == application_id)
        .filter(RiskScore.model_name == FROZEN_MODEL_NAME)
        .filter(RiskScore.score_status == "EXPERIMENTAL_SHADOW_SCORE")
        .order_by(RiskScore.score_id.desc())
        .first()
    )
    details = db.query(AssessmentDetail).filter(AssessmentDetail.score_id == score.score_id).first() if score else None
    shap_explanations = (db.query(SHAPExplanation).filter(SHAPExplanation.score_id == score.score_id)
        .order_by(SHAPExplanation.feature_rank.asc()).all()) if score else []
    documents = db.query(Document).filter(Document.application_id == application_id).all()
    features = db.query(ExtractedFeature).filter(ExtractedFeature.application_id == application_id).all()
    experimental = (db.query(ExperimentalAssessment)
        .filter(ExperimentalAssessment.application_id == application_id)
        .order_by(ExperimentalAssessment.created_at.desc()).first())
    experimental_payload = _assessment_payload(experimental) if experimental else None
    financial_health_event = (db.query(AuditEvent)
        .filter(AuditEvent.application_id == application_id)
        .filter(AuditEvent.action == "financial_document_analysis")
        .order_by(AuditEvent.event_timestamp.desc()).first())
    bank_cashflow = (db.query(BankCashflowAssessment)
        .filter(BankCashflowAssessment.application_id == application_id)
        .order_by(BankCashflowAssessment.score.isnot(None).desc(), BankCashflowAssessment.created_at.desc(), BankCashflowAssessment.assessment_id.desc()).first())

    review_events = _case_review_events(db, application_id)
    review_history = [{
        "event_id": event.event_id,
        "action": event.action,
        "timestamp": event.event_timestamp.isoformat(),
        "performed_by": (event.details or {}).get("performed_by"),
        "review_status": (event.details or {}).get("review_status"),
        "assigned_to": (event.details or {}).get("assigned_to"),
        "note": (event.details or {}).get("note"),
        "requested_information": (event.details or {}).get("requested_information", []),
    } for event in review_events]

    return {
        "application_id": application.application_id,
        "application": {
            "application_id": application.application_id,
            "application_date": application.application_date,
            "application_status": application.application_status,
            "borrower_phone": user.phone,
        },
        "credit_risk": ({
            "status": "EXPERIMENTAL_SHADOW_SCORE",
            "score_status": score.score_status,
            "risk_score": score.credit_score,
            "probability_of_default": score.probability_default,
            "risk_tier": None,
            "model_metadata": {"model_name": score.model_name, "model_version": score.model_version},
            "reason_codes": [item.generated_reason for item in shap_explanations if item.generated_reason],
            "shap_explanations": [
                {
                    "feature_name": item.feature_name,
                    "shap_value": item.shap_value,
                    "score_contribution": item.score_contribution,
                    "contribution_type": item.contribution_type,
                    "feature_rank": item.feature_rank,
                    "generated_reason": item.generated_reason,
                }
                for item in shap_explanations
            ],
        } if _is_frozen_shadow_score(score) else ({
            "status": experimental_payload["assessment_status"],
            "assessment_id": experimental.assessment_id,
            "risk_score": experimental_payload["score"],
            "probability_of_default": experimental_payload["probability_of_default"],
            "risk_tier": None,
            "model_metadata": {"model_name": experimental.model_name, "model_version": experimental.model_version},
            "reason_codes": experimental_payload["reason_codes"],
            "feature_values": experimental.feature_values,
            "woe_values": experimental.woe_values,
            "feature_contributions": experimental.feature_contributions,
            "assessment_timestamp": experimental.created_at.isoformat(),
        } if experimental else {"status": application.application_status or "INSUFFICIENT_EVIDENCE", "risk_score": None, "probability_of_default": None, "risk_tier": None})),
        "experimental_assessment": experimental_payload,
        "financial_health": ({**(financial_health_event.details or {}),
            "analysis_id": financial_health_event.event_id,
            "analyzed_at": financial_health_event.event_timestamp.isoformat()} if financial_health_event else None),
        "bank_cashflow_assessment": (dict(bank_cashflow.result_json or {},
            assessment_id=bank_cashflow.assessment_id, application_id=bank_cashflow.application_id,
            assessment_type=bank_cashflow.assessment_type, model_version=bank_cashflow.model_version,
            status=bank_cashflow.assessment_status, score=bank_cashflow.score,
            pd=None, assessment_timestamp=bank_cashflow.created_at.isoformat()) if bank_cashflow else None),
        "review": _case_snapshot(db, application_id),
        "review_history": review_history,
        "consent": (lambda c: {"bank": c.bank_consent, "salary": c.salary_consent, "utility": c.utility_consent, "dpdpa": c.dpdpa_consent})(db.query(Consent).filter(Consent.application_id == application_id).first()) if db.query(Consent).filter(Consent.application_id == application_id).first() else {},
        "fraud_risk": details.fraud_risk if details else {},
        "document_risk": details.document_risk if details else {},
        "documents": [
            {
                "document_id": document.document_id,
                "document_type": document.document_type,
                "file_name": document.file_name,
                "upload_timestamp": document.upload_timestamp,
                "processing_status": document.processing_status,
                "parser_version": document.parser_version,
            }
            for document in documents
        ],
        "features": [
            {
                "feature_name": feature.feature_name,
                "feature_value": feature.feature_value,
                "feature_source": feature.feature_source,
                "created_at": feature.created_at,
            }
            for feature in features
        ],
    }


@router.post("/applications/{application_id}/case-updates")
def update_lender_case(application_id: int, update: LenderCaseUpdate,
        db: Session = Depends(get_db), _session=Depends(require_lender)):
    application = db.query(Application).filter(Application.application_id == application_id).first()
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    current = _case_snapshot(db, application_id)
    note = update.note.strip()
    requested = [item.strip() for item in update.requested_information if item.strip()]
    review_status = current["review_status"]
    assigned_to = current["assigned_to"]
    requested_information = current["requested_information"]

    if update.action == "assign_to_me":
        assigned_to = _session.phone_number
        if review_status == "NEW":
            review_status = "IN_REVIEW"
    elif update.action == "set_status":
        if update.review_status is None:
            raise HTTPException(status_code=422, detail="Choose a review status")
        review_status = update.review_status
    elif update.action == "add_note" and not note:
        raise HTTPException(status_code=422, detail="Enter a note before saving")
    elif update.action == "request_information":
        if not requested:
            raise HTTPException(status_code=422, detail="List at least one item to request")
        review_status = "AWAITING_DOCUMENTS"
        requested_information = requested

    event = AuditEvent(application_id=application_id, action="lender_case_updated",
        entity="application", status="success", event_timestamp=datetime.utcnow(),
        details={"action": update.action, "review_status": review_status,
            "assigned_to": assigned_to, "requested_information": requested_information,
            "note": note or None, "performed_by": _session.phone_number})
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"review": _case_snapshot(db, application_id), "event_id": event.event_id,
        "message": "Case update recorded in the audit trail. PRISM has not contacted the borrower."}


@router.get("/audit-events")
def list_audit_events(db: Session = Depends(get_db), _session=Depends(require_lender)):
    rows = db.query(AuditEvent).order_by(AuditEvent.event_timestamp.desc()).limit(500).all()
    return {"events": [{"event_id": row.event_id, "application_id": row.application_id, "action": row.action,
        "entity": row.entity, "status": row.status, "timestamp": row.event_timestamp.isoformat(), "details": row.details or {}} for row in rows]}
