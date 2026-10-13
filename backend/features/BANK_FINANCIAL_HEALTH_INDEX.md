# Experimental Bank Financial Health Index V1

## Status and separation

`BANK_CASHFLOW_EXPERIMENTAL` is a descriptive fixed-weight index, not a supervised credit-risk model. No linked bank-transaction and subsequent repayment-outcome dataset is available in this repository. The unrelated UCI Taiwan credit-card default data is not a validation sample for bank transactions. No PD, lending tier, bureau score, or decision is produced. The frozen `CREDIT_ACCOUNT_EXPERIMENTAL` Phase 2F route and its artifacts remain separate.

## Index mapping

For available factors, normalize each factor to `[0,1]`, normalize their fixed weights over available factors, and compute:

`score = round(300 + 600 × Σ(normalized_weight × factor_value))`

| Factor | Fixed weight | Transformation |
|---|---:|---|
| Surplus-month rate | 0.25 | Observed calendar months where credits exceed debits / observed months |
| Expense-to-income health | 0.25 | `clip(1 − total debits / total credits, 0, 1)` |
| Income regularity | 0.20 | `1 / (1 + sample CV of monthly credits)` |
| Liquidity buffer | 0.15 | `clip(mean observed closing balance / (3 × mean monthly debits), 0, 1)` |
| Explicit debt-payment burden | 0.15 | `clip(1 − identified recurring loan/EMI debit per month / mean monthly credits, 0, 1)` |

Missing factors are omitted and remaining weights renormalized. A missing debt match is unknown, not zero debt. The 300–900 mapping is an internal presentation scale only. It is not equivalent to CIBIL or another bureau scale. Factor points sum to the displayed score minus 300 after rounding reconciliation.

## Evidence gates

A score requires all of the following: at least three consecutive observed transaction months; statement-period evidence covering each represented calendar month in full; verified, consistent account reference and currency; a configured `PRISM_ACCOUNT_REFERENCE_SALT` for HMAC-based account linking; extraction quality of at least 0.80; transaction ordering; declared statement page sequence; no ambiguous exact duplicates or unresolved internal-transfer/refund/reversal rows; and opening/closing plus transaction running-balance reconciliation. If any required evidence is absent or fails, the system persists the findings and monthly observations with a null score and null PD.

Account references are HMAC-SHA256 tokenized with `PRISM_ACCOUNT_REFERENCE_SALT`; raw account values and transaction narration are not included in the assessment response. The secret must remain outside source control and be stable across assessment requests where accounts are to be linked. No raw tokens are persisted in the assessment record.

## What-if scenarios

Scenarios are hypothetical only. They call the same component transformations and weighting/mapping, do not overwrite persisted results, and are available only for a scored baseline. The generated three-month income sequence uses the provided mean and coefficient of variation; expenses are held constant across those months. Scenarios with negative values or debt obligations above expenses are rejected.

## Research and governance limits

The index has no default target, fitted coefficients, calibration, out-of-sample predictive validation, or subgroup performance evaluation. Tests cover deterministic arithmetic, monotonic behavior, missing evidence, and route persistence only. Real-world bank-layout compatibility is not established from two redacted sample PDFs. Use requires borrower consent, lender review, human oversight, and separate review of the applicable RBI Digital Lending Directions. This prototype does not assert RBI certification, CIBIL equivalence, or production lending readiness.
