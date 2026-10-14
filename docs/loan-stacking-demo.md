# Synthetic loan-obligation overlap demo

This development-only demo uses fixed fictional records and does not persist
them. It does not call borrower assessment, lender, or score APIs.

## Run

In PowerShell from `backend`, run
`$env:PRISM_ENV="development"; $env:PRISM_DEMO_FIXTURES="true"; $env:PRISM_OTP_LOGGING="true"; python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000`.
In a second terminal from `prism-frontend`, run
`$env:VITE_PRISM_DEMO_FIXTURES="true"; npm run demo:frontend`. Open
`http://127.0.0.1:5173/loan-stacking-demo`.

The API is `GET /demo/loan-stacking` (scenario list) and
`GET /demo/loan-stacking/{scenario_id}` (one fixed scenario). Both return 404
unless the backend demo flags are enabled. The endpoint accepts no transactions
and writes no database records.

## Method and limits

A candidate recurring payment stream needs debit transactions with a debt
repayment keyword and the same fictional masked lender/mandate reference in at
least two distinct months.
Repeated exact rows are deduplicated; reversals and explicit transfers/card
payments are excluded. Multiple candidate references in the same month produce
a possible-overlap signal. Keyword-only rows without distinct references yield
`INSUFFICIENT_EVIDENCE`. The API always reports
`confirmed_loan_stacking: false`.

When a scenario includes synthetic monthly net income, the demo reports the
observed payment-to-income ratio for the applicable months. It applies no
credit-score penalty, policy threshold, or lending decision. The references
and recurring payment patterns are demonstrations of grouping logic, not proof
that real accounts or loans exist.

The backend flag also permits local OTP console delivery. Use synthetic test
identities only: the backend prints a `DEVELOPMENT-ONLY OTP` line without the
phone number. No SMS is sent. The browser shows the local-only delivery notice;
read the OTP from the backend terminal and enter it in the UI. OTP logging is
disabled unless both backend flags are explicitly set, and the backend rejects
signup in production, test, and unconfigured environments. First-login
verification requires migration 005's tables; this demo setup applies no
migrations automatically.

Choose these fixed scenarios from the page:

- **Two recurring payment streams overlap**: two masked references recur in
  three months; the result is possible overlap, not confirmation.
- **One loan with repeated instalments**: one reference recurs and remains one
  candidate stream, not stacking.
- **Duplicate, reversal, transfer, and card-payment controls**: duplicate rows
  are deduplicated and the reversal, transfer, and card payment are excluded.
- **Loan keywords without distinct references**: returns insufficient evidence.

## Actual borrower assessment

New `POST /assess/bank-cashflow` assessments also run the separate
`OBSERVED_REPAYMENT_STREAM_REVIEW_V1` review. It is persisted in the existing
assessment JSON, returned through assessment/history APIs, and shown on
borrower results and lender case detail. No demo flag is required for that
assessment path. The result is a manual-review signal, never a confirmed loan
stacking determination or score input. See
[`advanced-feature-status.md`](advanced-feature-status.md) for methodology and
limits.
