from datetime import datetime
from uuid import uuid4

from database.models import AuditEvent, BankCashflowAssessment, Consent
from test_credit_card_document_assessment import postgres_demo


def test_returning_borrower_reuses_application_and_can_read_saved_monthly_history(postgres_demo, monkeypatch):
    from auth import service as auth_service

    state = postgres_demo
    db = state['db']
    application_id = state['application'].application_id
    consent = db.query(Consent).filter_by(application_id=application_id).one()
    consent.bank_consent = True
    db.commit()
    monthly = [{"month":"2026-08","income_total":100000,"expense_total":60000,
        "net_flow":40000,"credit_count":1,"debit_count":2,"observed_pattern_score":742,
        "available_pattern_count":3,"average_balance":85000}]
    assessment = BankCashflowAssessment(assessment_id=str(uuid4()), application_id=application_id,
        user_id=state['user'].user_id, input_sha256='a' * 64,
        assessment_type='BANK_CASHFLOW_EXPERIMENTAL', model_version='PRISM_CASHFLOW_SNAPSHOT_V1',
        assessment_status='SCORED', evidence_document_ids=[], feature_values={}, score=742,
        probability_default=None, feature_contributions=[], reason_codes=[],
        validation_status='OBSERVED_PATTERNS_VERIFIED', result_json={
            'model_name':'PRISM cash-flow snapshot',
            'currency':'INR','months_observed':1,'observed_months':['2026-08'],
            'transaction_count':3,'monthly':monthly,'financial_metrics':{},
            'recommendations':['Maintain a positive monthly surplus.'],'document_findings':[],
            'fraud_findings':{'fraud_score':0,'fraud_status':'CLEAR','flags':[],
                'rule_count':0,'engine_version':'test-engine',
                'score_semantics':'heuristic weighted rule score; not a calibrated probability',
                'coverage':{'transactions_reviewed':3}},
            'feature_values':{'surplus_month_rate':1.0},
            'feature_contributions':[{'feature':'surplus_month_rate','direction':'FAVORABLE'}],
            'methodology':{'weights':{'surplus_month_rate':0.25},'limitations':['Experimental index']},
            'evidence':{'balance_reconciled':True}},
        created_at=datetime(2026, 9, 1))
    db.add(assessment)
    db.add(AuditEvent(application_id=application_id, action='bank_cashflow_assessment_checked',
        entity='bank_cashflow_assessment', status='scored', event_timestamp=datetime(2026, 9, 2),
        details={'assessment_id':assessment.assessment_id,'source_document_count':1,'score_generated':True}))
    db.commit()
    monkeypatch.setattr(auth_service, 'verify_otp', lambda *_: True)

    login = auth_service.verify(db, state['user'].phone, '123456')
    assert login['application_id'] == application_id
    assert login['has_prior_assessments'] is True
    assert login['is_returning_user'] is True

    response = state['client'].get('/assess/bank-cashflow/history',
        headers={'session-id':login['session_id']})
    assert response.status_code == 200, response.text
    history = response.json()
    assert history['application_id'] == application_id
    assert history['assessment_count'] == 1
    assert history['monthly_scores'][0]['month'] == '2026-08'
    assert history['monthly_scores'][0]['score'] == 742
    assert history['assessments'][0]['model_name'] == 'PRISM cash-flow snapshot'
    assert history['assessments'][0]['fraud_findings']['engine_version'] == 'test-engine'
    assert history['assessments'][0]['feature_contributions'][0]['feature'] == 'surplus_month_rate'
    assert history['assessments'][0]['methodology']['weights']['surplus_month_rate'] == 0.25
    assert history['assessments'][0]['evidence']['balance_reconciled'] is True
    assert history['assessments'][0]['checked_at'] == ['2026-09-02T00:00:00+00:00']
    assert history['activity'][0]['source_document_count'] == 1
