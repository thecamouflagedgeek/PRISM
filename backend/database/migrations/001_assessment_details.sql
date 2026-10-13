CREATE TABLE IF NOT EXISTS prism.assessment_details (
    assessment_detail_id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES prism.applications(application_id),
    score_id INTEGER NOT NULL UNIQUE REFERENCES prism.risk_scores(score_id),
    fraud_risk JSONB NOT NULL,
    document_risk JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_assessment_details_application_id
    ON prism.assessment_details (application_id);
