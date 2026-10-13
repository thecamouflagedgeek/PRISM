PRISM SYNTHETIC DOCUMENT QA DOSSIER

24 PDFs: six months each of bank statements, credit-card statements, salary slips, and electricity bills. One entirely fictional borrower, March-August 2026.

All PDFs are synthetic and prominently marked. Do not use for lending, identity verification, or represent as genuine issued documents.

Ground truth: ground_truth.json and bank_transactions.csv.

Bank account references and amounts are linked across bank statements, salary slips, and utility bills.

Credit card monthly statement fields are intentionally explicit for extraction QA. The card payments are recorded in the bank statements, but the statement payment allocation is synthetic and simplified; this is not a complete issuer ledger.

IMPORTANT: These documents do not prove your existing PRISM validation gates will accept them. Check account-reference salt, statement linkage, reconciliation, and exact Phase 2F feature semantics. If a document fails, fix the parser or record the missing evidence; do not weaken controls or invent scores.
