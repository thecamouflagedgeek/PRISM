# Advanced feature status

## Loan-like repayment stream review

Every new `POST /assess/bank-cashflow` assessment now runs
`OBSERVED_REPAYMENT_STREAM_REVIEW_V1`. The result is stored inside the existing
`bank_cashflow_assessments.result_json` JSONB payload, returned by the detail
and latest endpoints, included in borrower history and PDF output, and shown in
the borrower results and lender case detail views. The rule version participates
in assessment idempotency so an older saved assessment is not silently mutated.
No new table or column is required.

The review considers loan/EMI-like debits, deduplicates exact rows, excludes
transfers, reversals/refunds and card payments, and groups recurrence by an
explicitly labeled loan/mandate reference when present or a normalized
narration signature otherwise. It reports source document/page/line locations,
observed and missing months, amounts, exclusions, and limitations. The 20%
monthly amount-variation rule and five-day payment-date span are uncalibrated
review aids only. They are not confidence scores. Low extraction quality,
missing months, or insufficient recurrence produces an explicit
insufficient-evidence status. Candidate streams are not verified obligations,
and overlapping streams are not confirmed loan stacking. The signal does not
enter the credit score or lending decision.

Narration data may omit or distort account identifiers, and two obligations
with the same creditor text can merge while one obligation with changing
narration can split. Lenders must verify against source statements or borrower
disclosure. No production-grade multi-loan classifier is claimed.

## Repayment-tenure comparison

The borrower results page and lender case detail include **Compare repayment
tenures**. The UI requires principal, nominal annual interest rate, fees,
monthly net income, expenses excluding debt, existing obligations, a
user-supplied debt-to-income limit, and the tenures being compared. It does not
impute terms from an assessment. `POST /assess/bank-cashflow/tenure-comparison`
is borrower-session and application scoped; lenders use
`POST /lender/applications/{application_id}/tenure-comparison` with a lender
session. Both require a saved bank assessment, return the same deterministic
comparison, and persist nothing.

The calculation uses a fixed nominal annual rate divided by 12 and monthly
reducing-balance amortization with end-of-month payments. Fees are shown
separately and included in total cost. An option is eligible only if it meets
the explicitly supplied debt-to-income limit and leaves a nonnegative monthly
residual. The recommended option is the lowest total-cost eligible term. All
inputs are user/lender supplied and unverified; outputs are hypothetical
planning information, not PRISM affordability policy, an offer, a credit score,
or a lending recommendation. Independent reference calculations are tested in
`backend/test_repayment_tenure.py`.

## Portfolio sentiment

The lender portfolio panel and authenticated `GET /lender/portfolio/sentiment`
show `UNAVAILABLE`; no sentiment result or portfolio aggregate is produced.
The repository CSV has 20 rows with binary labels, and no source, license,
label definition, collection method, or permitted-use record. The retired
exploratory script fit TF-IDF before splitting and combined text predictions
with a hand-written rule. It also printed individual loan descriptions and
income values; it has been replaced by a metadata-only audit that never prints
examples or trains a model. Sentiment cannot be described as credit risk or
default probability. Do not enable inference until an approved corpus and
leakage-controlled independent evaluation exist.

## Local schema observation

Read-only PostgreSQL catalog inspection on 2026-10-13 found
`audit_events`, `experimental_assessments`, and `bank_cashflow_assessments` in
schema `prism`, with INTEGER core foreign keys and columns, nullability,
foreign keys, named constraints, and indexes matching the ORM/migration
definitions inspected. Legacy `audit_logs` remained present. No migration
tracking table was found, so table presence cannot identify which SQL file was
used. This pass did not apply migration `005` or write application data.
