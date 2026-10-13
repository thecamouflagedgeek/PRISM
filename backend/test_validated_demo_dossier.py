import hashlib
import json
from pathlib import Path
import fitz
import pytest
from database.models import Consent
from phase2.credit_parser.document_extraction import extract_labeled_fields
from route.assessment_routes import process_bank_doc
from test_credit_card_document_assessment import postgres_demo, multipart

ROOT = Path(__file__).parents[1] / 'tests/fixtures/prism_demo_validated'
MANIFEST = json.loads((ROOT/'manifest.json').read_text())
TRUTH = json.loads((ROOT/'ground_truth.json').read_text())


def test_every_corrected_pdf_and_original_hash():
    for item in MANIFEST['files']:
        path = ROOT/item['name']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
        original = Path(__file__).parent/'test_fixtures/aarav_original'/item['name']
        assert hashlib.sha256(original.read_bytes()).hexdigest() == item['original_sha256']
        with fitz.open(path) as pdf:
            assert len(pdf) == 1
            text=pdf[0].get_text()
        assert 'SYNTHETIC' in text and 'FICTIONAL' in text and 'Page 1 of 1' in text
        if item['category']=='creditCards':
            fields,gaps=extract_labeled_fields(text)
            assert not gaps,(item['name'],gaps)
            row=next(r for r in TRUTH['credit_card_monthly_evidence'] if r['month']==fields['statement_month'])
            assert fields['account_reference']==TRUTH['card_reference']
            assert fields['_auxiliary_fields']['statement_reference']==row['statement_reference']
        elif item['category']=='bank':
            _,actual,meta=process_bank_doc(str(path))
            _,original_rows,_=process_bank_doc(str(original))
            columns=['date','amount','type','closing_balance','narration']
            assert actual[columns].to_dict('records')==original_rows[columns].to_dict('records')
            assert meta['declared_page_sequence_complete'] is True


def test_complete_corrected_api_and_invalid_support_blocks_identity_check(postgres_demo):
    state=postgres_demo; client=state['client']; headers={'session-id':state['borrower'].session_id}
    consent=state['db'].query(Consent).filter_by(application_id=state['application'].application_id).one()
    consent.bank_consent=consent.salary_consent=consent.utility_consent=True; state['db'].commit()
    banks=sorted(ROOT.glob('Bank_Statement_*.pdf')); cards=sorted(ROOT.glob('Credit_Card_*.pdf'))
    support=[(f'{category}_files',(p.name,p.read_bytes(),'application/pdf')) for category,prefix in [('salary','Salary_Slip'),('utility','Utility_Bill')] for p in sorted(ROOT.glob(f'{prefix}_*.pdf'))]
    bank=client.post('/assess/bank-cashflow',headers=headers,files=multipart(banks)+support).json()
    card=client.post('/assess/credit-card-statements',headers=headers,data={'credit_card_consent':'true','prediction_cutoff_month':'2026-09'},files=multipart(cards)).json()
    assert bank['score']==775 and bank['transaction_count']==48 and bank['months_observed']==6
    assert bank['evidence']['account_linked'] and bank['evidence']['balance_reconciled']
    assert bank['aggregation_receipt']['debits_parsed']==42
    assert len(bank['supporting_documents'])==12
    from fraud.integration import assess_fraud
    import pandas as pd
    ledger = pd.concat([process_bank_doc(str(path))[1] for path in banks], ignore_index=True)
    independent_review = assess_fraud(transactions=ledger)
    assert bank['fraud_findings']['flags'] == independent_review['flags']
    assert bank['fraud_findings']['coverage']['transactions_reviewed'] == 48
    assert 'not assessed' in bank['fraud_findings']['coverage']['identity_and_loan_stacking']
    saved = client.get(f"/assess/bank-cashflow/{bank['assessment_id']}", headers=headers)
    assert saved.status_code == 200
    assert saved.json()['fraud_findings'] == bank['fraud_findings']
    assert card['score']==pytest.approx(454.635898966963,abs=1e-8)
    assert card['probability_of_default']==pytest.approx(.2727810906249319,abs=1e-10)
    assert card['document_findings']['processing_trace'][-1]=='ASSESSMENT_PERSISTED'
    for k,v in TRUTH['frozen_model_input_candidates'].items(): assert float(card['feature_values'][k])==pytest.approx(v)
    invalid=client.post('/assess/bank-cashflow',headers=headers,files=multipart(banks)+[('salary_files',('unsupported.txt',b'not salary','text/plain'))])
    assert invalid.status_code==422 and 'IDENTITY_CHECK_FAILED' in invalid.text
    assert 'unsupported.txt' in invalid.text and 'no score was generated' in invalid.text.lower()


