"""Exact external synthetic dossier; original and repaired fixtures are distinct."""
import hashlib
import json
from pathlib import Path

import fitz
import pandas as pd
import pytest
from database.models import Consent, BankCashflowAssessment
from ingestion.universal_pipeline import TextExtractor
from phase2.credit_parser.document_extraction import extract_document_text
from route.assessment_routes import process_bank_doc
from test_credit_card_document_assessment import postgres_demo, multipart

ROOT = Path(__file__).parent / 'test_fixtures' / 'aarav_original'
TRUTH = json.loads((ROOT / 'ground_truth.json').read_text())


@pytest.mark.parametrize('kind', ['native', 'multi', 'scanned_without_ocr', 'encrypted', 'corrupted'])
def test_pdf_lifecycle(tmp_path, kind):
    path = tmp_path / 'statement.pdf'
    if kind == 'corrupted':
        path.write_bytes(b'%PDF-1.7 broken')
    else:
        with fitz.open() as pdf:
            for _ in range(2 if kind == 'multi' else 1):
                page = pdf.new_page()
                if kind != 'scanned_without_ocr':
                    page.insert_text((40, 40), 'CREDIT CARD STATEMENT with readable financial evidence')
            options = {'encryption': fitz.PDF_ENCRYPT_AES_256, 'owner_pw': 'owner', 'user_pw': 'secret'} if kind == 'encrypted' else {}
            pdf.save(path, **options)
    if kind in {'corrupted', 'encrypted'}:
        with pytest.raises((ValueError, RuntimeError, fitz.FileDataError)):
            extract_document_text(str(path), None)
    else:
        text, method, confidence, pages = extract_document_text(str(path), None)
        assert pages == (2 if kind == 'multi' else 1)
        assert method == ('no_readable_text' if kind == 'scanned_without_ocr' else 'native_pdf_text')
        assert bool(text.strip()) == (kind != 'scanned_without_ocr')


def test_original_bank_rows_match_all_ground_truth():
    observed = []
    for month in TRUTH['monthly_summary']:
        _, tx, meta = process_bank_doc(str(ROOT / f"Bank_Statement_{month['month']}.pdf"))
        assert len(tx) == month['bank_transactions']
        assert meta['opening_balance'] == month['opening_balance']
        assert meta['statement_closing_balance'] == month['closing_balance']
        assert meta['quality_score'] >= .8
        for row in tx.to_dict('records'):
            observed.append((pd.to_datetime(row['date'], format='%d/%m/%Y').date().isoformat(),
                row['amount'], row['type'], row['closing_balance'], row['narration']))
    expected = [(r['date'], r['credit'] or r['debit'], 'CR' if r['credit'] else 'DR',
                 r['balance'], r['description']) for r in TRUTH['bank_transactions']]
    assert observed == expected


