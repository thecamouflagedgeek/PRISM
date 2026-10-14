import { API_BASE_URL } from "../api";

async function request(path, options = {}) {
  let response;
  try { response = await fetch(`${API_BASE_URL}${path}`, { ...options, signal: options.signal || AbortSignal.timeout(180000) }); }
  catch (cause) {
    const error = new Error(cause.name === 'TimeoutError' || cause.name === 'AbortError'
      ? 'Assessment timed out. Refresh to check saved results or try again.'
      : 'Unable to reach PRISM. Check that the backend is running.');
    error.status = cause.name === 'TimeoutError' || cause.name === 'AbortError' ? 408 : 503;
    throw error;
  }
  let body = null;
  try { body = await response.json(); } catch { /* non-JSON response */ }
  if (!response.ok) {
    const detail = body?.detail;
    const error = new Error((typeof detail === "string" ? detail : detail?.message) || body?.message || `Request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return body;
}

export const api = {
  demoFixtures: async (sessionId) => {
    const manifest = await request('/demo-fixtures', { headers: { 'session-id': sessionId } });
    const selected = { bankStatements: [], creditCards: [], salary: [], utility: [] };
    const loaded = await Promise.all(manifest.files.map(async item => {
      const response = await fetch(`${API_BASE_URL}/demo-fixtures/${item.category}/${encodeURIComponent(item.name)}`, {
        headers: { 'session-id': sessionId }, signal: AbortSignal.timeout(30000),
      });
      if (!response.ok) throw new Error(`Synthetic file selection failed (${response.status}).`);
      return { category: item.category === 'bank' ? 'bankStatements' : item.category,
        file: new File([await response.blob()], item.name, { type: 'application/pdf' }) };
    }));
    loaded.forEach(({ category, file }) => selected[category].push(file));
    return { files: selected, cutoffMonth: manifest.cutoff_month };
  },
  signup: (phone_number, role = "borrower") => request("/auth/signup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone_number, role }) }),
  verifyOtp: (phone_number, otp, role = "borrower") => request("/auth/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone_number, otp, role }) }),
  recordConsent: (payload) => request("/consent", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  borrowerConsent: (sessionId) => request('/consent', { headers: { 'session-id': sessionId } }),
  assess: ({ sessionId, files, passwords = {} }) => {
    if (!sessionId) throw new Error("Your session has expired. Please log in again.");
    if (!files?.bank) throw new Error("A bank statement is required to run an assessment.");
    const form = new FormData();
    form.append("bank_file", files.bank);
    if (files.salary) form.append("salary_file", files.salary);
    if (files.utility) form.append("utility_file", files.utility);
    if (passwords.bank) form.append("bank_password", passwords.bank);
    if (passwords.salary) form.append("salary_password", passwords.salary);
    if (passwords.utility) form.append("utility_password", passwords.utility);
    return request("/assess", { method: "POST", headers: { "session-id": sessionId }, body: form });
  },
  assessCreditCardStatements: ({ sessionId, files, consent, cutoffMonth }) => {
    if (!sessionId) throw new Error("Your session has expired. Please log in again.");
    const statements = files?.creditCards || [];
    if (!statements.length) throw new Error("Upload at least one credit-card statement.");
    const form = new FormData();
    statements.forEach((file) => form.append("statement_files", file, file.name));
    form.append("credit_card_consent", consent ? "true" : "false");
    if (cutoffMonth) form.append("prediction_cutoff_month", cutoffMonth);
    return request("/assess/credit-card-statements", { method: "POST", headers: { "session-id": sessionId }, body: form });
  },
  borrowerAssessment: (assessmentId, sessionId) => request(`/assess/credit-card-assessments/${assessmentId}`, { headers: { "session-id": sessionId } }),
  borrowerLatestCreditAssessment: (sessionId) => request('/assess/credit-card-assessments/latest', { headers: { 'session-id': sessionId } }),
  borrowerFinancialHealth: (sessionId) => request("/assess/financial-health/latest", { headers: { "session-id": sessionId } }),
  assessBankCashflow: ({ sessionId, files, supportingFiles = {}, assessmentProfile = 'history', statementPassword = '' }) => {
    if (!sessionId) throw new Error("Your session has expired. Please log in again.");
    const form = new FormData();
    form.append('assessment_profile', assessmentProfile);
    if(statementPassword) form.append('statement_password',statementPassword);
    (files || []).forEach((file) => form.append("statement_files", file, file.name));
    for (const category of ['salary', 'utility']) {
      const selected = supportingFiles[category];
      (Array.isArray(selected) ? selected : selected ? [selected] : []).forEach(file => form.append(`${category}_files`, file, file.name));
    }
    return request("/assess/bank-cashflow", { method: "POST", headers: { "session-id": sessionId }, body: form });
  },
  previewBankStatements: ({sessionId,files,statementPassword}) => {const form=new FormData();files.forEach(file=>form.append('statement_files',file,file.name));if(statementPassword)form.append('statement_password',statementPassword);return request('/assess/bank-cashflow/preview',{method:'POST',headers:{'session-id':sessionId},body:form});},
  borrowerBankCashflow: (sessionId, assessmentId) => request(`/assess/bank-cashflow/${assessmentId || 'latest'}`, { headers: { "session-id": sessionId } }),
  borrowerBankHistory: (sessionId) => request('/assess/bank-cashflow/history', { headers: { 'session-id': sessionId } }),
  bankCashflowWhatIf: (assessmentId, sessionId, scenario) => request(`/assess/bank-cashflow/${assessmentId}/what-if`, { method: "POST", headers: { "Content-Type": "application/json", "session-id": sessionId }, body: JSON.stringify(scenario) }),
  borrowerTenureComparison: (payload, sessionId) => request('/assess/bank-cashflow/tenure-comparison', { method: 'POST', headers: { 'Content-Type': 'application/json', 'session-id': sessionId }, body: JSON.stringify(payload) }),
  bankCashflowPdf: async (assessmentId, sessionId) => {
    const response = await fetch(`${API_BASE_URL}/assess/bank-cashflow/${assessmentId}/report.pdf`, { headers: { "session-id": sessionId } });
    if (!response.ok) throw new Error(`Bank assessment PDF request failed (${response.status}).`);
    return response.blob();
  },
  borrowerWhatIf: (assessmentId, sessionId, scenario) => request(`/assess/credit-card-assessments/${assessmentId}/what-if`, { method: "POST", headers: { "Content-Type": "application/json", "session-id": sessionId }, body: JSON.stringify(scenario) }),
  assessmentPdf: async (assessmentId, sessionId) => {
    const response = await fetch(`${API_BASE_URL}/assess/credit-card-assessments/${assessmentId}/report.pdf`, { headers: { "session-id": sessionId } });
    if (!response.ok) { const error = new Error(`PDF report request failed (${response.status}).`); error.status = response.status; throw error; }
    return response.blob();
  },
  whatIf: (sessionId, overrides) => request("/assess/whatif", { method: "POST", headers: { "Content-Type": "application/json", "session-id": sessionId }, body: JSON.stringify({ overrides }) }),
  lenderApplications: (sessionId) => request("/lender/applications", { headers: { "session-id": sessionId } }),
  lenderApplication: (applicationId, sessionId) => request(`/lender/applications/${applicationId}`, { headers: { "session-id": sessionId } }),
  lenderUpdateCase: (applicationId, sessionId, update) => request(`/lender/applications/${applicationId}/case-updates`, { method: "POST", headers: { "Content-Type": "application/json", "session-id": sessionId }, body: JSON.stringify(update) }),
  lenderTenureComparison: (applicationId, payload, sessionId) => request(`/lender/applications/${applicationId}/tenure-comparison`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'session-id': sessionId }, body: JSON.stringify(payload) }),
  lenderPortfolioSentiment: (sessionId) => request('/lender/portfolio/sentiment', { headers: { 'session-id': sessionId } }),
  lenderAuditEvents: (sessionId) => request("/lender/audit-events", { headers: { "session-id": sessionId } }),
};

export default api;