def test_inconsistent_payment_reference_and_dates_are_rejected():
    from phase2.credit_parser.document_extraction import validate_statement_dates
    assert 'PAYMENT_DUE_DATE_NOT_AFTER_STATEMENT_DATE' in validate_statement_dates({'statement_date':'31/03/2026','payment_due_date':'27/03/2026'})
    assert 'PAYMENT_STATEMENT_REFERENCE_MISMATCH' in validate_statement_dates({'statement_reference':'TEST-A','payment_statement_reference':'TEST-B'})


def test_single_statement_snapshot_and_optional_documents(postgres_demo):
    state = postgres_demo; client = state['client']; headers = {'session-id':state['borrower'].session_id}
    consent = state['db'].query(Consent).filter_by(application_id=state['application'].application_id).one()
    consent.bank_consent = consent.salary_consent = consent.utility_consent = True; state['db'].commit()
    bank = ROOT/'Bank_Statement_2026-03.pdf'
    response = client.post('/assess/bank-cashflow',headers=headers,data={'assessment_profile':'snapshot'},files=multipart([bank]))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['model_version'] == 'PRISM_CASHFLOW_SNAPSHOT_V1'
    assert result['score'] == 696 and result['status'] == 'SCORED'
    assert result['transaction_count'] == 8 and result['months_observed'] == 1
    assert result['coverage']['history_depth'] == 'LIMITED'
    assert result['feature_values']['income_regularity'] is None
    assert 'income_regularity' in result['coverage']['unknown_factors']
    assert result['pd'] is None and result['evidence_gaps'] == []
    saved = client.get(f"/assess/bank-cashflow/{result['assessment_id']}",headers=headers).json()
    assert saved['score'] == 696 and saved['coverage'] == result['coverage']
    unchanged = client.post(f"/assess/bank-cashflow/{result['assessment_id']}/what-if",headers=headers,json={'monthly_income':92000}).json()
    assert unchanged['score'] == 696 and unchanged['feature_values']['income_regularity'] is None
    supporting = [('salary_files',('salary.pdf',(ROOT/'Salary_Slip_2026-03.pdf').read_bytes(),'application/pdf')),
                  ('utility_files',('utility.pdf',(ROOT/'Utility_Bill_2026-03.pdf').read_bytes(),'application/pdf'))]
    enriched = client.post('/assess/bank-cashflow',headers=headers,data={'assessment_profile':'snapshot'},files=multipart([bank])+supporting).json()
    assert enriched['score'] == 696 and len(enriched['supporting_documents']) == 2
    # Different statement patterns produce a different calculated score.
    second = client.post('/assess/bank-cashflow',headers=headers,data={'assessment_profile':'snapshot'},files=multipart([ROOT/'Bank_Statement_2026-08.pdf'])).json()
    assert second['score'] != result['score'] and second['score'] != 454.64
    legacy = client.post('/assess/bank-cashflow',headers=headers,files=multipart([bank])).json()
    assert legacy['score'] is None  # Existing three-month V1 methodology unchanged.


def test_snapshot_bad_balances_are_upload_errors_not_scores():
    from features.thin_file_score import calculate_cashflow_snapshot
    _, tx, meta = process_bank_doc(str(ROOT/'Bank_Statement_2026-03.pdf'))
    with pytest.raises(ValueError,match='RUNNING_BALANCE'):
        calculate_cashflow_snapshot(tx,currency='INR',evidence={'balance_reconciled':False})
