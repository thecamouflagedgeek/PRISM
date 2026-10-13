export const FROZEN_FEATURES = [
  "recent_delinquency_level",
  "months_with_delinquency",
  "payment_to_statement_ratio",
  "mean_statement_balance",
];

const finite = (value) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));

/** Normalize supported frozen-model API responses without inventing missing values. */
export function normalizeAssessmentResponse(source = {}) {
  const trace = source.feature_trace ?? source.trace?.feature_trace ?? null;
  const isFrozenResponse = source.status === "EXPERIMENTAL_SHADOW_SCORE" &&
    source.decision_use === "NOT_FOR_CREDIT_DECISION" &&
    source.scorecard && typeof source.scorecard === "object";
  const featureValues = isFrozenResponse && source.features && typeof source.features === "object"
    ? Object.fromEntries(FROZEN_FEATURES.map((key) => [key, finite(source.features[key]) ? Number(source.features[key]) : null]))
    : Object.fromEntries(FROZEN_FEATURES.map((key) => [key, null]));
  const observedFeatureCount = Object.values(featureValues).filter((value) => value !== null).length;
  const rawScore = isFrozenResponse ? source.scorecard.experimental_shadow_score : null;
  const rawPd = isFrozenResponse ? source.scorecard.raw_pd : null;
  const scoreable = isFrozenResponse && finite(rawScore) && finite(rawPd) &&
    Number(rawPd) > 0 && Number(rawPd) < 1 && observedFeatureCount === FROZEN_FEATURES.length;

  return {
    application_id: source.application_id ?? null,
    assessment_id: source.assessment_id ?? source.trace_id ?? null,
    assessment_status: scoreable ? "SCORED" : (source.status ?? "INSUFFICIENT_EVIDENCE"),
    model_version: source.artifact_sha256 ?? null,
    score: scoreable ? Number(rawScore) : null,
    probability_of_default: scoreable ? Number(rawPd) : null,
    risk_tier: null,
    feature_coverage: observedFeatureCount / FROZEN_FEATURES.length,
    feature_values: featureValues,
    woe_values: trace
      ? Object.fromEntries(FROZEN_FEATURES.map((key) => [key, finite(trace[key]?.woe) ? Number(trace[key].woe) : null]))
      : Object.fromEntries(FROZEN_FEATURES.map((key) => [key, null])),
    feature_contributions: trace
      ? Object.fromEntries(FROZEN_FEATURES.map((key) => [key, finite(trace[key]?.contribution ?? trace[key]?.logit_contribution) ? Number(trace[key].contribution ?? trace[key].logit_contribution) : null]))
      : {},
    reason_codes: Array.isArray(source.reason_codes) ? source.reason_codes : [],
    improvement_recommendations: [],
    document_findings: source.document_findings ?? source.extraction ?? source.evidence ?? {},
    fraud_findings: source.fraud_findings ?? source.fraud_risk ?? null,
    assessment_timestamp: source.assessed_at ?? source.assessment_timestamp ?? null,
    scoreable,
    source,
  };
}

export function isValidFrozenAssessment(source) {
  return normalizeAssessmentResponse(source).scoreable;
}
