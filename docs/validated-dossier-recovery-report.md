# Corrected synthetic dossier acceptance - 11 October 2026

Second follow-up: the user's pasted current response contains **one** extracted card (March, document814) and **one** bank month/eight transactions, with corrected dates and explicit September cutoff. The remaining failure was an incomplete selected set, not the repaired fixture dates. Added a whole-folder selector that places all monthly PDFs into four upload categories and reads the selected manifest's explicit cutoff; it requires normal supporting/card consents. Recognized partial March-August synthetic bank/card selections list missing months and cannot submit. Explicit multipart filenames preserve the PDF basenames for directory-selected files. A fresh browser test first reproduced one-March selection, verified the disabled submit/missing-month message, selected the actual Downloads directory, and passed the complete scoring/refresh/simulation/PDF/idempotency/lender journey: **1 passed (24.7s)**, log `docs/downloads-folder-browser-test.txt`, evidence `docs/live-demo/downloads-folder-run/`. Tests used isolated ports8001/5174 without interrupting the user's backend8000 or frontend5173. Frontend10 tests and the final production build passed. No scoring or evidence gate change.

Follow-up: the user's actual `C:/Users/hp/Downloads/PRISM_Synthetic_Financial_Documents` folder still contained defective original PDFs. Its originals were hash-verified and preserved in sibling `PRISM_Synthetic_Financial_Documents_ORIGINAL_BACKUP_20261011`; all 24 PDFs and ground-truth files were replaced with validated copies, then hash-verified against the corrected manifest. README.txt now documents explicit cutoff and all-six-per-category selection. A complete new manual browser journey directly from that Downloads directory passed in 18.3 seconds, including scoring, refresh, simulations, exports, idempotency and lender retrieval. Evidence: `docs/downloads-manual-browser-test.txt` and `docs/live-demo/downloads-manual-run/`. Initial follow-up attempts stopped at OTP because the manually restarted backend logged outside the demo test log; the PRISM reload worker was stopped and the demo launcher restored before the passing run. Previously persisted insufficient assessments are preserved; re-upload is required to assess changed file bytes.

**PASS for this fictional local demo:** three fresh authenticated browser journeys (including ordinary manual upload), 24 PDFs each, displayed credit **454.64**, raw uncalibrated PD **27.28%**, bank index **775**. Read-only PostgreSQL verification and six downloaded PDFs corroborate each application's IDs and values.

## Root causes

Before repair, normal UI upload of all 24 originals reproduced terminal insufficient evidence. All original banks lacked declared page coverage; all six cards had due dates before issue dates and incomplete explicit observation/payment linkage. October's default credit window requires April-September whereas this evidence covers March-August. Contradictory dates now block original cards even with September cutoff. Originals remain unchanged negative fixtures.

Earlier one-file handling and positional amount extraction explained one-month/eight-row and zero-expense outcomes; array upload and explicit debit/credit parsing already fixed those defects. This request's original reproduction received six months, 48 rows and nonzero expenses. The remaining blockers were fixture quality, chronology and explicit historical cutoff. No validation gate was removed.

## Corrected evidence

`tests/fixtures/prism_demo_validated/` holds 24 corrected one-page native-text PDFs, original/corrected hashes, ground truth and individual validation reports. All 24 pages were extracted and visually checked. The unchanged bank ledger has 48 rows, 42 debits and six credits; running balances, opening/closing continuity, secure linkage, page coverage and extraction thresholds pass. Supporting salary/utility evidence never enters the frozen credit features. Utility periods denote statement months with intra-month due/payment dates; they are not completed-period card billing contracts.

Card issue day 1, preceding-calendar-month purchase dates, due day 20 for CURRENT and day 15 for DELINQUENT are documented new fictional schedules. Bank-matching payments remain day 17 with unchanged amounts. Each card declares matching statement/payment reference TEST-CARD-4821-YYYY-MM, SETTLED status, month-end observation and exclusive cutoff 2026-09. Original constructed severity labels 0,0,1,1,2,1 are retained, not inferred DPD or issuer-certified history. July severity 2 is explicitly a synthetic prior-history assumption. Zero corrected PDFs were rejected.

The development-only **Load Validated Synthetic Dossier** selector hash-checks the exact corrected files, selects them in ordinary controls and shows the explicit historical cutoff. Manual upload uses those same endpoints, consents and gates, with an explicit **Use historical cutoff 2026-09** action. Nothing injects scores.

## Calculations

| Frozen feature | Actual value |
|---|---:|
| recent_delinquency_level | 1 |
| months_with_delinquency | 4 |
| payment_to_statement_ratio | 0.3735955056179775280898876404 |
| mean_statement_balance | 29666.66666666666666666666667 |

