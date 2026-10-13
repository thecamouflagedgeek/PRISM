import test from 'node:test';
import assert from 'node:assert/strict';
import { lenderCredit } from './lenderAssessmentContract.js';

test('persisted experimental score and signed contributions are recognized', () => {
  const output = lenderCredit({ experimental_assessment: {
    status: 'EXPERIMENTAL_SHADOW_SCORE', score: 454.6, probability_of_default: .2728,
    model_version: 'frozen', feature_contributions: { delinquency: .87, payment: -.28 }
  } });
  assert.equal(output.status,'EXPERIMENTAL_SHADOW_SCORE'); assert.equal(output.risk_score,454.6);
  assert.equal(output.contribution_unit,'logit'); assert.equal(output.risk_tier,null);
  assert.equal(output.shap_explanations[0].contribution_type,'Raises default logit');
});
