# PRISM real-document assessment integration

**Status:** document-to-model-to-PostgreSQL workflow is implemented and passes synthetic backend integration tests. The requested live borrower browser login/upload has not been completed: the browser reached the borrower landing page, where a human must complete authentication. The frozen scorecard remains `PHASE_2B6_INCONCLUSIVE` and is not for lending decisions.

## What was missing

The borrower upload route previously handled supporting bank, salary, and utility documents, but did not turn card statement files into the four Phase 2E evidence features or persist frozen Phase 2F assessments against applications. There was also no borrower-scoped refresh/report path or lender retrieval of the same experimental record. This implementation adds a separate, opt-in route and storage table; it does not route card evidence through the legacy bank/salary/utility score.

## Implemented flow

1. An authenticated borrower session is checked against its application and recorded DPDPA consent. Card-specific processing consent is required on the upload.
2. Up to 12 PDF/JPG/JPEG/PNG files (15 MB each) are saved with the existing application-scoped document store. PDF text extraction, the existing scanned-PDF OCR service, and Tesseract image OCR are used.
3. A conservative classifier requires a card-statement title and card-summary signals, while rejecting bank statements with strong bank markers. The parser extracts only explicitly labeled fields. Missing values remain absent; differing duplicate values become conflicts. Statement dates/period, amount due, minimum due, payment date, and due date are retained as auxiliary observations with source-line references; they do not substitute for model inputs.
4. The six statement records must meet Phase 2E identity, coverage, provenance, consistency, product, consent, currency, and explicit repayment-status rules before Phase 2F inference. Non-card, unreadable, missing-month, duplicate/conflicting, or low-confidence evidence stays unscored. No absence-of-transaction heuristic is used.
5. Eligible evidence is passed into the existing `run_equivalence_path` and frozen Phase 2F scoring service. The assessment, document IDs/findings, validated feature vector, WoE values, contribution trace, PD, uncapped score, reason codes, recommendations, consent record, and artifact hash are written to the separate `prism.experimental_assessments` table. An audit event is written. A unique application/input hash makes repeated identical uploads idempotent.
6. Borrower latest/by-ID routes are scoped to the borrower and application. The existing lender role guard protects lender routes, which read the same assessment row. What-if uses the existing guarded frozen scoring helper and never writes a new assessment. The PDF report is generated from the persisted row and paginates its contents.

## Feature definitions

The feature order and formulas are taken from the frozen Phase 2D/2E contract in `backend/phase2/credit_evidence/feature_adapter.py` and `build_phase2d_outputs.py`:

| Frozen feature | Derivation from validated statement evidence |
|---|---|
| `recent_delinquency_level` | Explicit delinquency severity in the latest month of the six-month window. Zero is accepted only when the statement explicitly records current/zero severity. |
| `months_with_delinquency` | Count of the six explicit monthly severities greater than zero. |
| `payment_to_statement_ratio` | Sum of payments explicitly applied to the six statements divided by the sum of each matching statement balance floored at zero; a positive denominator is required. |
| `mean_statement_balance` | Arithmetic mean of the six signed statement balances, in their original currency units. |

No feature imputation, bank-transaction linkage, currency conversion, retraining, recalibration, score clipping, or operational tier assignment is performed.

## Synthetic files and actual model outputs

[`backend/phase2/real_evidence/generate_statement_fixtures.py`](../backend/phase2/real_evidence/generate_statement_fixtures.py) creates three six-month profile sets for the October 2026 cutoff. [`ground_truth.json`](../backend/phase2/outputs/synthetic_statement_fixtures/ground_truth.json) contains each statement's structured evidence, expected feature vector, frozen WoE bins/contributions, PD, score, artifact hash, and synthetic-only limitation. The output directory contains 18 regular statement PDFs, one scanned PDF, and one scanned PNG (20 files total).

