# PRISM real-document scoring failure report

- **Run date:** 2026-10-09
- **Privacy:** File names, account data, names, raw text, transaction descriptions, and document IDs are omitted. File aliases are local to this report.

## Findings from available uploaded documents

| Alias | Classification | Extraction | Fields / validation | Frozen feature coverage | Score result / cause |
|---|---|---|---|---|---|
| Bank upload A | Bank statement; card classifier did not confirm a card statement | Native PDF text, 1 page; bank parser returned 7 transactions, 7/7 valid dated amount/type rows | Canonical date, amount, type, narration, closing-balance columns available. Parser's reported quality value was 0.60; this is parser coverage, not measured field accuracy. | 0/4 | Not eligible. No six-month credit-card balances, same-statement payments, and explicit repayment severity. Bank rows cannot substitute. |
| Bank upload B | Bank statement; card classifier did not confirm a card statement | Native PDF text, 1 page; bank parser returned 7 transactions, 7/7 valid dated amount/type rows | Same schema/validation outcome as A. No OCR was required. | 0/4 | Not eligible for the same evidence reason. |

The 7/7 figure is structural row validity, not ground-truth accuracy. We found no complete real-world credit-card statement history in the accessible files. Consequently there is no real card set for which a model PD or score can truthfully be reported.

## Available parser regression fixtures

The following aliases refer to the nine existing local document fixtures. They are regression materials, not proof of real-world compatibility. The active universal parser currently returns a bank DataFrame for fixture 7 and a utility record for fixture 8; fixtures 1–6 and 9 do not complete the active bank-only parser path. The earlier OCR/entity pass is listed to identify missing fields without exposing source text.

| Alias | Observed class / layout | Fields found | Missing fields | Validation / coverage | Frozen feature coverage |
|---|---|---|---|---|---|
| Fixture 1 | Utility, scanned, 1 page; OCR token confidence 0.949 | Consumer number, bill amount, payment-discipline marker | Due date | Utility validation passed; field coverage 0.50 | 0/4 |
| Fixture 2 | Utility, scanned, 1 page; OCR token confidence 0.939 | Units consumed, payment-discipline marker | Bill amount, due date | Partial; required utility fields missing; coverage 0.33 | 0/4 |
| Fixture 3 | Utility, scanned, 1 page; OCR token confidence 0.853 | Units consumed, bill amount, payment-discipline marker | Due date | Partial; required utility field missing; coverage 0.50 | 0/4 |
| Fixture 4 | Utility, scanned, 1 page; OCR token confidence 0.870 | Payment-discipline marker | Bill amount, due date | Partial; required utility fields missing; coverage 0.17 | 0/4 |
| Fixture 5 | Utility, scanned, 1 page; OCR token confidence 0.839 | Bill amount, payment-discipline marker | Due date | Partial; required utility field missing; coverage 0.33 | 0/4 |
| Fixture 6 | Utility, scanned, 1 page; OCR token confidence 0.620 | Due date, payment-discipline marker | Bill amount | Partial; required utility field missing; coverage 0.33 | 0/4 |
| Fixture 7 | Bank, digital, 2 pages | 25 transaction rows; date, amount, type, narration, closing balance | None in required bank row schema | 25/25 rows passed structural validation; parser coverage 0.60 | 0/4 |
| Fixture 8 | Utility, digital, 1 page | Consumer number, due date, usage, bill amount, payment-discipline marker | None in required utility schema in prior entity pass | Utility validation passed; coverage 0.83 | 0/4 |
| Fixture 9 | Salary, scanned, 1 page; OCR token confidence 0.784 | Gross salary, net salary, HRA, PF contribution marker | Salary field coverage incomplete | Partial salary extraction; coverage 0.38 | 0/4 |

No fixture contains a complete, verified six-month card history. Model eligibility is therefore false for every fixture; no PD or score was generated.

## Historical upload metadata without recoverable source files

The read-only database recheck found five additional completed-status records (bank/utility/salary types) whose stored PDF files were absent, plus one failed bank-document record whose file was absent. The failed record has no persisted failure detail. Their precise extraction result cannot be reconstructed or attributed to OCR, parser, eligibility, or rendering without the files or logs.

## Implemented in this repair

- Added an independent bank financial-health summary for monthly credits/debits/net flow, cash-flow variability, observed balances, recurring narration patterns, keyword-based possible debt payments, explicit returned-payment terms, and salary-labelled credits. Transaction descriptions are not included in the summary.
- Persisted the aggregate-only financial-health object in the existing application-scoped audit store and exposed it to authenticated borrower refresh and lender application detail.
- Added a separate borrower/lender panel. It is explicitly described as supporting analysis, not a credit PD or a lending threshold.
- Expanded card-field extraction to conservative common label variants, Indian day-first dates and rupee amounts, and page/line provenance. Native PDFs use explicit required-field coverage; scans require both that coverage and measured Tesseract token confidence. These are extraction-quality checks, not claims of ground-truth accuracy. Fields remain absent unless explicitly present, and six-month/account/status eligibility checks remain authoritative.
- Removed raw statement text and transaction-row debug output from the active table extraction and consistency-validation paths.

## Verification and limitations

- Bank-upload A/B reprocessing: both classified and parsed as bank statements; 7/7 rows valid in each; card eligibility correctly false.
- Financial-health, Phase 2E parser, and Phase 2D evidence contract tests: **132 passed** (one protected-artifact-manifest test excluded from that run). Phase 2F shadow-scorecard/reliability tests: **44 passed**.
- The protected-artifact manifest check does not pass in this checkout: 28/34 tracked references are missing or differ from the manifest, including two production scoring artifacts. This task did not edit model/artifact files, but their integrity cannot be attested from this workspace snapshot.
- The card-assessment route test could not collect because `httpx2`, required by the installed Starlette TestClient, is missing.
- Frontend production build passed with Vite.
- Read-only PostgreSQL connectivity and existing document/audit metadata retrieval succeeded. The new financial-health write/read route itself was not exercised against an authenticated upload because no active borrower browser session was available. A live authenticated browser upload therefore remains unverified.
- Extraction accuracy against annotated ground truth is **not measured**. No real credit-card set was scoreable. Synthetic and existing fixture behavior is not reported as real-world accuracy.
