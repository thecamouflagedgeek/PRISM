-- Additive store for the distinct experimental bank financial-health index.
-- This table has no link to credit-card scores and contains no PD output.
CREATE TABLE IF NOT EXISTS prism.bank_cashflow_assessments (
    assessment_id VARCHAR(36) PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES prism.applications(application_id),
    user_id BIGINT NOT NULL REFERENCES prism.users(user_id),
    input_sha256 CHAR(64) NOT NULL,
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
    CONSTRAINT ck_bank_cashflow_score_range CHECK (score IS NULL OR (score >= 300 AND score <= 900))
);
CREATE INDEX IF NOT EXISTS ix_bank_cashflow_app_created
    ON prism.bank_cashflow_assessments(application_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_bank_cashflow_user
    ON prism.bank_cashflow_assessments(user_id);
