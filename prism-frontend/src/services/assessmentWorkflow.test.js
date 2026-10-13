import test from 'node:test';
import assert from 'node:assert/strict';
import { runAssessment, restoreAssessment } from './assessmentWorkflow.js';

test('remount reuses request; both scores remain separate', async () => {
  let bankCalls = 0, cardCalls = 0;
  const input = { sessionId: 'test', files: { bankStatements: [1,2,3,4,5,6], creditCards: [1,2,3,4,5,6] } };
  const api = { assessBankCashflow: async ({ files }) => { bankCalls++; assert.equal(files.length,6); return { score: 700 }; },
    assessCreditCardStatements: async () => { cardCalls++; return { score: 400 }; } };
  const first = runAssessment(input, api);
  assert.equal(first, runAssessment(input, api));
  const result = await first;
  assert.equal(bankCalls, 1); assert.equal(cardCalls, 1);
  assert.equal(result.score, 400); assert.equal(result.bank_cashflow_assessment.score, 700);
});

test('failed bank does not suppress valid card result', async () => {
  const input = { files: { bankStatements: [1], creditCards: [1] } };
  const result = await runAssessment(input, { assessBankCashflow: async () => { throw new Error('timeout'); },
    assessCreditCardStatements: async () => ({ score: 410 }) });
  assert.equal(result.score,410); assert.equal(result.processing_errors[0].message, 'timeout');
});

test('all failures terminate with an error', async () => {
  await assert.rejects(runAssessment({ files: { bankStatements: [1] } }, {
    assessBankCashflow: async () => { throw new Error('authentication required'); }
  }), /authentication required/);
});

test('historical cutoff is transmitted explicitly', async () => {
  await runAssessment({ cutoffMonth: '2026-09', files: { creditCards: [1] } }, {
    assessCreditCardStatements: async ({ cutoffMonth }) => { assert.equal(cutoffMonth, '2026-09'); return { score: 454.6 }; }
  });
});

test('bank-only update retains the same applications saved credit result', async () => {
  const result = await runAssessment({ sessionId: 'test', files: { bankStatements: [1] } }, {
    assessBankCashflow: async () => ({ assessment_id: 'bank', score: 775 }),
    borrowerLatestCreditAssessment: async id => { assert.equal(id,'test'); return { assessment_id: 'credit', score: 454.6 }; }
  });
  assert.equal(result.assessment_id,'credit'); assert.equal(result.bank_cashflow_assessment.assessment_id,'bank');
});

test('refresh recovers completed request even when timeout prevented saving IDs', async () => {
  const result = await restoreAssessment('test', null, null, {
    borrowerLatestCreditAssessment: async () => ({ assessment_id:'credit', score:454.6 }),
    borrowerBankCashflow: async () => ({ assessment_id:'bank', score:775 })
  });
  assert.equal(result.score,454.6); assert.equal(result.bank_cashflow_assessment.score,775);
});

test('bank-first single-file score survives an incomplete optional card result', async () => {
  const result = await runAssessment({bankFirst:true,sessionId:'test',files:{bankStatements:[1],creditCards:[1]}}, {
    assessBankCashflow: async ({assessmentProfile}) => {assert.equal(assessmentProfile,'auto');return {assessment_type:'BANK_CASHFLOW_EXPERIMENTAL',assessment_profile:'snapshot',score:696};},
    assessCreditCardStatements: async () => ({score:null,status:'INSUFFICIENT_EXPERIMENTAL_EVIDENCE'})
  });
  assert.equal(result.score,696);assert.equal(result.optional_credit_assessment,null);
});

test('bank-first requires a bank and rejects bad bank even with a scored card', async () => {
  await assert.rejects(runAssessment({bankFirst:true,files:{creditCards:[1]}},{}),/bank statement/);
  await assert.rejects(runAssessment({bankFirst:true,files:{bankStatements:[1],creditCards:[1]}},{
    assessBankCashflow:async()=>{throw new Error('Bank balances need correction');},
    assessCreditCardStatements:async()=>({score:450})
  }),/Bank balances/);
});

test('snapshot refresh keeps the bank score primary without missing-card prompts', async () => {
  const result=await restoreAssessment('test',null,'bank',{
    borrowerLatestCreditAssessment:async()=>({score:null,status:'INSUFFICIENT_EXPERIMENTAL_EVIDENCE'}),
    borrowerBankCashflow:async()=>({assessment_type:'BANK_CASHFLOW_EXPERIMENTAL',assessment_profile:'snapshot',score:696})
  });
  assert.equal(result.score,696);assert.equal(result.optional_credit_assessment,null);
});
