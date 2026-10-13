# PRISM bank-first upload workflow

The normal borrower journey requires one readable bank statement. Upload categories appear in this order: bank (required), salary (optional), utility (optional), credit card (optional). No dossier, six-month history or card statement is required to enable assessment. Optional files require the corresponding processing consent.

After ordinary login and consent, select a bank statement and press Run Assessment. PRISM extracts dated transactions, verifies balances and selects BANK_FINANCIAL_HEALTH_INDEX_V1 when all documented history gates pass; otherwise it calculates the separate PRISM_CASHFLOW_SNAPSHOT_V1 from verified observed patterns. Use Preview extracted transactions to review source pages, totals and reconciliation before assessment. Encrypted PDFs have a password input. The primary score is 300–900. Results show history coverage, measured and unknown factors, explanations, practical next steps, fraud flags, a what-if simulator and borrower rights. Refresh and lender retrieval preserve the same assessment.

A file that cannot supply readable, consistent bank transactions returns an actionable correction on the upload page, preserving the selection. It does not open an insufficient-evidence scorecard or generate an invented score. Salary and utility documents support review; they do not automatically increase the bank score. A partial optional card history does not block the bank assessment. Eligible historical cards can produce a separate frozen research-model assessment.

## Local demonstration

From prism-frontend, run npm run demo:backend and npm run demo:frontend in separate terminals. Open http://127.0.0.1:5173, use the locally generated fictional OTP, record consent, and upload a bank PDF. The corrected files in C:/Users/hp/Downloads/PRISM_Synthetic_Financial_Documents support individual selection. March scores 696 and August scores 759 from their different transaction patterns.

Bulk import & fictional demo is an optional collapsed convenience. The validated 24-file dossier remains available under tests/fixtures/prism_demo_validated and output/PRISM_Validated_Synthetic_Dossier.zip. For the optional historical card assessment, review the explicit 2026-09 exclusive cutoff and card consent. The full bank set scores 775; eligible historical cards retain their independent frozen calculation of 454.635898966963. Neither number is a universal fallback.

The demo selector requires backend PRISM_ENV=demo/development and PRISM_DEMO_FIXTURES=true, and frontend development mode with VITE_PRISM_DEMO_FIXTURES=true. Production rendering omits it. Sessions expire after 60 minutes and backend restarts invalidate them.

## Acceptance

Run browser acceptance on isolated ports to avoid interfering with working services: set PRISM_DEMO_PORT=8001 and PRISM_TEST_UI_PORT=5174, then npm run test:browser. thin-file.spec.js covers bank-only, optional salary/utility, one optional card, invalid-file correction, refresh, explanations, fraud, simulation, PDF and authorized lender retrieval. Evidence is under docs/live-demo/thin-file. See thin-file-bank-first-report.md for the current contract and limitations.