def test_exact_dossier_persistence_gates_and_repaired_bank(postgres_demo, tmp_path):
    state = postgres_demo
    consent = state['db'].query(Consent).filter_by(application_id=state['application'].application_id).one()
    consent.bank_consent = consent.salary_consent = consent.utility_consent = True
    state['db'].commit()
    headers = {'session-id': state['borrower'].session_id}
    cards = sorted(ROOT.glob('Credit_Card_*.pdf'))
    banks = sorted(ROOT.glob('Bank_Statement_*.pdf'))
    client = state['client']
    current = client.post('/assess/credit-card-statements', headers=headers,
        data={'credit_card_consent': 'true'}, files=multipart(cards))
    assert current.status_code == 200, current.text
    assert current.json()['score'] is None
    assert 'MONTH_WINDOW_OR_CONTINUITY_INVALID' in current.json()['evidence_validation']['blocking_reasons']
    historical = client.post('/assess/credit-card-statements', headers=headers,
        data={'credit_card_consent': 'true', 'prediction_cutoff_month': '2026-09'}, files=multipart(cards))
    assert historical.json()['score'] is None
    assert 'PAYMENT_DUE_DATE_NOT_AFTER_STATEMENT_DATE' in historical.json()['evidence_validation']['blocking_reasons']
    corrected_cards = sorted((Path(__file__).parents[1] / 'tests/fixtures/prism_demo_validated').glob('Credit_Card_*.pdf'))
    historical = client.post('/assess/credit-card-statements', headers=headers,
        data={'credit_card_consent': 'true', 'prediction_cutoff_month': '2026-09'}, files=multipart(corrected_cards))
    assert historical.status_code == 200, historical.text
    card = historical.json()
    assert card['assessment_status'] == 'SCORED', card
    for key, value in TRUTH['frozen_model_input_candidates'].items():
        assert float(card['feature_values'][key]) == pytest.approx(value)
    assert card['artifact_sha256'] == 'DE1C1106759ED00F53F208C5185D63B3D8D22DB477D3A3EFD36132B5830E4CA6'
    supporting = [(f'{category}_files', (p.name, p.read_bytes(), 'application/pdf'))
                  for category, pattern in [('salary', 'Salary_Slip_*.pdf'), ('utility', 'Utility_Bill_*.pdf')]
                  for p in sorted(ROOT.glob(pattern))]
    original = client.post('/assess/bank-cashflow', headers=headers, files=multipart(banks) + supporting)
    assert original.status_code == 200, original.text
    assert original.json()['months_observed'] == 6
    assert original.json()['transaction_count'] == 48
    assert original.json()['evidence_gaps'] == ['STATEMENT_PAGE_COVERAGE_NOT_VERIFIED']
    assert len(original.json()['supporting_documents']) == 12
    for item in original.json()['supporting_documents']:
        assert not item['findings'], item
        if item['document_type'] == 'SALARY':
            fields = item['fields']
            assert fields['gross_salary'] - fields['deductions'] == pytest.approx(fields['net_salary'], abs=.02)
        else:
            assert item['fields']['payment_status'].startswith('PAID')
            assert item['fields']['amount_due'] > 0
    repaired = []
    for source in banks:
        path = tmp_path / source.name
        with fitz.open(source) as pdf:
            for i, page in enumerate(pdf):
                page.insert_text((40, 820), f'Page {i+1} of {len(pdf)} | SYNTHETIC FIXTURE REPAIR: page declaration added', fontsize=8)
            pdf.save(path)
        repaired.append(path)
    response = client.post('/assess/bank-cashflow', headers=headers, files=multipart(repaired) + supporting)
    assert response.status_code == 200, response.text
    bank = response.json()
    assert bank['status'] == 'SCORED', bank
    assert bank['pd'] is None and bank['months_observed'] == 6 and bank['transaction_count'] == 48
    assert client.get(f"/assess/bank-cashflow/{bank['assessment_id']}", headers=headers).json()['score'] == bank['score']
    replay = client.post('/assess/bank-cashflow', headers=headers, files=multipart(repaired) + supporting)
    assert replay.json()['assessment_id'] == bank['assessment_id']
    assert replay.json()['idempotent_replay'] is True
    row = state['db'].query(BankCashflowAssessment).filter_by(assessment_id=bank['assessment_id']).one()
    baseline = row.score
    scenario = client.post(f"/assess/bank-cashflow/{bank['assessment_id']}/what-if", headers=headers,
        json={'monthly_income': 110000})
    assert scenario.status_code == 200, scenario.text
    state['db'].refresh(row)
    assert row.score == baseline
    report = client.get(f"/assess/bank-cashflow/{bank['assessment_id']}/report.pdf", headers=headers)
    with fitz.open(stream=report.content, filetype='pdf') as pdf:
        report_text = ''.join(page.get_text() for page in pdf)
    assert bank['assessment_id'] in report_text and f"Index score: {baseline}" in report_text
    lender = client.get(f"/lender/applications/{state['application'].application_id}",
        headers={'session-id': state['lender'].session_id}).json()
    assert lender['experimental_assessment']['assessment_id'] == card['assessment_id']
    assert lender['bank_cashflow_assessment']['assessment_id'] == bank['assessment_id']
    output = tmp_path / 'reports'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'PRISM-synthetic-bank-assessment.pdf').write_bytes(report.content)
    card_report = client.get(f"/assess/credit-card-assessments/{card['assessment_id']}/report.pdf", headers=headers)
    assert card_report.status_code == 200
    (output / 'PRISM-synthetic-credit-assessment.pdf').write_bytes(card_report.content)
    evidence = {'credit': card, 'bank_original': original.json(), 'bank_repaired': bank,
                'database_verification': 'PostgreSQL rollback-only integration; IDs not retained'}
    (tmp_path / 'scorecard-recovery-evidence.json').write_text(json.dumps(evidence, indent=2))


def test_account_token_is_stable_without_exposing_identifier(monkeypatch):
    monkeypatch.setenv('PRISM_ACCOUNT_REFERENCE_SALT', 'synthetic-test-secret')
    text = 'Account reference: TEST-ACCT-0042\nCurrency: INR'
    a = TextExtractor._safe_source_metadata(text, 'native_text', False)
    b = TextExtractor._safe_source_metadata(text, 'native_text', False)
    assert a['account_reference_token'] == b['account_reference_token']
    assert 'TEST-ACCT-0042' not in json.dumps(a)


@pytest.mark.parametrize('encrypted', [False, True])
def test_bad_pdf_http_validation_is_controlled(postgres_demo, encrypted):
    if encrypted:
        with fitz.open() as doc:
            doc.new_page().insert_text((40,40),'Credit card statement: encrypted test')
            content = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='secret')
    else:
        content = b'%PDF corrupted synthetic fixture'
    response = postgres_demo['client'].post('/assess/credit-card-statements',
        headers={'session-id': postgres_demo['borrower'].session_id}, data={'credit_card_consent':'true'},
        files=[('statement_files', ('bad.pdf', content, 'application/pdf'))])
    assert response.status_code == 422
    assert 'unlocked PDF' in response.json()['detail']
