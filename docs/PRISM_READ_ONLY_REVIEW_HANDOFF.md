# PRISM — Technical Handoff for a Read-Only Review

- **Snapshot date:** 13 October 2026 (Asia/Kolkata)
- **Repository:** `PRISM_INTEGRATED`
- **Current branch observed:** `freia-hazel-merge`
- **Audience:** the next coding agent, acting strictly as an independent reviewer

## 1. Assignment and authority boundary

The next agent is authorized to perform **review checks only**. It must inspect the existing implementation, configuration templates, documentation, fixtures and tests; run safe, read-only checks when their side effects are understood; and report evidence-based findings. It must not change, generate, format, repair, refactor, migrate, install, stage, commit, upload, delete, or otherwise write project or user data. It must not contact external services or perform live borrower/lender workflows. Do not edit this handoff either.

For each finding, report severity, exact file and line, a concise explanation, reproducible evidence, user or model risk, and a suggested remedy as a recommendation only. Separate verified facts from inference and unknowns. If a check could write to the configured database, alter a fixture, send an OTP, upload documents, or change a running service, do not execute it; explain the limitation. Never print or repeat secrets, OTPs, passwords, full phone numbers, account identifiers, personal transaction narrations, or private statement contents in the report.

## 2. Non-negotiable review standard: no hardcoded outcomes

“Nothing hardcoded” means assessment outcomes must come from the evidence and the documented, versioned calculation or model—not from the applicant name, phone, file name, folder, demo scenario, fixed fallback response, or expected output. The reviewer must search for and report:

- applicant-specific scores or score lookup tables; file-name or persona-based score routing; fabricated features, transactions, identity matches, income, payment history, model confidence, fraud findings, or missing months;
- success-shaped fallback scores when parsing, identity, consent, data quality, storage, or model execution fails;
- user- or lender-visible claims that synthetic/demo fixtures are real bank records or that an experimental index is a validated credit score;
- hardcoded credentials, OTPs, passwords, personal identifiers, local paths, account secrets, and private URLs;
- test/demo fixtures or feature flags that can silently enter ordinary borrower/lender traffic.

Do **not** flag every literal as “hardcoding.” Documented scoring weights and transformations, frozen model coefficients and bins, enums, schemas, rendering bounds, localization strings, protocol constants, and explicit configurable defaults can be legitimate. Check their source, version, purpose, separation, provenance, and whether runtime evidence—not identity—determines the result. Any score change must be reproducible from the same evidence and model version. Missing or invalid evidence must follow the documented failure contract rather than receive invented values.

## 3. System map

PRISM is a local prototype with a React/Vite browser application and a FastAPI/SQLAlchemy backend. PostgreSQL is configured via `PRISM_DATABASE_URL`; schema objects are under the PostgreSQL `prism` schema. The backend loads `backend/.env` relative to its source. `backend/main.py` mounts the ordinary API router and a separate experimental shadow router, exposes `/` and `/health`, and exposes `/ready` through the Phase 4 readiness check. The Phase 4 demo router is mounted only when `ENABLE_PHASE4_DEMO` is enabled. CORS has local Vite origins plus configured `PRISM_CORS_ORIGINS`.

### Backend areas

- `backend/auth/`: OTP signup/verification and role selection. A borrower session is short-lived server-side state; lender authorization is controlled by `PRISM_LENDER_PHONES` and a lender role. Auth/session data flows through `backend/core/session_store.py` and `backend/auth/store.py`.
- `backend/route/`: ordinary auth, consent, upload/assessment, bank cashflow, credit-card assessment, lender, dashboard, explanation, fraud, parsing, validation, and synthetic-fixture endpoints. `routes.py` assembles the standard route modules.
- `backend/ingestion/`: document extraction, file classification/parsing, bank layouts and transaction normalization. Relevant modules include `universal_pipeline.py`, `bank_transaction_pipeline.py`, `bank_layout.py`, `identity.py`, and `rpt_ingestion.py`.
- `backend/document_validation/`, `backend/validation/`: document quality, structural and consistency validation.
- `backend/features/`: bank cash-flow index/snapshot, salary, utility, card, and financial-health features.
- `backend/fraud/`: rule/configuration-based transaction fraud signals; these signals are separate from a model-derived default probability.
- `backend/scoring/`: the legacy/research scoring pipeline, score scaling, rules, binning, logistic regression, confidence, reports, and validation utilities. Its existence does not mean every product flow calls a trained model.
- `backend/database/`: SQLAlchemy connection, models, CRUD, and ordered SQL migrations.
- `backend/phase2/`: separate research/evidence contract, card parser and frozen shadow scorecard. `backend/phase2/shadow_api/` is a distinct opt-in JSON API.
- `backend/phase4/`: separately gated controlled demonstration API and scenario builder; not the ordinary borrower document-upload endpoint.
- `backend/storage/`, `backend/services/`, `backend/explain/`, `backend/llm/`, `backend/utils/`: storage adapters and service, explanation, language-model, and utility code; audit where they are invoked before making claims about production use.

