from database.models import AuditEvent, BankCashflowAssessment, ExperimentalAssessment


def test_assessment_orm_exposes_existing_migration_indexes_and_bank_checks():
    assert "idx_prism_audit_events_app_time" in {index.name for index in AuditEvent.__table__.indexes}
    assert "ix_experimental_assessments_user" in {index.name for index in ExperimentalAssessment.__table__.indexes}
    assert "ix_bank_cashflow_user" in {index.name for index in BankCashflowAssessment.__table__.indexes}
    assert {"ck_bank_cashflow_no_pd", "ck_bank_cashflow_score_range"}.issubset(
        {constraint.name for constraint in BankCashflowAssessment.__table__.constraints}
    )


def test_jsonb_server_defaults_match_existing_additive_schema():
    assert str(AuditEvent.__table__.c.details.server_default.arg) == "'{}'::jsonb"
    assert str(ExperimentalAssessment.__table__.c.reason_codes.server_default.arg) == "'[]'::jsonb"
    assert str(ExperimentalAssessment.__table__.c.document_findings.server_default.arg) == "'{}'::jsonb"
    assert str(BankCashflowAssessment.__table__.c.evidence_document_ids.server_default.arg) == "'[]'::jsonb"
    assert str(BankCashflowAssessment.__table__.c.feature_values.server_default.arg) == "'{}'::jsonb"
