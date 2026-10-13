export function lenderCredit(payload) {
  const experimental = payload?.experimental_assessment;
  if (!experimental) return payload?.credit_risk || payload || {};
  return {
    status: experimental.status,
    assessment_id: experimental.assessment_id,
    risk_score: experimental.score,
    probability_of_default: experimental.probability_of_default,
    risk_tier: null,
    model_metadata: { model_name: 'PRISM_PHASE2F_FROZEN', model_version: experimental.model_version },
    reason_codes: experimental.reason_codes || [],
    contribution_unit: 'logit',
    shap_explanations: Object.entries(experimental.feature_contributions || {}).map(([feature_name, value]) => ({
      feature_name, score_contribution: Number(value),
      contribution_type: Number(value) > 0 ? 'Raises default logit' : Number(value) < 0 ? 'Lowers default logit' : 'Neutral',
      generated_reason: 'Signed coefficient × frozen WoE contribution; association, not a causal effect.'
    }))
  };
}
