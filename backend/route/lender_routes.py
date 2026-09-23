from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import (
    Application,
    AssessmentDetail,
    Document,
    ExtractedFeature,
    RiskScore,
    SHAPExplanation,
    User,
)

router = APIRouter(prefix="/lender", tags=["Lender"])


def _latest_score_subquery():
    return (
        select(func.max(RiskScore.score_id))
        .where(RiskScore.application_id == Application.application_id)
        .correlate(Application)
        .scalar_subquery()
    )


def _application_summary(application, user, score, document_count):
    return {
        "application_id": application.application_id,
        "application_date": application.application_date,
        "application_status": application.application_status,
        "borrower_phone": user.phone,
        "risk_score": score.credit_score if score else None,
        "probability_of_default": score.probability_default if score else None,
        "risk_tier": score.risk_tier if score else None,
        "document_count": document_count,
    }


@router.get("/applications")
def list_applications(db: Session = Depends(get_db)):
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
        .filter(RiskScore.score_id.isnot(None))
        .order_by(Application.application_date.desc())
        .all()
    )
    return {"applications": [_application_summary(*row) for row in rows]}


@router.get("/applications/{application_id}")
def get_application_assessment(application_id: int, db: Session = Depends(get_db)):
    application_row = (
        db.query(Application, User)
        .join(User, User.user_id == Application.user_id)
        .filter(Application.application_id == application_id)
        .first()
    )
    if application_row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    application, user = application_row
    score = (
        db.query(RiskScore)
        .filter(RiskScore.application_id == application_id)
        .order_by(RiskScore.score_id.desc())
        .first()
    )
    if score is None:
        raise HTTPException(status_code=404, detail="No persisted assessment found for this application")

    details = db.query(AssessmentDetail).filter(AssessmentDetail.score_id == score.score_id).first()
    shap_explanations = (
        db.query(SHAPExplanation)
        .filter(SHAPExplanation.score_id == score.score_id)
        .order_by(SHAPExplanation.feature_rank.asc())
        .all()
    )
    documents = db.query(Document).filter(Document.application_id == application_id).all()
    features = db.query(ExtractedFeature).filter(ExtractedFeature.application_id == application_id).all()

    return {
        "application_id": application.application_id,
        "application": {
            "application_id": application.application_id,
            "application_date": application.application_date,
            "application_status": application.application_status,
            "borrower_phone": user.phone,
        },
        "credit_risk": {
            "risk_score": score.credit_score,
            "probability_of_default": score.probability_default,
            "risk_tier": score.risk_tier,
            "confidence": {"confidence_pct": score.confidence_score},
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
        },
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