### Frontend areas

`prism-frontend/src/App.jsx` currently coordinates application screens with page state and session restoration. It is not a conventional route-per-page architecture; verify every transition and refresh path. Main screens include landing, login/OTP, consent, upload, processing, results, borrower dashboard, lender login/dashboard, applications and assessment detail, document review, fraud intelligence, explainability, and audit log. Shared UI lives in `components/`; API clients/workflow contracts live in `services/`, `api.js`, and `assessmentContract.js`; page components and styles live in `pages/`; shared CSS is in `App.css`, `index.css`, and the theme stylesheet.

Hindi/English localization is configured in `src/i18n.js` using `i18next` and `react-i18next`, with JSON resources at `public/locales/en/translation.json` and `public/locales/hi/translation.json`. `LanguageContext.jsx` and `services/i118n.js` also exist; trace which path each screen uses rather than assuming every visible string is covered. Language preference uses browser storage. Inspect parity, missing-key behavior, dynamically created text, accessibility labels, date/number formatting, and navigation across borrower and lender flows.

## 4. Distinct scoring and assessment paths — do not conflate them

### A. Bank Financial Health Index V1 — multi-month bank cash flow

`backend/features/bank_health_index.py` calculates `BANK_CASHFLOW_EXPERIMENTAL` (`BANK_FINANCIAL_HEALTH_INDEX_V1`). It is a fixed-weight, descriptive index, not a trained credit-risk model. Its published mapping is `round(300 + 600 × weighted normalized health)`. The documented factor weights are surplus-month rate 0.25, expense-to-income health 0.25, income regularity 0.20, liquidity buffer 0.15, and explicit debt-payment burden 0.15. Missing factors are excluded and the remaining weights renormalized; unknown debt is not silently treated as zero debt. See `backend/features/BANK_FINANCIAL_HEALTH_INDEX.md` for exact transforms and assumptions.

The full-history evidence gates documented there include three consecutive observed months, period coverage for represented months, consistent account/currency, configured HMAC account-reference salt for cross-statement linkage, extraction quality at least 0.80, transaction ordering, declared page sequence, resolved duplicates/transfers/refunds/reversals, and reconciliation of declared opening/closing and running balances. Failure can persist observations with null score. Never characterize this path as a bureau score, PD, or lending decision.

### B. Cash-flow Snapshot V1 — one-statement thin-file path

`backend/features/thin_file_score.py` calculates `PRISM_CASHFLOW_SNAPSHOT_V1`. The documented formula uses the same 300–900 presentation mapping and factor family, with unavailable factors omitted and weights renormalized. One observed month has unknown income regularity; missing debt remains unknown. The snapshot is an uploaded-period descriptive score, not a trained/validated risk model or bureau equivalent. Passwords for encrypted PDFs are request-only and must not be persisted.

`POST /assess/bank-cashflow` accepts `assessment_profile` in `history`, `snapshot`, `auto`; the handler’s default is `history`, while the frontend helper currently defaults to `auto`. In `auto`, eligible history takes precedence, otherwise the snapshot path is attempted. Inspect the live call chain and tests for exact eligibility and error presentation. `docs/live-demo-workflow.md` documents differing synthetic March/August scores (696 and 759); treat these strictly as fixture regression examples, never expected scores for arbitrary data. Snapshot limitations and gates are in `backend/features/THIN_FILE_CASHFLOW_SNAPSHOT.md`.

