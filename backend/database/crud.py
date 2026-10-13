import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from database.models import (
    User,
    Application,
    Consent,
    Document,
    ExtractedFeature,
    SHAPExplanation,
    RiskScore,
    AssessmentDetail,
    AuditEvent,
)


# ==========================
# USERS
# ==========================

def get_user_by_phone(db: Session, phone: str):

    return (
        db.query(User)
        .filter(User.phone == phone)
        .first()
    )


def create_user(db: Session, phone: str):

    user = User(
    phone=phone,
    created_at=datetime.utcnow()
)

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


# ==========================
# APPLICATIONS
# ==========================

def create_application(db: Session, user_id: int):

    application = Application(
        user_id=user_id,
        application_date=datetime.utcnow(),
        application_status="IN_PROGRESS"
    )

    db.add(application)
    db.commit()
    db.refresh(application)

    return application


# ==========================
# CONSENTS
# ==========================

def save_consent(
    db: Session,
    application_id: int,
    bank_consent: bool,
    salary_consent: bool,
    utility_consent: bool,
    dpdpa_consent: bool,
):
    # ----------------------------------
    # Check if consent already exists
    # ----------------------------------

    consent = (
        db.query(Consent)
        .filter(
            Consent.application_id == application_id
        )
        .first()
    )

    # ----------------------------------
    # UPDATE Existing Record
    # ----------------------------------

    if consent:

        consent.bank_consent = bank_consent
        consent.salary_consent = salary_consent
        consent.utility_consent = utility_consent
        consent.dpdpa_consent = dpdpa_consent
        consent.consent_version = "v1.0"
        consent.consent_timestamp = datetime.utcnow()

        db.commit()
        db.refresh(consent)

        return consent

    # ----------------------------------
    # CREATE New Record
    # ----------------------------------

    consent = Consent(
        application_id=application_id,
        bank_consent=bank_consent,
        salary_consent=salary_consent,
        utility_consent=utility_consent,
        dpdpa_consent=dpdpa_consent,
        consent_version="v1.0",
        consent_timestamp=datetime.utcnow()
    )

    db.add(consent)

    db.commit()

    db.refresh(consent)

    return consent

def save_risk_score(
    db: Session,
    application_id: int,
    result: dict,
):
    confidence = result.get("confidence", {})

    score = RiskScore(
        application_id=application_id,
        credit_score=result["risk_score"],
        probability_default=result["probability_of_default"],
        confidence_score=confidence.get("confidence_pct", float(confidence.get("score", 0) or 0) * 100),
        risk_tier=result["risk_tier"],
        generated_at=datetime.utcnow(),
        model_name="WoE_Logistic_Scorecard",
        model_version="v1.0",
        score_status="ACTIVE",
    )

    db.add(score)
    db.commit()
    db.refresh(score)

    return score
def save_shap_explanations(
    db: Session,
    score_id: int,
    explanations: list,
):
    """
    Persist feature-level explanation rows linked to the score that generated them.
    Scorecard contributions are recorded separately; true SHAP values may be null.
    """

    saved_explanations = []

    for explanation in explanations:
        record = SHAPExplanation(
        score_id=score_id,
        feature_name=explanation["feature_name"],
        shap_value=explanation.get("shap_value"),
        score_contribution=explanation["score_contribution"],
        contribution_type=explanation["contribution_type"],
        feature_rank=explanation["feature_rank"],
        generated_reason=explanation["generated_reason"],
        created_at=datetime.utcnow(),
    )

        db.add(record)
        saved_explanations.append(record)

    db.commit()

    for record in saved_explanations:
        db.refresh(record)

    return saved_explanations


def save_assessment_details(
    db: Session,
    application_id: int,
    score_id: int,
    fraud_risk: dict,
    document_risk: dict,
):
    """Persist outputs already calculated by assess_borrower; never recompute them."""
    details = AssessmentDetail(
        application_id=application_id,
        score_id=score_id,
        fraud_risk=fraud_risk,
        document_risk=document_risk,
        created_at=datetime.utcnow(),
    )
    db.add(details)
    db.commit()
    db.refresh(details)
    return details


def mark_application_assessed(db: Session, application_id: int):
    application = db.query(Application).filter(Application.application_id == application_id).first()
    if application is None:
        return None
    application.application_status = "ASSESSED"
    db.commit()
    db.refresh(application)
    return application
# ==========================
# DOCUMENTS
# ==========================

def save_document(
    db: Session,
    application_id: int,
    document_type: str,
    file_name: str,
    storage_path: str,
    parser_version: str = "v1.0",
    storage_provider: str = "LOCAL",
):
    # Generate hash from file path + timestamp
    with open(storage_path, "rb") as f:
        document_hash = hashlib.sha256(
            f.read()
        ).hexdigest()

    source_path = Path(storage_path)
    document_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    safe_suffix = source_path.suffix.lower()[:10]
    storage_root = Path(os.getenv("PRISM_DOCUMENT_STORAGE_ROOT", Path(__file__).resolve().parents[1] / "storage"))
    storage_dir = storage_root / f"application_{application_id}"
    storage_dir.mkdir(parents=True, exist_ok=True)
    durable_path = storage_dir / f"{document_hash[:20]}_{uuid4().hex[:8]}{safe_suffix}"
    shutil.copyfile(source_path, durable_path)

    document = Document(
        application_id=application_id,
        document_type=document_type,
        file_name=file_name,
        storage_path=str(durable_path),
        upload_timestamp=datetime.utcnow(),
        document_hash=document_hash,
        parser_version=parser_version,
        processing_status="UPLOADED",
        storage_provider=storage_provider
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def update_document_status(
    db: Session,
    document_id: int,
    status: str
):

    document = (
        db.query(Document)
        .filter(Document.document_id == document_id)
        .first()
    )

    if document is None:
        return None

    document.processing_status = status

    db.commit()
    db.refresh(document)

    return document

def save_features(
    db: Session,
    application_id: int,
    feature_source: str,
    features: dict,
):
    """
    Saves all extracted features for a document.

    feature_source:
        BANK
        SALARY
        UTILITY
    """

    if features is None:
        return

    for feature_name, feature_value in features.items():

        db_feature = ExtractedFeature(

            application_id=application_id,

            feature_name=feature_name,

            feature_value=str(feature_value),

            feature_source=feature_source,

            created_at=datetime.utcnow()

        )

        db.add(db_feature)

    db.commit()


def save_audit_event(db: Session, application_id: int, action: str, entity: str, status: str = "success", details: dict | None = None):
    event = AuditEvent(application_id=application_id, action=action, entity=entity, status=status.lower(),
        event_timestamp=datetime.utcnow(), details=details or {})
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
