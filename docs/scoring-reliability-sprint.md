# PRISM scoring reliability sprint — validation report

> Historical snapshot: this report predates the real-document integration. Its statements that extraction and persistence were not implemented are superseded by [`final-real-document-integration.md`](final-real-document-integration.md), which records the newer implementation and test results. The frozen-model verification and artifact identity recorded below remain applicable.

**Result: scoring mathematics independently verified; full real-document and borrower-to-lender acceptance criteria remain unmet.** The frozen research model remains `PHASE_2B6_INCONCLUSIVE` and experimental only.

## Frozen inference identity

- Frozen Phase 2F artifact: `backend/phase2/outputs/phase2f/frozen_shadow_scorecard.json`
- Frozen recovered Phase 2B.6 specification: `backend/phase2/outputs/phase2b6_recovery/recovered_final_scorecard.json`
- Source data: 30,000-row UCI default-card dataset; SHA-256 `88BD2BD25327B52AF2148B7437740ACA427AAF8F0E52AD782EE8BBAE44B509BD`.
- Phase 2F artifact SHA-256 before and after the inference validation: `DE1C1106759ED00F53F208C5185D63B3D8D22DB477D3A3EFD36132B5830E4CA6` (unchanged).
- Recovered Phase 2B.6 artifact SHA-256: `A8F64F289D76DBA2B766F85739CEA9B59AC0D8285C7F0531B387ADBBA1EEF6EC`.
- Feature order: `recent_delinquency_level`, `months_with_delinquency`, `payment_to_statement_ratio`, `mean_statement_balance`.
- Inference applies the artifact's frozen right-closed bins and WoE maps, then `logit = -1.248440883572674 + Σ(coefficient × WoE)`, `PD = sigmoid(logit)`. Coefficients in feature order: `-0.718481742041798`, `-0.6450690745928691`, `-0.6990225651079325`, `-2.995212789975563`.
- The shadow score uses `600 + (50 / ln(2)) × ln(((1 − PD) / PD) / 20)`. It is not clipped. Invalid/nonfinite features fail closed; score conversion rejects PD values outside `(0, 1)`. The production bank/salary/utility scorer is not imported by the experimental inference route.

## Independent arithmetic and score scale

For the six-month synthetic fixture, the frozen model produces logit `1.40255601170979`, PD `0.8025891757561177`, good:bad odds `0.24596746406142594:1`, and score `282.73056512249605`. An independent reconstruction using the formula above matched the API result; the corresponding displayed value **282.73 is mathematically correct**. No PD, coefficient, bin, or artifact was changed.

The held-out distribution was independently reconstructed for all 6,000 rows in the deterministic 20% UCI test split. Every PD matched the saved frozen prediction to maximum absolute error `0.0`.

| Statistic | Score |
|---|---:|
| Minimum | 244.6919 |
| Maximum | 568.3689 |
| Mean | 487.6591 |
| Median | 508.9730 |
| 5th percentile | 304.5748 |
| 25th percentile | 470.8532 |
| 75th percentile | 539.5047 |
| 95th percentile | 543.2696 |
| Below 300 | 4.4333% |
| 300–900 inclusive | 95.5667% |
| Above 900 | 0% |

The 300–900 range is illustrative, not a guarantee of the frozen formula. The results screen now labels off-reference scores and explains that its edge marker is only the reference-scale boundary; the uncapped number remains the research score. Its circular progress ring is suppressed for off-reference values.

## Synthetic profile checks

Twenty labeled, model-scored feature vectors cover zero through severe delinquency, isolated and repeated delinquency, low/high payment ratios, low/high balances, mixed patterns, and exact frozen bin boundaries. The table records raw inputs, bin IDs, WoE, PD, score, and reason codes in [phase2f_synthetic_profile_validation.csv](../backend/phase2/outputs/phase2g/phase2f_synthetic_profile_validation.csv). API scores and an independent calculation agreed within `1e-10` for score and `1e-12` for PD. Profile interpretations are explicitly descriptive, not decisions.

Automated checks also cover fixed feature names/order, deterministic same-input output, score formula anchors, invalid PD boundaries, frozen bin assignments, and artifact immutability. The synthetic profiles test model behavior across bins; they do not represent real applicants or validate the model for current-market decisions.

## Document extraction, storage, and persistence

Real multi-month credit-card statement extraction is still not connected to the four frozen features. The regular `/assess` upload flow recognizes a credit-card document but marks it unscoreable; the Phase 2E parser accepts structured evidence, not arbitrary statement PDFs or OCR text. The current rule correctly refuses to treat absent delinquency records as on-time payments. No representative card statements were provided, so PDF and scanned-image feature accuracy against ground truth was not established.

The experimental scoring route is not wired to PostgreSQL assessment persistence or application-scoped borrower ownership. The configured local database is reachable as `prism_db`, and read-only inspection confirmed the `prism.risk_scores` and `prism.assessment_details` tables exist. No records were written or modified. As a result, refresh retrieval, borrower/lender same-record consistency, persisted what-if isolation, and PDF-to-persisted-result consistency were not demonstrated.

## Verification record

- Targeted Phase 2F/2G plus reliability checks: **78 passed** (including 20 synthetic profile cases).
- Frontend contract tests: **3 passed**.
- Frontend production build: **passed**.
- Full backend suite: **not green**. Initial collection fails because `backend/phase2/feature_compatibility/protected_hashes_before.json` is absent. Excluding that module, the suite reports **340 passed, 53 failed, 3 errors**; failures/errors include absent historical Berka inputs and pre-generated Phase 2/3/4 outputs. The Phase 4 borrower-to-lender test also cannot start because `backend/phase4/outputs/demo_scenarios.json` is absent.
- PostgreSQL check: connection and table discovery only; no writes.
- No real-document browser upload or end-to-end persistence check was performed. The synthetic lab is a separate non-production workflow.

## Files changed for this sprint

- `prism-frontend/src/pages/ResultsPage.jsx` — explicit out-of-reference score presentation.
- `backend/phase2/tests/test_phase2f_reliability_sprint.py` — 20 profiles and mathematical regression checks.
- `backend/phase2/real_evidence/validate_frozen_inference.py` — deterministic held-out and synthetic-profile audit generator.
- Generated `backend/phase2/outputs/phase2g/phase2f_test_score_distribution.json`, `phase2f_test_score_distribution.csv`, and `phase2f_synthetic_profile_validation.csv`.

**Acceptance status:** the frozen score calculation and display behavior are verified. Real statement extraction, assessment persistence, and complete borrower-to-lender browser validation remain blocked by missing extraction implementation, representative documents, and connected persistence workflow. No model retraining, recalibration, artifact edit, or score manipulation occurred.