### C. Frozen credit-card shadow scorecard — Phase 2F

`backend/phase2/shadow_api/routes.py` exposes `/experimental/shadow-golden-request`, `/experimental/shadow-assess`, `/experimental/shadow-assess/debug`, and `/experimental/shadow-simulate`. It is opt-in via `ENABLE_EXPERIMENTAL_SHADOW_SCORING` (default off), accepts structured JSON rather than uploaded PDFs, requires the documented repayment evidence and consent, and does not persist request evidence. Its frozen scorecard JSON is under `backend/phase2/outputs/phase2f/`. This path applies frozen bins/WoE and logistic-regression coefficients to four repayment/card features, produces raw PD and a separate presentation-only PDO score, and returns no lending decision. Evidence contract is in `backend/phase2/shadow_api/API.md`; reliability history is in `docs/scoring-reliability-sprint.md`. Phase 2B.6 is documented inconclusive and production real-world status unverified. Never claim this is the bank cash-flow model.

### D. Legacy `/assess` and supporting document route

`backend/route/assessment_routes.py` provides `POST /assess`, `GET /assess/financial-health/latest`, and `POST /assess/whatif`. Frontend `services/api.js` still exposes this route in addition to bank-cashflow. Trace which upload/results screens call which assessment path; don’t infer from a shared results card or numerical range. Salary/utility extraction and summary features can be supporting evidence, but the documented bank-first flow must not misrepresent salary/utility documents alone as repayment history.

### E. Phase 4 controlled demo and synthetic fixtures

`backend/phase4/demo_api.py` is separately gated by `ENABLE_PHASE4_DEMO` and has bearer authorization/readiness/scenario endpoints. `backend/route/demo_fixture_routes.py` exposes development synthetic fixtures. Synthetic personas and statement documents live in `data/testing/` and other data subfolders. Fixtures are test evidence only and must remain conspicuously synthetic; no fixture should be promoted to a real customer record or silently selected as an ordinary applicant’s upload.

## 5. Upload, identity, persistence, dashboard, and lender flow

The intended borrower flow is OTP login → consent → bank statement required, salary and utility optional, card statements separately optional → parsing/validation → assessment → saved borrower history/dashboard. The browser asks for `session-id` on authenticated API operations. `services/api.js` uses `API_BASE_URL` from `src/api.js`; uploads use `FormData`. Check session restoration and error handling carefully: earlier user reports included bank-only upload returning to the welcome screen after HTTP 403. A historical report is not proof that this is fixed in the current checkout.

Auth verification looks up a borrower by phone, creates one if absent, determines whether saved assessment rows exist, selects the most recent assessment’s application when possible, and returns a session/application context. The schema includes `users`, `applications`, `consents`, `documents`, `extracted_features`, `risk_scores`, `shap_explanations`, `assessment_details`, `audit_events`, `experimental_assessments`, and `bank_cashflow_assessments`; confirm migrations and current models before relying on completeness. Monthly dashboard scores may be derived from observations; verify their provenance and distinguish a saved assessment score from an observed-month score.

Bank cash-flow endpoints include `/assess/bank-cashflow/preview`, `POST /assess/bank-cashflow`, `/latest`, `/history`, `/{assessment_id}`, `/{assessment_id}/what-if`, and `/{assessment_id}/report.pdf`. Preview should not itself score. What-if is hypothetical and must not overwrite the baseline. Credit-card assessment is under `/assess/credit-card-statements`, with latest/detail/what-if/report endpoints. Borrower history and app navigation are implemented across backend `bank_cashflow_routes.py`, frontend `BorrowerDashboard.jsx`, `ResultsPage.jsx`, and `App.jsx`.

Lender APIs are under `/lender`: application list/detail, case updates, and audit events. Role checks rely on server session and lender phone allowlist configuration. Case workflow updates/audit events are not evidence that lender outreach or a real underwriting workflow exists. Review access controls, data minimization, status meaning, borrower/lender result consistency, and ability to view only authorized applications. Historical user reports include unauthorized lender login and assessment HTTP 403/session reset; verify current behavior using static trace or isolated safe tests.

