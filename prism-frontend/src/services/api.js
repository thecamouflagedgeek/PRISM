const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  let response;
  try { response = await fetch(`${API_BASE_URL}${path}`, options); }
  catch { throw new Error("Unable to reach PRISM. Check that the backend is running."); }
  let body = null;
  try { body = await response.json(); } catch { /* non-JSON response */ }
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error((typeof detail === "string" ? detail : detail?.message) || body?.message || `Request failed (${response.status}).`);
  }
  return body;
}

export const api = {
  signup: (phone_number) => request("/auth/signup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone_number }) }),
  verifyOtp: (phone_number, otp) => request("/auth/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone_number, otp }) }),
  recordConsent: (payload) => request("/consent", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  assess: ({ sessionId, files, passwords = {} }) => {
    if (!sessionId) throw new Error("Your session has expired. Please log in again.");
    if (!files?.bank) throw new Error("A bank statement is required to run an assessment.");
    const form = new FormData();
    form.append("bank_file", files.bank);
    if (files.salary) form.append("salary_file", files.salary);
    if (files.utility) form.append("utility_file", files.utility);
    if (passwords.bank) form.append("bank_password", passwords.bank);
    if (passwords.utility) form.append("utility_password", passwords.utility);
    return request("/assess", { method: "POST", headers: { "session-id": sessionId }, body: form });
  },
  whatIf: (sessionId, overrides) => request("/assess/whatif", { method: "POST", headers: { "Content-Type": "application/json", "session-id": sessionId }, body: JSON.stringify({ overrides }) }),
  lenderApplications: () => request("/lender/applications"),
  lenderApplication: (applicationId) => request(`/lender/applications/${applicationId}`),
  lenderAuditEvents: () => request("/lender/audit-events"),
};

export default api;
