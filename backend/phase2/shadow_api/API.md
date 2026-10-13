# PRISM Experimental Shadow API

This opt-in API demonstrates the non-production Phase 2D → 2E → 2F experimental credit-evidence path. It is independent of `/assess` and never returns a lending decision.

The scorer loads `backend/phase2/outputs/phase2f/frozen_shadow_scorecard.json` by path. That experimental specification records provenance to the recovered Phase 2B.6 artifact and is not copied into `backend/scoring/artifacts/`.

## Endpoint and flag

- `POST /experimental/shadow-assess` accepts evidence, consent, and a prediction cutoff.
- `POST /experimental/shadow-assess/debug` accepts the same request and adds the detailed bin/WoE/contribution trace.
- `GET /experimental/shadow-golden-request` returns the existing synthetic Phase 2E golden fixture as an API request.
- `ENABLE_EXPERIMENTAL_SHADOW_SCORING` defaults to `false`. While disabled, experimental routes return HTTP 404 with `EXPERIMENTAL_FEATURE_DISABLED` before parsing/scoring.

## Accepted inputs

Send structured JSON containing a pseudonymous `borrower_reference`, `prediction_cutoff_month`, up to twelve `statements`, optional explicit `repayment_history`, and a `consent` object. An eligible result requires six complete account-linked months and `CREDIT_CARD_STATEMENTS` consent; `BUREAU_REPAYMENT_HISTORY` scope is additionally required when bureau/lender repayment records are supplied. Each record must provide the Phase 2E source metadata and matching account/provider/product/month information. Statements may carry explicit repayment status; status is never inferred from payments.

No caller-provided final feature vector is accepted. The API does not accept files, arbitrary PDF, OCR, controlled text uploads, or real bureau API calls. Evidence is handled in the request and not persisted by this experimental API.

The exact synthetic example is [`golden_api_request.json`](../outputs/phase2g/golden_api_request.json); the deterministic response is [`golden_api_response.json`](../outputs/phase2g/golden_api_response.json).

## Response and fail-closed behavior

Successful responses use `EXPERIMENTAL_SHADOW_SCORE` and `NOT_FOR_CREDIT_DECISION`. `scorecard.raw_pd` is the recovered raw logistic-regression PD. `scorecard.experimental_shadow_score` is a separate Phase 2F presentation scale (Base Score 600, PDO 50, Base Odds 20:1); it was not part of the Phase 2B.6 empirical experiment. No risk tier, approve/reject decision, or calibration is returned.

Evidence that is incomplete, invalid, unsupported, lacks valid consent, has unresolved account linkage, or contains multiple accounts returns HTTP 200 with `INSUFFICIENT_EXPERIMENTAL_EVIDENCE`, `eligibility.eligible: false`, a machine-readable `blocking_reasons` list, `features: null`, `scorecard: null`, and no reason codes. Malformed JSON/schema requests receive FastAPI validation errors and never invoke scoring.

The normal endpoint returns the evidence summary, four behavioral features, raw PD, odds, PDO presentation score, reason codes, trace ID, model status, and limitations. The explicit `/debug` endpoint returns the detailed reconstructable trace. The trace is request-scoped; it is not stored.

## Golden output

The frozen example produces recent delinquency `3`, delinquent months `3`, payment-to-statement ratio `0.5`, and mean statement balance `350`; raw PD approximately `0.802589175756118`; good:bad odds approximately `0.245967464061426`; and experimental presentation score approximately `282.730565122`. Reasons are ranked by adverse coefficient × WoE contribution. This does not establish external, current-market, Indian-market, or real-world lending validity. Phase 2B.6 remains `PHASE_2B6_INCONCLUSIVE` and production remains `UNVERIFIED_REAL_WORLD`.