The dashboard/product surface includes score history, observed months and periods, spending and cash-flow patterns, personalized improvement steps, fraud checks, score explainability/reason codes, what-if simulation, RBI information/guidelines, and “Know More” content. Review that each is data-backed, correctly scoped, honestly labeled, accessible, localized, and not dressed as official RBI approval or deterministic score guarantees. Fraud rules are indicators, not proof of fraud. RBI content requires a current legal/source review before any compliance claim.

## 6. Extraction and identity checks

Bank parsing is intended to use actual uploaded document text/layout, normalize dated transaction rows, classify signed debit/credit, preserve unknown amounts, collect page/period/currency/account evidence, and check opening/running/closing balances. Native coordinate extraction and OCR have distinct accuracy limitations. A parseable PDF is not automatically an eligible statement, and running-balance consistency is not proof that a statement is complete or genuine. Passwords should be ephemeral. Inspect every PDF/OCR path for page truncation, date locale ambiguity, column alignment, debit/credit polarity, duplicate pages/rows, refunds and transfers, multiple accounts, opening/closing checks, and extraction-quality calculation.

Cross-document identity matching is a separate validation objective for bank, salary, and utility sources. Verify normalization, evidence provenance, match thresholds, ambiguous/missing-name behavior, and that name-only overlap is not treated as authoritative proof. Mismatch must not be turned into a score. Do not expose document contents or sensitive identifiers in errors, logs, result JSON, fixtures, or audit events.

Reports in `docs/real-bank-integration-report.md` and `docs/real_document_scoring_failure_report.md` describe prior parser runs, sample PDFs, fixes, protected-artifact checks, and limitations. Read those reports, but independently inspect current code and status: earlier snapshots conflict in age and scope, and prior success counts do not establish the current working tree’s correctness.

## 7. Configuration and privacy

Configuration names found in source include `PRISM_DATABASE_URL`, `PRISM_SQL_ECHO`, `PRISM_CORS_ORIGINS`, `PRISM_ACCOUNT_REFERENCE_SALT`, `PRISM_DOCUMENT_STORAGE_ROOT`, `PRISM_LENDER_PHONES`, `PRISM_ENV`, `PRISM_DEMO_FIXTURES`, `PRISM_CASHFLOW_SNAPSHOT_V1`, `PRISM_V*`/`PRISM_S*` flags, `ENABLE_EXPERIMENTAL_SHADOW_SCORING`, and `ENABLE_PHASE4_DEMO`. This inventory is not proof every variable is used or configured. Inspect references and safe example/template files only. Do not read out or include actual `backend/.env`/frontend local environment values; do not print connection URLs, salts, OTP state, auth tokens, or passwords. Missing configuration must fail explicitly rather than trigger unsafe fallback behavior.

Review file retention/deletion, temp files, document hashes, storage metadata, access controls, audit logging, PII masking, response schemas, errors, telemetry, and demo endpoints. Avoid reading raw files in `data/real world/` or `data/testing/` unless strictly necessary; filenames and folder labels may themselves contain personal data. Do not copy any source document into the handoff or reports.

## 8. Test and check inventory

### Frontend scripts (`prism-frontend/package.json`)

- `npm run build` — Vite production build.
- `npm run lint` — ESLint.
- `npm run test:contracts` — Node contract tests for assessment response behavior.
- `npm run test:browser` — Playwright browser suite; can interact with local services and may invoke persistent backend state, so inspect setup before running.
- `npm run dev` — Vite dev server; this is not a review check.
- `npm run demo:backend` / `npm run demo:frontend` — demo startup scripts; do not start these under the read-only mandate.

### Backend

Tests are spread across `backend/test_*.py`, `backend/phase2/tests/`, `backend/phase3/tests/`, `backend/phase4/tests/`, `backend/document_validation/`, `backend/fraud/`, `backend/scoring/`, and root `tests/`. Relevant coverage includes assessment persistence/history, bank health math, upload formats/OCR, document identity, validation, fraud boundaries, lender workflows, password handling, protected model artifacts, shadow scoring and phase 4 demo. Read `docs/integration-setup.md` and `docs/live-demo-workflow.md` for developer setup; they are operational guides, not authorization to write to the live database.

