"""Read-only corroboration of committed browser acceptance, never creates scores."""
import json
from pathlib import Path
import fitz
from sqlalchemy.orm import Session
from database.db import engine
from database.models import ExperimentalAssessment, BankCashflowAssessment, Document


def main():
    output = Path(__file__).resolve().parents[1] / 'docs' / 'live-demo'
    browser = json.loads((output / 'browser-evidence.json').read_text())
    app_id = browser['application_id']
    with Session(engine) as db:
        card = db.query(ExperimentalAssessment).filter_by(assessment_id=browser['credit']['assessment_id'], application_id=app_id).one()
        bank = db.query(BankCashflowAssessment).filter_by(assessment_id=browser['bank']['assessment_id'], application_id=app_id).one()
        assert abs(float(card.score) - browser['credit']['score']) < 1e-8
        assert bank.score == 775
        assert db.query(ExperimentalAssessment).filter_by(application_id=app_id).count() == 1
        assert db.query(BankCashflowAssessment).filter_by(application_id=app_id).count() == 1
        assert db.query(Document).filter_by(application_id=app_id).count() == 24
        result = {'application_id': app_id, 'credit_id': card.assessment_id, 'bank_id': bank.assessment_id,
            'document_count': 24, 'credit_assessment_count': 1, 'bank_assessment_count': 1, 'database_verified': True}
        # Original/default-cutoff failure was separately executed in the real UI.
        original_card = db.query(ExperimentalAssessment).filter_by(application_id=99).one()
        original_bank = db.query(BankCashflowAssessment).filter_by(application_id=99).one()
        result['original_browser_negative'] = {'application_id': 99, 'credit_id': original_card.assessment_id,
            'bank_id': original_bank.assessment_id, 'credit_score': float(original_card.score) if original_card.score else None,
            'card_cutoff': original_card.prediction_cutoff_month, 'card_validation': original_card.evidence_validation,
            'bank_score': original_bank.score, 'bank_gaps': original_bank.result_json['evidence_gaps'],
            'documents': db.query(Document).filter_by(application_id=99).count()}
    for name, identity, needle in [('credit',card.assessment_id,'454.635898966963'),('bank',bank.assessment_id,'Index score: 775')]:
        with fitz.open(output / f'{name}.pdf') as pdf:
            text = ''.join(p.get_text() for p in pdf)
            assert identity in text and needle in text
            assert f'Application: {app_id}' in text
    result['downloaded_pdf_values_verified'] = True
    (output / 'database-verification.json').write_text(json.dumps(result, indent=2))
    (output / 'acceptance-report.md').write_text(f'''# PRISM P0 live-demo acceptance — 10 October 2026

**Actual browser result: PASS.** Playwright drove the regular borrower UI at `http://127.0.0.1:5173`, using the regular backend at `http://127.0.0.1:8000` and the local PostgreSQL database. This report accompanies the assertion log at `../live-demo-browser-tests.txt` and sanitized request/response evidence at `browser-evidence.json`.

## Reproduced failure and corrections

Before the new fixture-loader changes, a fresh borrower application **99** submitted all 24 original PDFs using the normal four category controls. Both POST requests completed with HTTP 200 and terminal insufficient-evidence results. Card classification and extraction succeeded, but the October default cutoff required April–September while the source evidence was March–August: `MONTH_WINDOW_OR_CONTINUITY_INVALID`. The bank parsed six months and all 48 transactions but correctly blocked scoring with `STATEMENT_PAGE_COVERAGE_NOT_VERIFIED`. These were evidence failures, not missing numerical rendering or a permanent spinner. Initial development reloads also attempted latest retrieval before that fresh application had any records, producing expected empty-history 404s; the positive acceptance run had no such responses.

Added a development-only, authenticated **file selector** in the actual upload form. It selects exactly the verified PDF bytes, labels the separately repaired bank copies, and explicitly fills the September historical cutoff. The borrower still records consent and presses Run Assessment; no score is inserted or hardcoded. A hashed manifest rejects modified fixture bytes. Production disables the selector and backend file endpoints. See `../live-demo-workflow.md` for commands.

The dashboard now shows both saved numerical scorecards together, exposes an explicit insufficient-evidence state instead of misleading score-pending wording, and displays the card result to two decimals. Starting a different application or logging out clears old saved assessment references. A React upload-row key warning was corrected. Sanitized demo-only server receipts record received field names and known synthetic filenames, never contents or authentication tokens.

Changed/added files this P0 follow-up: backend `route/demo_fixture_routes.py`, `core/demo_receipt.py`, `route/routes.py`, receipt calls in both assessment routes, `test_fixtures/demo_manifest.json`, `test_demo_fixture_loader.py`, and read-only `verify_live_demo.py`; frontend `pages/UploadPage.jsx`, `pages/ResultsPage.jsx`, `components/BankCashflowAssessment.jsx`, `pages/LenderDashboard.jsx`, `App.jsx`, `services/api.js`, `.env.demo`, `scripts/demo-backend.mjs`, `playwright.config.js`, `e2e/live-demo.spec.js`, package scripts/dependency and ignored runtime files. Existing extraction/scoring recovery changes are documented in `../scorecard-recovery-report.md`.

## Submitted and extracted evidence

**24 PDFs**: six page-repaired bank statements, six unchanged original cards, six original salary slips and six original utility bills, March–August 2026. Actual server multipart receipt: **18 files** at `/assess/bank-cashflow` (`statement_files`, `salary_files`, `utility_files`) and **six files** at `/assess/credit-card-statements` (`statement_files`, explicit card consent and `prediction_cutoff_month=2026-09`). Authentication propagated via `session-id`; its value is redacted.

No PDF in the positive set was rejected. Six bank/card months aggregate; all 48 bank rows independently match original transaction ground truth, including dates, debit/credit values, narration and balances. Twelve supporting documents are supporting-only. Page coverage, account linkage, full periods, running balances and cross-statement continuity pass for the repaired positive set. The original PDFs are unchanged and remain a negative test.

## Actual calculations

| Frozen card input | Extracted value |
|---|---:|
| recent_delinquency_level | 1 |
| months_with_delinquency | 4 |
| payment_to_statement_ratio | 0.37359550561797755 |
| mean_statement_balance | 29666.666666666668 |

Actual uncapped score **454.635898966963**, displayed **454.64**; raw uncalibrated PD **0.2727810906249319**, displayed **27.28%**. Independent acceptance arithmetic reads ground truth and the immutable bins/coefficients, rather than trusting response scores. Score tolerance 1e-8; PD tolerance 1e-10.

Frozen Phase 2F artifact SHA-256 remains `DE1C1106759ED00F53F208C5185D63B3D8D22DB477D3A3EFD36132B5830E4CA6`. No frozen feature definitions, model weights, evidence gates or score cap were changed.

| Bank indicator | Calculated value |
|---|---:|
| surplus_month_rate | 1.000000 |
| expense_to_income (normalized health component) | 0.278970 |
| income_regularity | 0.973306 |
| liquidity_buffer | 0.943977 |
| debt_burden | 0.903665 |

Version **BANK_FINANCIAL_HEALTH_INDEX_V1**, index **775**, six months, 48 transactions, **no PD**. Independent arithmetic recomputes monthly totals, sample income CV, observed balances, explicit EMI payments and fixed weighted index. Factor tolerance 1e-5; index comparison exact.

## Persisted IDs and actual journey

Application **{app_id}**:

- Card assessment: `{card.assessment_id}`.
- Bank assessment: `{bank.assessment_id}`.
- PostgreSQL: 24 documents, one card assessment, one bank assessment. Repeated upload returned the same IDs; no inconsistent duplicates.

Passed browser checks: normal generated-OTP authentication, mandatory and supporting consents, 24 visible filenames, actual multipart receipt, completed processing, visible numeric dashboard, both results after refresh, real simulations, both PDF downloads, baseline preservation after a second refresh, repeat-upload idempotency, and authorized lender View of the same application and exact assessment IDs. No unexpected 401, 404 or 500 occurred in the captured positive borrower/lender journey.

Card what-if payment ratio 0.9 produces score 458.4 and raw PD 26.26%; bank monthly income ₹110,000 produces 790. Both hypothetical results render in the UI. Persisted baselines remain 454.64 and 775. Downloaded `credit.pdf` and `bank.pdf` contain these saved IDs, application and exact baseline values; rendered pages were visually checked for layout.

Screenshot of both scorecards: `both-scorecards.png`. Lender screenshot: `lender.png`. Full sanitized numerical responses, extraction findings, provenance, URLs, statuses and multipart receipts: `browser-evidence.json`. Read-only PostgreSQL and PDF corroboration: `database-verification.json`.

## Testing and limitations

- Final authenticated browser acceptance: **1 passed**, including strengthened visible-simulation and exact-lender-ID assertions.
- Backend targeted regressions: **26 passed**; frontend contracts/workflow: **10 passed**; production build passed.
- Original dossier/default-cutoff negative journey was separately executed through the real browser, application 99. Its persisted gaps and IDs are retained in the database-verification evidence.
- The earlier broader suite's 361 passed, 57 failed and three errors were not reclassified as green or repaired by modifying historical artifacts. Missing research fixtures, historical protected-manifest differences and obsolete scorer tests remain outside this P0 fix. The full earlier triage remains in `../scorecard-recovery-report.md`.
- This verifies a fictional synthetic local demonstration, not real issuer-layout coverage, calibrated Indian lending risk, issuer-certified repayment evidence or production readiness. The raw credit PD remains experimental/inconclusive. The bank index is descriptive and produces no PD or lending tier.
- The original banks still lack page declarations. The historical September cutoff is explicit; October eligibility is not silently altered. The demo selector is unavailable outside development/demo.
- OTP is logged locally for test phones; sessions expire in 60 minutes and are held in memory. A backend restart requires login again. Production SMS and persistent authentication remain deployment work.
''', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'original_browser_negative'}, indent=2))


if __name__ == '__main__':
    main()
