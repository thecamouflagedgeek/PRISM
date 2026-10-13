# PRISM cash-flow snapshot V1

PRISM_CASHFLOW_SNAPSHOT_V1 is a separate descriptive uploaded-period score. It supports one bank statement without changing the legacy three-month bank index or frozen six-month card model. The frontend selects assessment_profile=auto, using the full history model when eligible and the snapshot otherwise; legacy API callers default to history.

Transactions must pass extraction-quality, date/order, currency, balance-reconciliation, duplicate and adjustment checks. One statement does not require cross-statement account matching. Supplied pages are the scope; unknown page completeness and missing calendar history are reported as coverage, not inferred.

The score is 300 plus 600 times the weighted normalized factor values, rounded to an integer. Base weights: surplus month rate 0.25, expense-to-income 0.25, income regularity 0.20, liquidity 0.15, debt burden 0.15. Transformations use bank_health_index._score. Unknown factors are excluded and remaining weights renormalized. One observed month has unknown income regularity; it is not assigned fabricated stability. Missing debt evidence remains unknown.

The March fixture has eight transactions and one observed month, four measured factors, unknown income regularity, and score 696. August scores 759. Optional salary/utility metadata does not itself increase the score. Fraud flags are computed by the existing transaction fraud engine and reported separately.

Simulation preserves unknown regularity unless the user explicitly supplies a hypothetical volatility. No-op simulation preserves the baseline score. Scenarios do not overwrite the saved assessment.

This is not a trained or validated credit-risk model, probability of default, bureau score, RBI-approved score or lending decision. Limited history remains visible. Invalid bank extraction returns HTTP 422 with correction instructions before results; no fallback score is assigned.

For statements without declared opening/closing balances, snapshot scoring requires at least two transactions per document with finite amounts, explicit directions and independently extracted running balances. Every successive balance change must match the signed transaction amount within 0.05. This verifies observed rows only: the first transaction has no preceding balance check, no opening balance is invented, and complete period reconciliation remains unverified. Any explicit opening/closing mismatch still blocks scoring. Full history V1 gates are unchanged.