Do not claim the full suite passes based on one targeted test. Prior reports document missing historical/research artifacts, incompatible test dependencies, and incomplete browser or production validation. Establish which tests actually collect/run in this snapshot, what database they connect to, and what fixtures they mutate before execution. For read-only review, safe static inspection and non-mutating frontend checks are preferred; document all checks that were skipped and why.

## 9. Existing checkout state — preserve it

At handoff, the checkout already had substantial local/uncommitted work: `git status --short` showed **133 entries** (46 modified, 83 untracked, and 4 deleted by the summary command’s simple status grouping). This includes backend, frontend, reports, tests, model/research outputs, fixtures, and data-related paths. Those are pre-existing user changes. Do not reset, clean, checkout, stage, commit, or “tidy” anything. Inspect the exact live status yourself, but do not reproduce potentially sensitive data filenames in a public report. The requested handoff file is an additional documentation file only; it must not be mistaken for implementation changes.

## 10. Review checklist and report shape

1. **Scope and clean boundary:** verify all findings against current tracked and untracked source without changing it; record the local changes as a constraint.
2. **Architecture trace:** draw the actual UI → service → endpoint → validation/parser → feature/model → persistence → dashboard/lender path for each score type.
3. **Hardcoded-outcome audit:** search for fixture/persona/file-name branches, constant score responses, fabricated fallbacks, accidental shared fixture selection, and secret/path literals. Distinguish legitimate versioned math/config from identity-based outputs.
4. **Evidence and identity audit:** verify banks-only and optional-document behavior, password secrecy, name mismatch, multi-account handling, period/reconciliation rules, error status and UI messaging.
5. **Model audit:** identify exactly which flow calls trained/frozen math versus a deterministic index/rule engine; validate provenance, artifact integrity references, score mapping and result labels. Never equate score range with bureau equivalence.
6. **Auth/privacy audit:** follow OTP, lender allowlist, role/session checks, ownership checks, consent, storage, logs, dashboard history and lender visibility. Don’t trigger actual OTPs, uploads or database mutations.
7. **UI/localization audit:** inspect page transitions, refresh/returning-user routing, upload failure behavior, JSON locale parity and missing untranslated text across borrower and lender pages.
8. **Verification:** run only checks proven to be non-mutating and disconnected from protected user data. State exact commands and result; do not treat skipped checks as passes.
9. **Findings only:** return severity-ranked findings with file/line and evidence, followed by coverage and limitations. Do not edit or implement any suggested fix. If no issues are observed, state what was reviewed and what remains unverified; do not call the entire product production-ready.

## 11. Primary references in this repository

- `backend/main.py`, `backend/route/routes.py`, `backend/auth/`, `backend/core/session_store.py`
- `backend/route/bank_cashflow_routes.py`, `backend/features/bank_health_index.py`, `backend/features/thin_file_score.py`
- `backend/features/BANK_FINANCIAL_HEALTH_INDEX.md`, `backend/features/THIN_FILE_CASHFLOW_SNAPSHOT.md`
- `backend/phase2/shadow_api/API.md`, `backend/phase2/outputs/phase2f/`
- `backend/route/experimental_assessment_routes.py`, `backend/route/lender_routes.py`, `backend/phase4/demo_api.py`
- `backend/database/models.py`, `backend/database/migrations/`
- `prism-frontend/src/App.jsx`, `prism-frontend/src/services/api.js`, `prism-frontend/src/services/assessmentWorkflow.js`, `prism-frontend/src/i18n.js`, `prism-frontend/public/locales/{en,hi}/translation.json`
- `docs/integration-setup.md`, `docs/live-demo-workflow.md`, `docs/real-bank-integration-report.md`, `docs/real_document_scoring_failure_report.md`, `docs/scoring-reliability-sprint.md`

**Final boundary:** this document provides project orientation, not a guarantee of correctness. Review must remain read-only and must not create or imply a score, validation result, compliance status, or implementation change that the evidence does not support.
