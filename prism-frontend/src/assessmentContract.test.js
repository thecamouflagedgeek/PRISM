import test from "node:test";
import assert from "node:assert/strict";
import { isValidFrozenAssessment, normalizeAssessmentResponse } from "./assessmentContract.js";

test("insufficient evidence never becomes a score or tier", () => {
  const view = normalizeAssessmentResponse({ status: "INSUFFICIENT_EXPERIMENTAL_EVIDENCE", features: null, scorecard: null });
  assert.equal(view.scoreable, false);
  assert.equal(view.score, null);
  assert.equal(view.probability_of_default, null);
  assert.equal(view.risk_tier, null);
  assert.equal(view.feature_coverage, 0);
});

test("only complete frozen responses with valid PD and score pass", () => {
  const valid = {
    status: "EXPERIMENTAL_SHADOW_SCORE", decision_use: "NOT_FOR_CREDIT_DECISION", artifact_sha256: "frozen-v1",
    features: { recent_delinquency_level: 0, months_with_delinquency: 0, payment_to_statement_ratio: 0.8, mean_statement_balance: 350 },
    scorecard: { raw_pd: 0.2, experimental_shadow_score: 510 },
  };
  assert.equal(isValidFrozenAssessment(valid), true);
  assert.equal(normalizeAssessmentResponse(valid).feature_coverage, 1);
  assert.equal(normalizeAssessmentResponse({ ...valid, scorecard: { ...valid.scorecard, raw_pd: 1 } }).scoreable, false);
  assert.equal(normalizeAssessmentResponse({ ...valid, features: { recent_delinquency_level: 0 } }).score, null);
});

test("zero-valued features count as present", () => {
  const view = normalizeAssessmentResponse({
    status: "EXPERIMENTAL_SHADOW_SCORE", decision_use: "NOT_FOR_CREDIT_DECISION",
    features: { recent_delinquency_level: 0, months_with_delinquency: 0, payment_to_statement_ratio: 0, mean_statement_balance: 0 },
    scorecard: { raw_pd: 0.5, experimental_shadow_score: 383.9 },
  });
  assert.equal(view.scoreable, true);
  assert.equal(view.feature_values.recent_delinquency_level, 0);
  assert.equal(view.feature_coverage, 1);
});
