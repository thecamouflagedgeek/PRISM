# PRISM scorecard recovery — engineering acceptance report

Verified 10 October 2026 in `PRISM_INTEGRATED`, branch `freia-hazel-merge`. Existing uncommitted work was preserved. The synthetic demonstration workflow is restored; this is not a production-readiness or scientific-validation claim.

## A. Root causes

- PDF extraction needed an explicit encrypted-document rejection and safe handling of corrupt PDFs. Native extraction quality was incorrectly treated as an OCR confidence value.
- Card classification and field aliases missed the dossier's monthly-statement labels, explicit payment allocation, fictional card reference, and synthetic repayment codes. Equivalent date/month labels could be mistaken for conflicting evidence.
- General currency cleanup consumed line breaks; amount matching split comma-grouped amounts and could capture reference/date fragments. Bank parsing did not reliably preserve debit/credit column roles or wrapped narration.
- Salary and utility uploads retained only one file per category. Legacy assessment processing could block the independent card/bank workflows. Duplicate effects and partial failures could lose useful results.
- The March–August dossier is outside the default October card window. The six original bank PDFs omit page declarations, so their evidence gate correctly rejects scoring.
- Account-reference hashing lacked a configured stable salt. Refresh retrieval and lender navigation did not consistently restore both assessment types; the lender View action previously opened an empty workspace.
- Credit PDF text wrapping allowed multiline payloads to overlap. Signed model contributions needed logit units, rather than implied score points.

## B. Code changes

- `backend/phase2/credit_parser/document_extraction.py`: PDF handling, classification, explicit aliases, equivalent dates, narrowly tagged synthetic status interpretation.
- `backend/ingestion/universal_pipeline.py`: currency/amount parsing, column-aware transaction extraction, provenance, measured field coverage, stable account-reference hashing.
- `backend/route/experimental_assessment_routes.py`: canonical extraction, controlled 422 errors, optional historical cutoff, parser-aware idempotency, application ownership filters, safe operational logs, readable paginated PDF.
- `backend/route/bank_cashflow_routes.py`: multiple supporting files, consent enforcement, deterministic supporting extraction, statement continuity, idempotency, exact assessment retrieval, safe logs.
- `backend/route/consent.py` and `lender_routes.py`: consent restoration and separate persisted bank/card summaries.
- Frontend `src/services/api.js`, new `assessmentWorkflow.js`, `App.jsx`, `UploadPage.jsx`, `ProcessingPage.jsx`, `ResultsPage.jsx`: all selected files, explicit cutoff, bounded request timeout, independent scoring and error states, saved-result recovery, document findings and update navigation.
- Frontend new `lenderAssessmentContract.js`, `LenderDashboard.jsx`, `AssessmentPage.jsx`, `ExplainabilityPage.jsx`: retrieve the selected application, preserve per-document findings, show actual score/PD/index and signed logit contributions.
- Added backend recovery regression tests and frontend workflow/lender tests; updated obsolete extraction-method/confidence expectations in existing card tests.
- Configured an ignored local account-reference salt and installed the already-declared HTTP test dependency. Secrets are not included in evidence files.

## C. Document validation

Exact archive: `C:/Users/hp/Downloads/PRISM_Synthetic_Financial_Documents.zip`. Unchanged originals and archive identity are under `backend/test_fixtures/aarav_original/`.

- Browser selected and submitted all **24 original PDFs**: six each bank, card, salary and utility, March–August 2026. All extracted; no original PDF was rejected as unreadable.
- All **48 original bank transactions** match the supplied transaction ground truth. Six bank months and six card months aggregate independently. Twelve supporting documents remain supporting evidence, not frozen-model inputs.
- Original bank assessment remains unscored with `STATEMENT_PAGE_COVERAGE_NOT_VERIFIED`.
- Six separate copies under `aarav_page_repaired/` add an explicitly marked page declaration only. They produce the eligible bank result. Original files are untouched; the gate was not weakened.
- PostgreSQL application 77 contains **30 documents**: 24 originals plus six separately repaired bank statements.
- Corrupt and encrypted PDFs return controlled 422 responses. Scanned documents without usable OCR evidence do not receive fabricated extraction confidence.

## D. Credit-card scoring

Explicit historical snapshot: exclusive cutoff **2026-09**, observed months **2026-03 through 2026-08**. The default application-month window remains unchanged.

| Frozen input | Verified value |
|---|---:|
| mean_statement_balance | 29666.6666666667 |
| months_with_delinquency | 4 |
| recent_delinquency_level | 1 |
| payment_to_statement_ratio | 0.373595505617978 |

Actual frozen inference: **uncapped score 454.635898966963**, **raw uncalibrated PD 0.2727810906249319 (27.28%)**. No lending tier is invented.

Frozen artifact `backend/phase2/outputs/phase2f/frozen_shadow_scorecard.json` SHA-256:
`DE1C1106759ED00F53F208C5185D63B3D8D22DB477D3A3EFD36132B5830E4CA6` — unchanged.

