# Real-statement integration and final demo verification — 2026-10-12

## Outcome and limits

The validated synthetic demonstration works through the normal manual borrower and lender journey. Three fresh applications passed complete acceptance. Real-world support is bounded: the authorized SBI-labelled six-transaction sample now extracts accurately, but lacks the verified period/opening/closing/page evidence needed to score the full V1 index. The ten-page sample has reflowed columns and is rejected for review. The encrypted Bank of Maharashtra sample was left unopened at the user's direction. No real sample in this run qualified for BANK_FINANCIAL_HEALTH_INDEX_V1. Arbitrary Indian-bank statements are not established as supported. Do not substitute the synthetic demo evidence for a claim of real-bank production readiness.

## Audited flow

Consented, owned multipart upload -> PDF/native-coordinate inspection or existing native-text/OCR fallback -> typed transactions and physical source pages -> account/currency/month aggregation -> opening/running/closing reconciliation and V1 gates -> fixed five-factor index -> PostgreSQL assessment -> borrower restoration -> authorized lender -> persisted PDF and hypothetical simulation. Single-statement users retain the separate versioned snapshot profile. Auto selection uses the full V1 only when every V1 gate passes; otherwise the snapshot must pass its own documented contract. No model gate or frozen credit-card artifact was changed.

## Defects found and changes

- Flattened text was losing debit/credit column alignment; narration keywords and character offsets could misclassify transactions. Added generic native word-coordinate reconstruction with header roles, swapped debit/credit and withdrawal/deposit labels, multiline row bands, source page, typed amounts and explicit ambiguity rejection. No bank-specific adapter or broad named-bank support was asserted.
- ISO date strings combined with day-first parsing could lose rows or change months. Native extraction returns typed timestamps; period parsing deduplicates overlapping two/four-digit matches.
- Missing amounts could become zero in the legacy canonical builder. They now remain unknown.
- Multiple account references could silently pick the first account. Ambiguous references now produce no linkage token. Existing HMAC secret configuration remains required; secrets are not hardcoded or returned.
- Borrower and lender latest retrieval could select a newer failed history result over a scored assessment. Both now prefer the newest scored result within the application, with deterministic tie ordering.
- A single bank upload always selected snapshot even when full V1 history was available. Auto now returns the original BANK_FINANCIAL_HEALTH_INDEX_V1 for eligible history; the bank index remains primary and the card result separate.
- Added ephemeral PDF password input and encrypted-document correction guidance. Passwords are not included in assessment identity or persisted results.
- Added a consented extraction-preview endpoint and UI with bank label where explicitly present, masked-reference availability, period, currency, transaction counts, totals, opening/closing balances, reconciliation and transaction source pages. Preview is read-only and audit logged. It never produces a score or overrides structural validation.
- Added monthly observed balance summaries alongside the existing income/expense table. Human-readable review/failure labels replace the raw evidence/research phrases in relevant borrower/lender renderings; internal statuses remain available to services and logs.
- Browser test failures included reusing a previous fixed lender's OTP log entry. Helpers now read only newly generated OTP entries for each login; authentication itself remains intact. An alternate test origin also failed CORS and was replaced by the configured isolated origin. These were failed/interrupted verification attempts, followed by the successful final run below.

## Actual sample compatibility

| Sample in the authorized real-world folder | Evidence established | Result |
|---|---|---|
| SBI-labelled one-page sample | Six dates and all twelve amount/balance values match the physical source words; five debits and one credit; successive balances reconcile within the existing five-paise tolerance | Preview available. One observed month; full-index eligibility remains unmet. No real-bank index claimed. |
| Ten-page statement | Text exists on all ten pages, but date/amount columns are reflowed; bank names in narration do not establish issuer identity | Review Required; no guessed rows or score. |
| Bank of Maharashtra-labelled two-page PDF | Encryption detected | Document Could Not Be Read without password; user requested investigation of the other samples. |

HDFC, ICICI, Axis and Kotak representative issuer formats were not established from these samples. Native coordinate tests use generated fixtures and prove parser behavior, not issuer compatibility. Actual scanned-bank end-to-end accuracy, mixed native/scanned pages and wide OCR layout robustness remain unverified. Existing image/OCR tests use controlled mocked output.

## Full validated demo results

All three runs were ordinary manual uploads of the same clearly labelled fictional validated fixture set: six bank months, 48 transactions, six optional cards plus salary/utility support. Index 775 was dynamically calculated using unchanged V1 factors:

| Factor | Value | Weight |
|---|---:|---:|
| Surplus month rate | 1.000000 | 0.25 |
| Expense-to-income health | 0.278970 | 0.25 |
| Income regularity | 0.973306 | 0.20 |
| Liquidity buffer | 0.943977 | 0.15 |
| Explicit debt burden | 0.903665 | 0.15 |

