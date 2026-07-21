from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    TIMESTAMP,
    Text,
    ForeignKey
)

from database.db import Base


# ==========================
# USERS
# ==========================
class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "prism"}

    user_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    email = Column(String)
    phone = Column(String, unique=True)
    created_at = Column(TIMESTAMP)


# ==========================
# APPLICATIONS
# ==========================
class Application(Base):
    __tablename__ = "applications"
    __table_args__ = {"schema": "prism"}

    application_id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("prism.users.user_id")
    )

    application_date = Column(TIMESTAMP)
    application_status = Column(String)


# ==========================
# CONSENTS
# ==========================
class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = {"schema": "prism"}

    consent_id = Column(Integer, primary_key=True)

    application_id = Column(
        Integer,
        ForeignKey("prism.applications.application_id")
    )

    bank_consent = Column(Boolean)

    salary_consent = Column(Boolean)

    utility_consent = Column(Boolean)

    dpdpa_consent = Column(Boolean)

    consent_version = Column(String)

    consent_timestamp = Column(TIMESTAMP)


# ==========================
# DOCUMENTS
# ==========================
class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "prism"}

    document_id = Column(Integer, primary_key=True)

    application_id = Column(
        Integer,
        ForeignKey("prism.applications.application_id")
    )

    document_type = Column(String)

    file_name = Column(String)

    storage_path = Column(Text)

    upload_timestamp = Column(TIMESTAMP)

    document_hash = Column(String)

    parser_version = Column(String)

    processing_status = Column(String)

    storage_provider = Column(String)

# ==========================
# EXTRACTED FEATURES
# ==========================

class ExtractedFeature(Base):
    __tablename__ = "extracted_features"
    __table_args__ = {"schema": "prism"}

    feature_id = Column(Integer, primary_key=True)

    application_id = Column(
        Integer,
        ForeignKey("prism.applications.application_id")
    )

    feature_name = Column(String)

    feature_value = Column(String)

    feature_source = Column(String)

    created_at = Column(TIMESTAMP)