| Profile | Recent delinquency | Months delinquent | Payment/balance ratio | Mean balance (INR) | Frozen PD | Uncapped score |
|---|---:|---:|---:|---:|---:|---:|
| Consistent | 0 | 0 | 0.7973684210526316 | 1266.6666666667 | 0.1705106271229297 | 498.0216872345 |
| Moderate | 1 | 3 | 0.4980061349693252 | 2716.6666666667 | 0.4125849885889706 | 409.3880353961 |
| Repeated | 9 | 6 | 0.1351320132013201 | 10100 | 0.7502095441100636 | 304.5748321486 |

The six-file integration test uploads the repeated profile, including its scanned September PDF. Extracted numeric values match the fixture ground truth; PD and score match the generator's actual Phase 2E/Phase 2F outputs. Frozen artifact SHA-256: `DE1C1106759ED00F53F208C5185D63B3D8D22DB477D3A3EFD36132B5830E4CA6`.

## Persistence, lender, PDF, and test evidence

The additive SQL migration is [`backend/database/migrations/003_experimental_assessments.sql`](../backend/database/migrations/003_experimental_assessments.sql). It creates only the new experimental assessment table and its indexes. It was applied to the configured `prism_db`; tests confirmed inserts, uniqueness/idempotent replay, borrower refresh, lender retrieval, what-if immutability, and report generation. Test users, applications, document rows, assessments, and audit events run inside a rollback-only outer transaction. Therefore, **no permanent assessment ID is claimed from these tests**; the response/ID and DB record were verified during each test transaction, then synthetic rows were rolled back.

Verification performed:

- Focused extraction + persistence + auth + lender + what-if + PDF suite: **3 passed**.
- Upload/scoring/Phase 2F/2G/Phase 1/document-storage regression selection: **107 passed, 3 subtests passed**.
- After fixing the lender summary helper's backward-compatible call signature: lender score-filter plus new assessment tests **5 passed**.
- Frontend contract tests: **3 passed**. Vite production build: **passed**. Changed Python modules compile.
- PDF test opens the generated response with PyMuPDF and confirms the persisted assessment ID, full-precision score, and PD are present in extracted report text.
- Local PostgreSQL inspection confirmed `prism.experimental_assessments` exists with its 21 columns and no leftover synthetic rows after rollback. A Vite-origin `OPTIONS` preflight returned HTTP 200 with the expected `session-id` and `content-type` headers.
- UI browser: local Vite borrower landing page opened successfully. **The authenticated file upload was not run in the browser**, because a human must complete the borrower login/OTP interaction. No login automation or authentication bypass was used.

Full backend suite triage:

- Unfiltered collection is blocked because `backend/phase2/tests/test_phase2c.py` requires the missing historical `backend/phase2/feature_compatibility/protected_hashes_before.json`.
- Running the rest of the suite excluding that module yielded **343 passed, 53 failed, 3 errors, 10 subtests passed** after the lender compatibility fix. The 53 remaining failures group as: 8 Phase 2 source/output/hash-baseline checks, 41 Phase 3S generated artifact/manifest checks, and 4 Phase 4 demo API checks that each fail because `backend/phase4/outputs/demo_scenarios.json` is absent. The 3 Phase 2 semisynthetic setup errors fail because `backend/phase2/berka/account.asc` is absent. The failing historical checks were not suppressed or repaired using fabricated data. The two lender helper failures seen on the first run were integration regressions; both now pass.
- The full suite is not green; missing baselines were not fabricated or removed.

## Scope and limitations

- This is a controlled-label document adapter, not a general statement-layout understanding system. A real issuer whose labels/layout differ may yield structured gaps and no score. Validate on representative real statements before wider use.
- OCR confidence gates scoring at 0.90. Statement page-level provenance identifies `page:1` for single-page files; for multi-page statements the current OCR/text adapter records a page range and source lines rather than per-field page numbers.
- Fraud checks are not run by this score endpoint; the response must not imply they were evaluated.
- The frozen PD is raw/un-calibrated and the score may be outside the usual reference range. Model status is inconclusive; no decision tier is issued and no lending decision may use this result.
- Borrower/lender UI production behavior has not been authenticated and validated end-to-end in a browser. The backend path is verified with FastAPI tests and PostgreSQL; a human browser login/upload remains the final handoff.
