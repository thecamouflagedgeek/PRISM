# PRISM integrated backend setup

The backend reads its database URL from `PRISM_DATABASE_URL`. Apply the SQL migrations in `backend/database/migrations/` in numeric order before using OTP signup, consent, assessment persistence, or lender retrieval.

Set `PRISM_LENDER_PHONES` to a comma-separated list of authorized lender phone numbers. Lender endpoints require a live lender session and reject borrower sessions.

Set `PRISM_CORS_ORIGINS` to additional frontend origins as a comma-separated list. Local Vite origins on ports 5173 and 5174 are allowed by default. Set `VITE_API_URL` for a non-local backend; development defaults to `http://127.0.0.1:8000`.

There is no SMS provider. Local OTP console delivery is disabled by default and is permitted only when both `PRISM_ENV=development` and `PRISM_OTP_LOGGING=true` are set. In that mode the backend logs a clearly labeled development-only OTP without the phone number; the API and UI state that no SMS was sent. Other environments fail signup with HTTP 503 rather than claiming delivery. Never enable this logging in production or shared environments.

Loan-like repayment review, repayment-tenure comparisons, and the unavailable portfolio-sentiment status are described in [`advanced-feature-status.md`](advanced-feature-status.md). The loan review runs as part of new bank-cashflow assessments; the tenure tool requires all proposed terms and affordability inputs explicitly; sentiment produces no output until approved data and validation exist.

## IIT Bombay assessment demonstration

Run the backend from `backend/` with Python 3.12 and the existing `backend/.env` configured. The environment file must contain `PRISM_DATABASE_URL`; do not commit or print its value. Enable the frozen research endpoint explicitly for the synthetic walkthrough:

```powershell
$env:ENABLE_EXPERIMENTAL_SHADOW_SCORING = "true"
py -3.12 -m uvicorn main:app --reload
```

In a second terminal:

```powershell
cd prism-frontend
npm run dev
```

Open `http://localhost:5173/experimental-credit-evidence-lab` and choose **Run Verified Example**. This loads the repository's synthetic six-month fixture and passes it through Phase 2E normalization, Phase 2D validation, and the frozen Phase 2F WoE–Logistic Regression model. The calculation trace exposes the four values, frozen bins, WoE values, coefficients, signed logit contributions, PD, and score. The What-if panel calls `POST /experimental/shadow-simulate` and never writes over its baseline. **Download assessment PDF** generates a PDF containing actual synthetic assessment outputs and, when run, a separately identified hypothetical scenario.

Main borrower PDF uploads continue through `POST /assess` for bank, salary, and utility supporting evidence. Credit-card statements use the separate authenticated `POST /assess/credit-card-statements` route. It accepts up to 12 PDF/JPG/JPEG/PNG documents, requires recorded DPDPA consent plus explicit card-processing consent, saves documents under the borrower's existing application, and persists a versioned record in `prism.experimental_assessments`. A bank statement alone creates an insufficient-evidence assessment with no PD or score. Existing `/assess` behavior and `/phase4/demo` remain separate.

The card extractor reuses PRISM PDF text and OCR services and recognizes only controlled, explicitly labeled fields. It does not claim broad compatibility with arbitrary issuer layouts. Six complete consecutive months, a consistent card identity, INR allowlist validation, explicit repayment status and severity, clear provenance, and Phase 2E eligibility are required before the frozen Phase 2F score runs. Missing or ambiguous history remains unscored. The lender view reads the same experimental assessment row; borrower refresh and report routes are application scoped. The Phase 2G what-if calculation remains behind `ENABLE_EXPERIMENTAL_SHADOW_SCORING` and is non-persistent.

### Added route contract

`POST /experimental/shadow-simulate` accepts exactly this shape (no unknown keys):

```json
{
  "baseline": {
    "recent_delinquency_level": 3,
    "months_with_delinquency": 3,
    "payment_to_statement_ratio": 0.5,
    "mean_statement_balance": 350
  },
  "scenario": {
    "recent_delinquency_level": 0,
    "months_with_delinquency": 0,
    "payment_to_statement_ratio": 0.8,
    "mean_statement_balance": 350
  }
}
```

Both vectors use the same immutable Phase 2F JSON and right-closed bin assignment as the frozen scorecard. Values outside the existing frozen bins are rejected; no currency is assumed or converted. The response contains complete baseline and scenario contributions, PD, score and delta, and marks `persisted: false` and `decision_use: NOT_FOR_CREDIT_DECISION`.

### Verification status

Verification status for the latest synthetic integration run is recorded in [`final-real-document-integration.md`](final-real-document-integration.md). The focused PostgreSQL-backed integration uses synthetic borrower/application rows inside a rollback-only transaction. The borrower UI is wired to the persistence route, and the frontend contract checks/build pass. A live browser login/upload still requires a human to complete the borrower authentication step; it has not been claimed as successful. The full backend suite remains blocked at Phase 2C collection by the missing historical `backend/phase2/feature_compatibility/protected_hashes_before.json`; tests excluding that module were run separately.
