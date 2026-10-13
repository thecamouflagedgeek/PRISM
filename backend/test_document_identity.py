from pathlib import Path
from ingestion.identity import extract_person_name, verify_document_identities
from test_credit_card_document_assessment import postgres_demo


def test_name_extraction_accepts_explicit_labels_and_titles():
    assert extract_person_name('Account Name\nMs. Usha Shah\nBranch\nExample') == 'usha shah'
    assert extract_person_name('Employee Name: Usha Shah\nNet Salary: 50000') == 'usha shah'


def test_name_extraction_rejects_missing_and_conflicting_names():
    assert extract_person_name('Customer Name\nAddress\nExample Road') is None
    assert extract_person_name('Customer Name: Usha Shah\nName: Person B') is None


def test_cross_document_name_mismatch_blocks_scoring_without_disclosing_names():
    result = verify_document_identities(
        [{'file_name':'bank.pdf','holder_name':'usha shah'}],
        [{'_identity_name':'person b','file_name':'salary.pdf'}])
    assert result['status'] == 'MISMATCH'
    assert result['verified'] is False
    assert result['mismatched_documents'] == ['salary.pdf']
    assert 'usha shah' not in str(result) and 'person b' not in str(result)


def test_unreadable_supporting_identity_fails_closed():
    result = verify_document_identities(
        [{'file_name':'bank.pdf','holder_name':'usha shah'}],
        [{'_identity_name':None,'file_name':'utility.pdf'}])
    assert result['status'] == 'UNVERIFIED'
    assert result['unverified_documents'] == ['utility.pdf']


def test_bank_only_does_not_require_cross_document_comparison():
    assert verify_document_identities([{'holder_name':None}], []) == {'status':'NOT_NEEDED','verified':True}


def test_selected_real_testing_statement_and_salary_mismatch_is_rejected(postgres_demo):
    from database.models import BankCashflowAssessment, Consent
    from test_credit_card_document_assessment import multipart
    root=Path(__file__).parents[1]/'data'/'testing'
    bank=root/'448392605-Bank-Statement-1.pdf'
    salary=root/'489674831-SALARY-SLIP-NEW.pdf'
    if not bank.exists() or not salary.exists():
        import pytest
        pytest.skip('Optional local bank statement samples are unavailable')
    state=postgres_demo;db=state['db'];client=state['client']
    consent=db.query(Consent).filter_by(application_id=state['application'].application_id).one()
    consent.bank_consent=True;consent.salary_consent=True;db.commit()
    files=multipart([bank])+[('salary_files',(salary.name,salary.read_bytes(),'application/pdf'))]
    response=client.post('/assess/bank-cashflow',headers={'session-id':state['borrower'].session_id},
        data={'assessment_profile':'auto'},files=files)
    assert response.status_code==422
    assert 'IDENTITY_CHECK_FAILED' in response.text and salary.name in response.text
    assert db.query(BankCashflowAssessment).filter_by(application_id=state['application'].application_id).count()==0
