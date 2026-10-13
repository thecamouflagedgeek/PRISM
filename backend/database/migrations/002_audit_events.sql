CREATE TABLE IF NOT EXISTS prism.audit_events (
    event_id BIGSERIAL PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES prism.applications(application_id),
    action VARCHAR(120) NOT NULL,
    entity VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    event_timestamp TIMESTAMP NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_prism_audit_events_app_time
    ON prism.audit_events (application_id, event_timestamp DESC);