Frozen score **454.635898966963**, raw PD **0.2727810906249319**. Independent browser arithmetic uses truth plus immutable bins/coefficients; tolerances 1e-8 score/1e-10 PD. Rechecked frozen artifact SHA-256: `DE1C1106759ED00F53F208C5185D63B3D8D22DB477D3A3EFD36132B5830E4CA6`. No feature definition, weight, formula or cap changed. Credit chart 300-900 bounds and score percentage positioning were removed; only bank retains that range. Fresh journeys have no forced 300-400 fallback or stale insufficient assessment.

| Bank factor | Actual value |
|---|---:|
| surplus_month_rate | 1.000000 |
| expense_to_income (health component) | 0.278970 |
| income_regularity | 0.973306 |
| liquidity_buffer | 0.943977 |
| debt_burden | 0.903665 |

BANK_FINANCIAL_HEALTH_INDEX_V1 computes **775**, no PD. Independent ledger calculation verifies average income 95500, expenses 68858.33, balance 195002.08, EMI 9200, minimum balance 103450 and sample income CV 0.027426.

## Three fresh database records

| Run | Selection | Application | Credit ID | Bank ID |
|---|---|---:|---|---|
| 1 | Loader | 126 | d519edef-4e5e-4871-aed8-5508446a444a | ddb16813-beb4-4181-96da-ae26d257caef |
| 2 | Manual | 127 | 7a9fea03-351e-4db5-9fac-73ce927bd9e5 | 72fc758d-17bd-4fe0-8759-1aeaa61876d0 |
| 3 | Loader | 128 | 8dfad52a-e74e-4c41-9b54-0b49183e30c0 | 516f1eac-57f0-4c6a-9224-a2894bde2985 |

Each has 24 persisted documents, exactly one credit and one bank assessment. Repeat upload preserves IDs. All runs check normal OTP/consents, all visible filenames, server multipart receipt (18 bank/support plus six card), completed processing, both numerical scorecards, refresh, both what-ifs, PDF export, baseline preservation and authorized lender View of exact IDs. No unexpected 401/404/500 was captured. Ratio 0.9 simulation gives credit 458.4/PD26.26%; bank income110000 gives790. Persisted baseline remains454.64/775.

Responses save per-document classification, month, actual/declared pages, linkage, quality, validation/rejection reason, and combined nine-stage trace through ASSESSMENT_PERSISTED. Aggregation records six bank months,12 supporting files,48 rows,42 debits,6 credits and successful reconciliation. Evidence and screenshots/PDFs: `docs/live-demo/validated-run-{1,2,3}/`; database corroboration: `docs/live-demo/validated-database-verification.json`. Earlier app117 reports are historical, not evidence for this corrected set.

## Changes and checks

Changed: `backend/phase2/credit_parser/document_extraction.py`, `backend/route/{experimental_assessment_routes,bank_cashflow_routes,demo_fixture_routes}.py`, `backend/ingestion/universal_pipeline.py`, frontend `pages/{UploadPage,ResultsPage,AssessmentPage}.jsx`. Added fixture builder/validator/read-only verifier and corrected PDF directory; updated backend card/loader/recovery tests and browser regression. Parser versioning prevents reusing older chronology-contract records. Invalid supporting-file rejection is isolated from otherwise valid bank scoring. Existing user changes remain intact.

- Three repeated browser tests: **3 passed**, `docs/validated-dossier-browser-tests.txt`.
- Original negative browser reproduction: **1 passed**, `docs/original-reproduction-2026-10-11.txt`.
- Targeted backend: **29 passed**, `docs/validated-dossier-backend-tests.txt`, including wrong chronology/reference and invalid supporting-file isolation.
- Frontend tests: **10 passed**. Production build passed (74 modules); stale browser-data warning is nonfatal.
- All24 fixture pages and downloaded report pages visually checked, without overlapping/clipped fields.

## Remaining limits

The earlier broad suite remains 361 passed,57 failed,3 errors, mostly absent research/historical fixtures, protected-manifest differences and obsolete scorer tests; it was not rerun or declared green. See `docs/scorecard-recovery-report.md`. Frozen model remains PHASE_2B6_INCONCLUSIVE, uncalibrated and not validated for Indian lending. Synthetic categorical history cannot establish real issuer risk or genuine-layout coverage. Local OTP, production SMS and in-memory60-minute sessions remain deployment work; restarting backend requires login. This establishes corrected local demo behavior, not production readiness. Wrong cutoff and genuinely insufficient future evidence still correctly fail.