All 48 dates, directions, amounts and running balances agree with synthetic ground truth. Six months were recognized and balances reconciled. Independent arithmetic in the browser test agrees with the index. The separate frozen card result remains 454.635898966963 and is not a bank-score fallback.

| Run | Application | Persisted bank assessment UUID |
|---|---:|---|
| 1 | 180 | 0270ce5f-c801-425d-9b17-c9b6ec014540 |
| 2 | 182 | 97929626-5c5d-469f-8bb5-895bba8f4620 |
| 3 | 185 | 3b6e1d75-3e45-4901-a830-dbc1dba322c8 |

Each passed normal OTP login, consent, manual multipart upload, ownership, numerical results, saved refresh, baseline-preserving simulations, both PDF downloads, idempotent resubmission and authorized lender retrieval. Screenshots and sanitized evidence are under docs/live-demo/real-integration-manual-{1,2,3}. Browser log: docs/real-bank-browser-manual.txt — 3 passed (1.6m).

## Validation

- Targeted backend: 28 passed, including coordinate roles, unknown amount rejection, multi-page extraction, encryption/password inspection, overlapping date patterns, actual sample source comparison, account ambiguity, consented preview, PostgreSQL auto-V1 persistence, failed-latest preservation, numerical index behavior, validated dossier and controlled upload-format/OCR tests. Log: docs/real-bank-targeted-tests.txt.
- Frontend contracts: 13 passed. Log: docs/real-bank-frontend-tests.txt.
- Production build passed. Log: docs/real-bank-build.txt.
- Final preview/real-sample and thin-file browser acceptance: 4 passed, including correction of invalid bank upload, real sample review/rejection, bank-only, salary/utility and one optional card. Log: docs/real-bank-browser-review.txt.
- Frozen scorecard SHA256 unchanged: DE1C1106759ED00F53F208C5185D63B3D8D22DB477D3A3EFD36132B5830E4CA6.
- The broader historical research suite was not rerun or represented as passing.

## Modified implementation files

backend/ingestion/bank_layout.py; backend/ingestion/parsers/bank_parser.py; backend/ingestion/universal_pipeline.py; backend/route/bank_cashflow_routes.py; backend/route/lender_routes.py; backend/test_native_bank_layout.py; prism-frontend/src/services/api.js; prism-frontend/src/services/assessmentWorkflow.js and its test; prism-frontend/src/pages/UploadPage.jsx, ResultsPage.jsx, ApplicationsPage.jsx and AssessmentPage.jsx; prism-frontend/src/components/BankCashflowAssessment.jsx; prism-frontend/e2e/live-demo.spec.js, thin-file.spec.js and real-bank-review.spec.js; .gitignore. Pre-existing unrelated changes were preserved.

## Privacy and remaining work

Private PDFs/RPT were already tracked before this task. They were removed from the current Git index with cached removal only, and ignored; all local originals remain intact. Existing Git history still contains earlier versions and was not rewritten. No copies of private financial statements were added to fixtures or reports. The actual-sample browser test avoids screenshots of private amounts and does not print private transaction data. Demo screenshots and evidence use fictional records.

The preview does not yet implement audited field correction/resubmission with user-confirmed provenance. Wider bank adapters, positional OCR, all 23 requested compatibility scenarios, malformed-layout repair and a genuinely eligible bank-generated demo set remain outstanding. A real-world full-index demonstration needs readable, complete and reconcilable source statements with adequate history, or the permission/password and source clarification needed to examine the currently unreadable files. No synthetic credit repayment history, default probability or fixed numerical fallback was invented.


The generated one-page bank PDF and the full-index dashboard screenshot were visually inspected: index, five factors, six-month table and report limitations are legible without clipping. Latest real-sample/thin-file browser acceptance finished with four passes; the three manual runs are separately retained.


## October 12 SBI single-file scoring correction

The authorized SBI sample now succeeds through the normal auto assessment and produces a cash-flow snapshot score of 308 from six transactions. Its coordinate extraction quality is 1.0. The earlier report of this file being blocked by missing opening/closing labels is superseded for the snapshot profile only. Successive transaction balances are checked independently; declared opening/closing and full-period completeness remain unverified and are recorded in coverage. No balance values are fabricated. Full history V1 evidence gates remain unchanged. Explicit declared-balance mismatches, corrupted successive balances and unreadable rows still block scoring. Parser identity advanced to native-coordinate-v6 to prevent reusing old cached results.

## October 12 Indian Bank newest-first ledger correction

The private data/testing Indian Bank ten-page statement extracts 233 transactions over six observed months and now produces a cash-flow snapshot of 438. Reconciliation now reverses the complete source ledger when dates descend, preserving same-day and cross-page sequence. Every successive balance reconciles within 0.05; missing declared opening/closing balances still limit the assessment to observed rows. Parser identity is native-coordinate-v7. The SBI test file continues to score 308. Statements from different accounts must be assessed separately.
