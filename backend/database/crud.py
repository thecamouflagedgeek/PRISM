import hashlib
from datetime import datetime

from sqlalchemy.orm import Session

from database.models import (
    User,
    Application,
    Consent,
    Document,
    ExtractedFeature
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

    document = Document(
        application_id=application_id,
        document_type=document_type,
        file_name=file_name,
        storage_path=storage_path,
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