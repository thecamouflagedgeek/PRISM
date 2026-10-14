from sqlalchemy import (
    Column,
    CheckConstraint,
    Integer,
    String,
    Boolean,
    TIMESTAMP,
    Text,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

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

    # ==========================
# RISK SCORES
# ==========================

class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = {"schema": "prism"}

    score_id = Column(Integer, primary_key=True)

    application_id = Column(
        Integer,
        ForeignKey("prism.applications.application_id")
    )

    credit_score = Column(Integer)

    probability_default = Column(Numeric(5, 4))

    confidence_score = Column(Numeric(5, 2))

    risk_tier = Column(String(20))

    generated_at = Column(TIMESTAMP)

    model_name = Column(String(50))

    model_version = Column(String(20))

    score_status = Column(String(20))

# ==========================
# SHAP EXPLANATIONS
# ==========================

class SHAPExplanation(Base):
    __tablename__ = "shap_explanations"
    __table_args__ = {"schema": "prism"}

    explanation_id = Column(Integer, primary_key=True)

    score_id = Column(
        Integer,
        ForeignKey("prism.risk_scores.score_id")
    )

    feature_name = Column(String(100))

    # Optional SHAP value in log-odds space; null for scorecard-only explanations
    shap_value = Column(Numeric(10, 6))

    # Effect on credit score in score points
    score_contribution = Column(Numeric(10, 2))

    contribution_type = Column(String(20))

    feature_rank = Column(Integer)

    generated_reason = Column(Text)

    created_at = Column(TIMESTAMP)


# ==========================
# ASSESSMENT DETAILS
# ==========================
class AssessmentDetail(Base):
    """Durable non-credit outputs for a persisted risk-score run."""
    __tablename__ = "assessment_details"
    __table_args__ = {"schema": "prism"}

    assessment_detail_id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("prism.applications.application_id"), nullable=False)
    score_id = Column(Integer, ForeignKey("prism.risk_scores.score_id"), nullable=False, unique=True)
    fraud_risk = Column(JSONB, nullable=False)
    document_risk = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("idx_prism_audit_events_app_time", "application_id", text("event_timestamp DESC")),
        {"schema": "prism"},
    )

    event_id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("prism.applications.application_id"), nullable=False)
    action = Column(String(120), nullable=False)
    entity = Column(String(80), nullable=False)
    status = Column(String(20), nullable=False)
    event_timestamp = Column(TIMESTAMP, nullable=False)
    details = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))


class ExperimentalAssessment(Base):
    """Versioned frozen-research result, kept separate from generic risk_scores."""
    __tablename__ = "experimental_assessments"
    __table_args__ = (
        UniqueConstraint("application_id", "input_sha256", name="uq_experimental_assessment_application_input"),
        Index("ix_experimental_assessments_app_created", "application_id", "created_at"),
        Index("ix_experimental_assessments_user", "user_id"),
        {"schema": "prism"},
    )

    assessment_id = Column(String(36), primary_key=True)
    application_id = Column(Integer, ForeignKey("prism.applications.application_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("prism.users.user_id"), nullable=False)
    input_sha256 = Column(String(64), nullable=False)
    model_name = Column(String(80), nullable=False)
    model_version = Column(String(64), nullable=False)
    assessment_status = Column(String(40), nullable=False)
    prediction_cutoff_month = Column(String(7), nullable=False)
    feature_values = Column(JSONB)
    woe_values = Column(JSONB)
    feature_contributions = Column(JSONB)
    logit = Column(Numeric(24, 16))
    probability_default = Column(Numeric(24, 16))
    score = Column(Numeric(24, 12))
    reason_codes = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    recommendations = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    source_document_ids = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    evidence_validation = Column(JSONB, nullable=False)
    document_findings = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    consent_record = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False)


class BankCashflowAssessment(Base):
    """Additive persistence for the separate, non-PD bank health index."""
    __tablename__ = "bank_cashflow_assessments"
    __table_args__ = (
        UniqueConstraint("application_id", "input_sha256", name="uq_bank_cashflow_app_input"),
        Index("ix_bank_cashflow_app_created", "application_id", "created_at"),
        Index("ix_bank_cashflow_user", "user_id"),
        CheckConstraint("probability_default IS NULL", name="ck_bank_cashflow_no_pd"),
        CheckConstraint("score IS NULL OR (score >= 300 AND score <= 900)", name="ck_bank_cashflow_score_range"),
        {"schema": "prism"},
    )
    assessment_id = Column(String(36), primary_key=True)
    application_id = Column(Integer, ForeignKey("prism.applications.application_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("prism.users.user_id"), nullable=False)
    input_sha256 = Column(String(64), nullable=False)
    assessment_type = Column(String(40), nullable=False)
    model_version = Column(String(64), nullable=False)
    assessment_status = Column(String(40), nullable=False)
    evidence_document_ids = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    feature_values = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    score = Column(Integer)
    probability_default = Column(Numeric(10, 8))
    feature_contributions = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    reason_codes = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    validation_status = Column(String(32), nullable=False)
    result_json = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False)
