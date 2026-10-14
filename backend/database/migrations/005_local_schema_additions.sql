-- Add only the persistence objects missing from the inspected legacy schema.
-- Core tables and prism.audit_logs are intentionally left unchanged.
BEGIN;

CREATE TABLE prism.audit_events (
    event_id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES prism.applications(application_id),
    action VARCHAR(120) NOT NULL,
    entity VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    event_timestamp TIMESTAMP NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_prism_audit_events_app_time
    ON prism.audit_events (application_id, event_timestamp DESC);

CREATE TABLE prism.experimental_assessments (
    assessment_id VARCHAR(36) PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES prism.applications(application_id),
    user_id INTEGER NOT NULL REFERENCES prism.users(user_id),
    input_sha256 VARCHAR(64) NOT NULL,
    model_name VARCHAR(80) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    assessment_status VARCHAR(40) NOT NULL,
    prediction_cutoff_month VARCHAR(7) NOT NULL,
    feature_values JSONB,
    woe_values JSONB,
    feature_contributions JSONB,
    logit NUMERIC(24,16),
    probability_default NUMERIC(24,16),
    score NUMERIC(24,12),
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_validation JSONB NOT NULL,
    document_findings JSONB NOT NULL DEFAULT '{}'::jsonb,
    consent_record JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_experimental_assessment_application_input
        UNIQUE (application_id, input_sha256)
);
CREATE INDEX ix_experimental_assessments_app_created
    ON prism.experimental_assessments (application_id, created_at);
CREATE INDEX ix_experimental_assessments_user
    ON prism.experimental_assessments (user_id);

CREATE TABLE prism.bank_cashflow_assessments (
    assessment_id VARCHAR(36) PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES prism.applications(application_id),
    user_id INTEGER NOT NULL REFERENCES prism.users(user_id),
    input_sha256 VARCHAR(64) NOT NULL,
    assessment_type VARCHAR(40) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    assessment_status VARCHAR(40) NOT NULL,
    evidence_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    feature_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    score INTEGER,
    probability_default NUMERIC(10,8),
    feature_contributions JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    validation_status VARCHAR(32) NOT NULL,
    result_json JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_bank_cashflow_app_input UNIQUE (application_id, input_sha256),
    CONSTRAINT ck_bank_cashflow_no_pd CHECK (probability_default IS NULL),
    CONSTRAINT ck_bank_cashflow_score_range
        CHECK (score IS NULL OR (score >= 300 AND score <= 900))
);
CREATE INDEX ix_bank_cashflow_app_created
    ON prism.bank_cashflow_assessments (application_id, created_at);
CREATE INDEX ix_bank_cashflow_user
    ON prism.bank_cashflow_assessments (user_id);

COMMIT;
