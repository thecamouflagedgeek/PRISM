# Phase 2F — Isolated Shadow Scorecard Execution

Status: `PHASE_2F_SHADOW_SCORE_VERIFIED`

This is an engineering and mathematical integration result for a synthetic controlled fixture. It does not establish external, current-market, Indian-market, or real-world lending validity. Phase 2B.6 remains `PHASE_2B6_INCONCLUSIVE`; production remains `UNVERIFIED_REAL_WORLD`.

## Verification

- Tests: 21 Phase 2F-specific and 227 total Phase 2 tests passed (baseline 206).
- Training, fitting, and calibration calls in Phase 2F: none.
- The original Phase 2B.6 runner did not persist its estimator; Phase 2F consumed the existing Phase 2B.6-R recovery artifact, created by the original final-fit procedure.
- Protected hashes unchanged: True across 69 files.

## Frozen model and golden trace

- Features, in order: recent_delinquency_level, months_with_delinquency, payment_to_statement_ratio, mean_statement_balance.
- Golden vector: `{"mean_statement_balance": "350", "months_with_delinquency": "3", "payment_to_statement_ratio": "0.5", "recent_delinquency_level": "3"}`.
- Bin IDs: `{"mean_statement_balance": 0, "months_with_delinquency": 1, "payment_to_statement_ratio": 3, "recent_delinquency_level": 1}`.
- WoE: `{"mean_statement_balance": -0.18768027859219305, "months_with_delinquency": -1.3538771425779765, "payment_to_statement_ratio": 0.40889681863656524, "recent_delinquency_level": -2.0895984742813423}`.
- Contributions: `{"mean_statement_balance": 0.5621423708655136, "months_with_delinquency": 0.8733442754752132, "payment_to_statement_ratio": -0.28582810302780487, "recent_delinquency_level": 1.501338351969542}`.
- Logit: 1.40255601170979; PD: 0.802589175756118; good:bad odds: 0.245967464061426.
- Phase 2F shadow PDO score: 282.730565122 (600 at 20:1; 650 at 40:1; 550 at 10:1). This scale was explicitly added for Phase 2F and was not used by Phase 2B.6.
- Reason codes, ranked by positive default-logit contribution: Recent repayment delinquency, Repeated repayment delinquency, Average statement balance. The machine trace links each to source record IDs, feature derivation, bin, WoE, coefficient, and contribution.
- Independent reconstruction max absolute error: 0.
- Boundary probes passed: 8; Phase 2E negative cases fail closed: 18.
- Reference test predictions reproduced from frozen artifacts: 25 rows; max absolute PD error 1.39e-16.
- Protected hashes unchanged: True across 69 files.
- Training/fitting/calibration calls in Phase 2F: none.

The detailed trace is in `golden_shadow_trace.json`; the full frozen specification is in `frozen_shadow_scorecard.json`. No production route or frontend was connected.
