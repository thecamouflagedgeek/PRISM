-- Additive frozen research assessment store. Existing tables and records remain untouched.
CREATE TABLE IF NOT EXISTS prism.experimental_assessments (
    assessment_id VARCHAR(36) PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES prism.applications(application_id),
    user_id BIGINT NOT NULL REFERENCES prism.users(user_id),
    input_sha256 CHAR(64) NOT NULL,
    model_name VARCHAR(80) NOT NULL,
    model_version CHAR(64) NOT NULL,
    assessment_status VARCHAR(40) NOT NULL,
    prediction_cutoff_month CHAR(7) NOT NULL,
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
    CONSTRAINT uq_experimental_assessment_application_input UNIQUE (application_id, input_sha256)
);

CREATE INDEX IF NOT EXISTS ix_experimental_assessments_app_created
    ON prism.experimental_assessments (application_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_experimental_assessments_user
    ON prism.experimental_assessments (user_id);