Signed logit contributions: balance −0.0651262103; delinquent months +0.8733442755; recent delinquency −0.2545070164; payment ratio −0.2858281030. Actual adverse reason: repeated repayment delinquency.

## E. Bank assessment

Six months, **48 transactions**, average monthly credits **₹95,500**, expenses **₹68,858.33**, observed balance **₹195,002.08**, minimum balance **₹103,450**, identified monthly debt payments **₹9,200**, income CV **0.027426**.

| Indicator | Value | Score contribution |
|---|---:|---:|
| surplus_month_rate | 1.0 | 150.00 |
| expense_to_income | 0.278970 | 41.85 |
| income_regularity | 0.973306 | 116.80 |
| liquidity_buffer | 0.943977 | 84.96 |
| debt_burden | 0.903665 | 81.39 |

Separately repaired evidence produces **experimental index 775**. This index produces **no PD and no risk tier**. Original evidence remains insufficient.

## F. Database

Committed synthetic application **77**, borrower user **62**:

- Card: `be8fae13-474d-42e4-ad52-4352ca81ccb4`.
- Original insufficient bank: `9290dee6-c7ac-43e2-99e8-b63447d84161`.
- Repaired bank: `3715d79b-af6e-4fb4-8dd4-7ab78af5d939`.

Verified authenticated retrieval, refresh, lender access and idempotent submissions. `scorecard-recovery-live-evidence.json` records committed results. `scorecard-recovery-evidence.json` is rollback-only test evidence; its test assessment IDs are not retained records.

## G. Frontend and browser

Executed normal local borrower and lender OTP flows in the isolated browser application, uploaded the full original dossier, observed card scoring and the original bank insufficiency, updated with separately repaired bank files, refreshed saved results, and retrieved the same application as lender. No authentication bypass was used.

Executed card what-if: payment ratio 0.9 changes score **454.6 → 458.4**, PD **27.28% → 26.26%**. Bank what-if: income ₹110,000 changes index **775 → 790**. Persisted baselines remained unchanged.

Downloaded both reports. Visual inspection exposed overlap in the initial credit PDF; the export was fixed and the final two-page credit and one-page bank PDFs were rendered and visually checked. Final PDFs reference committed application 77. The final PDF correction was checked through authenticated export/API and rendered files, not another full browser upload cycle.

Browser evidence: `recovery-original-browser.jpg` and `recovery-lender-explanation.jpg`. `recovery-lender-browser.jpg` is an earlier empty-workspace diagnostic, not passing acceptance evidence.

Request timeout and terminal error states are implemented and regression-tested; server sessions still expire and require reauthentication. Isolated review servers use ports 5174 and 8001; existing user servers on 5173 and 8000 were preserved. Restarting the isolated backend invalidated its previous in-memory sessions.

## H. Testing

- Targeted backend acceptance/regression: **24 passed** (`recovery-targeted-final.txt`). Includes PDF lifecycle, complete ground-truth transaction matching, original/repaired evidence, actual inference, supporting uploads, idempotency, persistence, ownership, lender retrieval, what-if and PDF.
- Frontend: **10 passed**; production build passed (74 modules).
- Full backend collection blocked by missing `backend/phase2/feature_compatibility/protected_hashes_before.json`.
- With that collection module excluded: **361 passed, 57 failed, 3 errors, 10 subtests passed** (`recovery-broad-suite-final.txt`). No skipped tests were reported. This is not a green full suite.
- Remaining failures concern absent historical/generated research outputs and fixtures, protected-manifest mismatches, and legacy scorer tests. Missing Berka `account.asc` causes three errors. Four legacy unit tests expect a removed `_to_score` API.
- Production model and binning hashes match their manifest. Historical protected manifest is not clean: 99 entries, 42 absent, 15 mismatched. Existing historical differences were not repaired by rebuilding or modifying frozen research artifacts. Some protected historical source entries also include deliberately changed integration/UI files.

## I. Remaining limitations

- Original bank PDFs need verified page-completeness evidence; separately repaired synthetic copies demonstrate the eligible path only.
- Card scoring uses an explicitly labeled historical September snapshot. October default eligibility is not silently changed.
- Fictional repayment codes and simplified due dates test extraction/formula compatibility; they do not establish issuer-certified repayment history or real-world model validity.
- The frozen Taiwan-trained experimental model retains `PHASE_2B6_INCONCLUSIVE`; PD is uncalibrated and neither output is approved for credit decisions, an RBI certification or a CIBIL score.
- Real issuer layouts and full fraud review are not established by this synthetic acceptance test. UI only reports checks actually returned.
- Authentication uses local OTP logging and in-memory expiring sessions; production SMS and persistent sessions remain deployment work.
- The broader research suite and historical integrity inventory remain unresolved. The restored synthetic demonstration should not be represented as a fully validated production lending platform.

Final deliverables: `output/pdf/PRISM-synthetic-credit-assessment.pdf` and `output/pdf/PRISM-synthetic-bank-assessment.pdf`.
