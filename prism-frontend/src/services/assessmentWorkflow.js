const inFlight = new WeakMap();

export async function restoreAssessment(sessionId, creditId, bankId, api) {
  const responses = await Promise.allSettled([
    creditId ? api.borrowerAssessment(creditId, sessionId) : api.borrowerLatestCreditAssessment(sessionId),
    api.borrowerBankCashflow(sessionId, bankId)
  ]);
  const credit = responses[0].status === 'fulfilled' ? responses[0].value : null;
  const bank = responses[1].status === 'fulfilled' ? responses[1].value : null;
  if (bank?.assessment_profile && bank.score != null) return { ...bank, optional_credit_assessment: credit?.score != null ? credit : null };
  if (credit || bank) return credit ? { ...credit, bank_cashflow_assessment: bank } : bank;
  const authenticationError = responses.find(r => r.status === 'rejected' && [401,403].includes(r.reason.status));
  if (authenticationError) throw authenticationError.reason;
  const financial_health = await api.borrowerFinancialHealth(sessionId);
  return { status: 'INSUFFICIENT_EXPERIMENTAL_EVIDENCE', scoreable: false, financial_health,
    data_sufficiency: { reasons: ['CREDIT_CARD_STATEMENT_AND_REPAYMENT_HISTORY_REQUIRED'] },
    model_validation_status: 'PHASE_2B6_INCONCLUSIVE' };
}

export function runAssessment(input, api) {
  if (inFlight.has(input)) return inFlight.get(input);
  const promise = (async () => {
    const bank = input.files.bankStatements || (input.files.bank ? [input.files.bank] : []);
    const cards = input.files.creditCards || [];
    if (input.bankFirst && !bank.length) throw new Error('Upload a bank statement to begin your assessment.');
    const jobs = [];
    if (bank.length) jobs.push(['bank', api.assessBankCashflow({ sessionId: input.sessionId, files: bank, supportingFiles: input.files, statementPassword: input.statementPassword, assessmentProfile: input.bankFirst ? 'auto' : 'history' })]);
    if (cards.length) jobs.push(['credit', api.assessCreditCardStatements({ sessionId: input.sessionId, files: input.files, consent: input.creditCardConsent, cutoffMonth: input.cutoffMonth })]);
    const responses = await Promise.allSettled(jobs.map(([, job]) => job));
    const results = {}, errors = [];
    responses.forEach((response, index) => {
      if (response.status === 'fulfilled') results[jobs[index][0]] = response.value;
      else errors.push({ assessment_type: jobs[index][0], message: response.reason.message, status: response.reason.status });
    });
    if (input.bankFirst) {
      if (!results.bank) {
        const bankError = errors.find(error => error.assessment_type === 'bank');
        const error = new Error(bankError?.message || 'Please upload a clearer bank statement.');
        error.status = bankError?.status; throw error;
      }
      return { ...results.bank, optional_credit_assessment: results.credit?.score != null ? results.credit : null,
        optional_document_review: cards.length ? { uploaded: cards.length, status: results.credit?.score != null ? 'SCORED' : 'SUPPORTING_REVIEW',
          message: results.credit?.score != null ? 'Additional card-history assessment available.' : 'Card documents were reviewed separately. They are not required for your cash-flow score.' } : null,
        processing_errors: errors.filter(error => error.assessment_type !== 'credit') };
    }
    if (!results.bank && !results.credit) {
      const error = new Error(errors.map(e => e.message).join('; ') || 'No assessment documents selected.');
      error.status = errors[0]?.status;
      throw error;
    }
    if (!cards.length && results.bank && api.borrowerLatestCreditAssessment) {
      try { results.credit = await api.borrowerLatestCreditAssessment(input.sessionId); }
      catch (error) { if (error.status !== 404) errors.push({ assessment_type: 'credit', message: error.message, status: error.status }); }
    }
    return results.credit ? { ...results.credit, bank_cashflow_assessment: results.bank, processing_errors: errors }
      : { ...results.bank, processing_errors: errors };
  })();
  inFlight.set(input, promise);
  return promise;
}
