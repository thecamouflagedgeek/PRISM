# Upload and results redesign - 11 October 2026

Implemented a cohesive green/neutral visual system, one two-score summary, readable explanations and progressive disclosure. Results no longer repeat large score blocks or show raw JSON by default. Desktop and 390px mobile screenshots were visually reviewed; horizontal overflow and excess collapsed-panel height were fixed.

Upload now uses a three-step guide, whole-folder selection, a two-column category grid, explicit per-category counts, readable file removal, a compact coverage summary and focused historical-window/consent controls. Fictional-demo selection is under an expandable section. Existing partial-synthetic protection remains; repeated manual selection deduplicates identical file name/size/lastModified entries. Normal consents, monthly validation and actual multipart uploads remain in force.

Results sections: **Your next steps**, **Why this score**, **Features**, **Fraud flags**, **What-if**, **Borrower rights**. The plan reflects observed delinquency, payment-to-statement ratio and cash flow; no guaranteed score uplift or loan eligibility is claimed. All four frozen signed logit contributions render with correct direction; adverse reason codes retain their actual source and numeric contribution. Technical provenance remains available under details. Bank metrics, monthly cash flow, five index factors and the bank simulator are under Explore bank cash flow. Credit and bank baseline simulations, reset and actual saved PDF exports remain available.

## Fraud integration

The current bank workflow now invokes the existing `fraud.integration.assess_fraud` / P1-v1 engine on the parsed ledger. Actual flags, weighted heuristic status and coverage persist in the bank assessment JSON and survive authenticated retrieval. An independent engine invocation and saved GET response are asserted in backend regression. Fraud signals are separate from both scores; no frozen model changes. Identity and loan-stacking coverage explicitly says not assessed because verified identity/application history was not supplied. Saved older results without this metadata say unavailable; a new upload generates it. Parser result version advances to explicit-table-v4-fraud so an older result is not reused as if fraud review had run.

For the 48-row fictional dossier, the engine returned one repeated-identical-transactions review signal and LOW heuristic status. Recurring payments can trigger this heuristic; this is not proof of fraud. There is no fake all-clear badge, fraud probability or issuer authenticity claim.

## RBI content

Official sources checked 11 October 2026:

- [Free Annual Credit Report](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=10590&Mode=0): one free full report per calendar year from each CIC holding a person's history, on authenticated request.
- [Digital Lending Directions, 2025](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12848&Mode=0): KFS/APR disclosure, cooling-off and regulated lender grievance provisions.
- [RBI Complaint Management System](https://cms.rbi.org.in/): linked for complaint-process review.

RBI protections are not invented score-based eligibility bands. The screen separates observed-history next steps from official protections, links the source directions, and states that PRISM's experimental score is not RBI-approved or a bureau-score equivalent. No regulatory-compliance certification is asserted.

## Verification

- Complete redesigned browser journey: **1 passed (32.5s)**. Folder upload from the actual Downloads directory, missing-month prevention, 24 PDFs, independent credit/PD/index calculations, reason-code display, engine coverage, linked RBI tab, mobile overflow check, refresh, credit/bank simulations, both PDFs, baseline preservation, idempotency and exact lender retrieval. Application **144**. Evidence: `docs/live-demo/ui-refresh/browser-evidence.json`; screenshots `both-scorecards.png`, `upload.png`, `mobile.png`, `explainability.png`, `fraud.png`, `rights.png`. Log `docs/ui-refresh-browser-test.txt`.
- Backend bank/fixture/fraud regressions: **21 passed**; `docs/ui-refresh-backend-tests.txt`. Datetime/Pydantic deprecation warnings remain.
- Frontend contracts/workflow: **10 passed**; `docs/ui-refresh-frontend-tests.txt`.
- Redesigned incomplete-evidence journey: **1 passed (18.9s)**; `docs/ui-refresh-negative-browser-test.txt`. Invalid original PDFs remain correctly unscored and can return to upload.
- Production build: passed,75 modules; `docs/ui-refresh-build.txt`. Browser-list freshness warning remains nonfatal.
- Frozen artifact SHA256 unchanged: `DE1C1106759ED00F53F208C5185D63B3D8D22DB477D3A3EFD36132B5830E4CA6`. Calculated credit454.635898966963 / rawPD0.2727810906249319 / bank775 unchanged.

Test services use isolated ports8001/5174 and terminate after acceptance; the user's backend8000/frontend5173 were not restarted. Historical broad-suite failures and experimental model limits remain as documented in `validated-dossier-recovery-report.md`.

Changed sources: ResultsPage.jsx, UploadPage.jsx, AssessmentUI.css, BankCashflowAssessment.jsx, bank_cashflow_routes.py, validated-dossier persistence regression and browser UI assertions. No model weights, score formula, PD calibration or validation gate was changed.
