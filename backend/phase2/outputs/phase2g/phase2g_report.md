# Phase 2G — Experimental Shadow API & Demo Integration

Status: `PHASE_2G_SHADOW_DEMO_READY`

## Result

The evidence-first Phase 2D → 2E → 2F path is exposed through a separate, default-off experimental API and a separately labeled frontend page. The experimental PDO score is presentation-only. This phase does not validate the model or change production model status.

## Golden API result

- Endpoint: `POST /experimental/shadow-assess`; detailed trace: `POST /experimental/shadow-assess/debug`.
- Feature flag: `ENABLE_EXPERIMENTAL_SHADOW_SCORING`, default `false`. Disabled calls return `EXPERIMENTAL_FEATURE_DISABLED`.
- Features: `{"mean_statement_balance": 350.0, "months_with_delinquency": 3.0, "payment_to_statement_ratio": 0.5, "recent_delinquency_level": 3.0}`.
- Raw PD: 0.802589175756118; good:bad odds: 0.245967464061426; experimental PDO presentation score: 282.730565122.
- Reason order: Recent repayment delinquency, Repeated repayment delinquency, Average statement balance. The UI reports coefficient × WoE contribution reasons, never SHAP.
- Golden evidence is the existing synthetic Phase 2E fixture; caller-supplied final feature vectors are rejected.

## Fail-closed and isolation checks

- API negative scenarios: 19; all returned no feature vector, PD, score, or reason codes. Statement-only evidence returns `MISSING_REPAYMENT_STATUS_EVIDENCE`; invalid consent blocks scoring; multiple accounts return `MULTI_ACCOUNT_AGGREGATION_UNRESOLVED`.
- No risk tier or approve/reject output is present. PDF and OCR support are not claimed. Request evidence is not persisted.
- `/assess` remains mounted, its source and production model/bin/manifest hashes are unchanged, and its response to the same invalid request was identical with the flag off and on.
- Protected files checked: 99; unchanged: True.

## Verification

- Phase 2G API tests: 31 passed. Full Phase 2 regression: 258 passed, 0 failed, 0 skipped (baseline 227).
- Frontend production build: passed using the project-local Vite executable. The global `npm` launcher is broken on this host; build warnings are recorded in `frontend_build_results.json`.
- Browser DOM check confirmed the experimental page, warning, and Run Verified Example action. No frontend test framework exists; the golden action was verified through API integration tests, not by a live-browser click.
- Runtime limitation: Python 3.14 on this host lacks pytesseract and scikit-learn required by the pre-existing production app import. Phase 2G endpoint integration was tested via TestClient on the mounted application with import-only stubs; production scoring was never invoked. Use the backend lock/Python 3.12 environment for local server startup.
- Phase 2F scorecard mathematics and artifacts were consumed unchanged. No fit, retraining, calibration, or production scorer call occurred in Phase 2G.

## Status preserved

Phase 2B.6 remains `PHASE_2B6_INCONCLUSIVE`; Phase 2C remains `PHASE_2C_REQUIRES_EVIDENCE_EXTENSION`; Phase 2D remains `PHASE_2D_CONTRACT_READY`; Phase 2E remains `PHASE_2E_EQUIVALENCE_VERIFIED`; Phase 2F remains `PHASE_2F_SHADOW_SCORE_VERIFIED`; production remains `UNVERIFIED_REAL_WORLD`.
