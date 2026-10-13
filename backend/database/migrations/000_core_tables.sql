CREATE SCHEMA IF NOT EXISTS prism;

CREATE TABLE IF NOT EXISTS prism.users (
    user_id BIGSERIAL PRIMARY KEY, full_name VARCHAR, email VARCHAR, phone VARCHAR UNIQUE, created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS prism.applications (
    application_id BIGSERIAL PRIMARY KEY, user_id BIGINT REFERENCES prism.users(user_id),
    application_date TIMESTAMP, application_status VARCHAR
);
CREATE TABLE IF NOT EXISTS prism.consents (
    consent_id BIGSERIAL PRIMARY KEY, application_id BIGINT REFERENCES prism.applications(application_id),
    bank_consent BOOLEAN, salary_consent BOOLEAN, utility_consent BOOLEAN, dpdpa_consent BOOLEAN,
    consent_version VARCHAR, consent_timestamp TIMESTAMP
);
CREATE TABLE IF NOT EXISTS prism.documents (
    document_id BIGSERIAL PRIMARY KEY, application_id BIGINT REFERENCES prism.applications(application_id),
    document_type VARCHAR, file_name VARCHAR, storage_path TEXT, upload_timestamp TIMESTAMP,
    document_hash VARCHAR, parser_version VARCHAR, processing_status VARCHAR, storage_provider VARCHAR
);
CREATE TABLE IF NOT EXISTS prism.extracted_features (
    feature_id BIGSERIAL PRIMARY KEY, application_id BIGINT REFERENCES prism.applications(application_id),
    feature_name VARCHAR, feature_value VARCHAR, feature_source VARCHAR, created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS prism.risk_scores (
    score_id BIGSERIAL PRIMARY KEY, application_id BIGINT REFERENCES prism.applications(application_id),
    credit_score INTEGER, probability_default NUMERIC(5,4), confidence_score NUMERIC(5,2), risk_tier VARCHAR(20),
    generated_at TIMESTAMP, model_name VARCHAR(50), model_version VARCHAR(20), score_status VARCHAR(20)
);
CREATE TABLE IF NOT EXISTS prism.shap_explanations (
    explanation_id BIGSERIAL PRIMARY KEY, score_id BIGINT REFERENCES prism.risk_scores(score_id),
    feature_name VARCHAR(100), shap_value NUMERIC(10,6), score_contribution NUMERIC(10,2),
    contribution_type VARCHAR(20), feature_rank INTEGER, generated_reason TEXT, created_at TIMESTAMP
);
