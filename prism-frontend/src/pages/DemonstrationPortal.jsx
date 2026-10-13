import { useEffect, useMemo, useState } from "react";
import { API_BASE_URL } from "../api";
import "./DemonstrationPortal.css";

const scopes = ["CREDIT_CARD_STATEMENTS", "BUREAU_REPAYMENT_HISTORY"];
const freshId = () => `APP_${crypto.randomUUID().replaceAll("-", "").slice(0, 10).toUpperCase()}`;
const pct = (value) => Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "Unavailable";

export default function DemonstrationPortal() {
  const [token, setToken] = useState(() => sessionStorage.getItem("prism_demo_token") || "");
  const [scenarios, setScenarios] = useState([]);
  const [scenario, setScenario] = useState("");
  const [evidenceText, setEvidenceText] = useState("");
  const [applicationId, setApplicationId] = useState(freshId);
  const [form, setForm] = useState({ borrower_reference: "SYN_BORROWER_DEMO_01", requested_loan_amount: "125000", loan_purpose: "Demonstration", employment_category: "SALARIED", declared_monthly_income: "65000", contact_reference: "SYN_CONTACT_DEMO_01" });
  const [consented, setConsented] = useState(false);
  const [consentAcknowledged, setConsentAcknowledged] = useState(false);
  const [created, setCreated] = useState(false);
  const [uploaded, setUploaded] = useState(null);
  const [assessment, setAssessment] = useState(null);
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}/phase4/demo${path}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail?.code || body.detail?.message || `Request failed (${response.status})`);
    return body;
  }

  useEffect(() => {
    if (!token) return;
    sessionStorage.setItem("prism_demo_token", token);
    request("/scenarios").then((body) => { setScenarios(body.scenarios || []); if (!scenario && body.scenarios?.length) setScenario(body.scenarios[0].id); }).catch((e) => setError(e.message));
    refreshHistory();
  // token is intentionally the only trigger; scenario selection is user controlled.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function refreshHistory() {
    try { setHistory((await request("/applications")).applications || []); } catch (e) { setError(e.message); }
  }
  async function run(action) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function loadScenario() {
    const body = await request(`/scenarios/${encodeURIComponent(scenario)}/evidence`);
    setEvidenceText(JSON.stringify(body, null, 2));
    setForm((current) => ({ ...current, borrower_reference: body.borrower_reference }));
    setUploaded(null); setAssessment(null);
    setMessage("Synthetic evidence loaded. Review the six statements and six repayment records before upload.");
  }
  async function createApplication() {
    await request("/applications", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...form, application_id: applicationId, requested_loan_amount: Number(form.requested_loan_amount), declared_monthly_income: Number(form.declared_monthly_income) }) });
    setCreated(true); setMessage("Application saved."); await refreshHistory();
  }
  async function recordConsent() {
    await request(`/applications/${encodeURIComponent(applicationId)}/consent`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ grant: true, scopes }) });
    setConsented(true); setConsentAcknowledged(true); setMessage("Consent recorded for credit card statements and bureau repayment history.");
  }
  async function withdrawConsent() {
    await request(`/applications/${encodeURIComponent(applicationId)}/consent`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ grant: false, scopes: [] }) });
    setConsented(false); setConsentAcknowledged(false); setMessage("Consent withdrawn. Assessment is now blocked by the backend.");
  }
  async function submitEvidence() {
    const parsed = JSON.parse(evidenceText);
    const file = new File([JSON.stringify(parsed)], "credit-account-evidence.json", { type: "application/json" });
    const data = new FormData(); data.append("file", file);
    const body = await request(`/applications/${encodeURIComponent(applicationId)}/evidence`, { method: "POST", body: data });
    setUploaded(body); setMessage("Evidence validated and stored with its SHA-256 provenance hash.");
  }
  async function assess() {
    const body = await request(`/applications/${encodeURIComponent(applicationId)}/assess`, { method: "POST" });
    setAssessment(body); setMessage("Assessment result saved. Fraud checks are shown separately from model scoring."); await refreshHistory();
  }
  async function openHistory(id) {
    await run(async () => {
      const body = await request(`/applications/${encodeURIComponent(id)}`);
      setApplicationId(id); setAssessment(body.application.assessments?.at(-1) ? { result: body.application.assessments.at(-1).result, assessed_at: body.application.assessments.at(-1).assessed_at } : null);
      setCreated(true); setConsented(body.application.consent?.state === "GRANTED"); setConsentAcknowledged(body.application.consent?.state === "GRANTED"); setUploaded(body.application.evidence?.at(-1) || null);
      setMessage(`Loaded persisted history for ${id}.`);
    });
  }
  async function deleteHistory(id) {
    if (!window.confirm(`Delete application ${id} and its stored consent, evidence, and assessment history?`)) return;
    await run(async () => {
      await request(`/applications/${encodeURIComponent(id)}`, { method: "DELETE" });
      setHistory((items) => items.filter((item) => item.application_id !== id));
      if (applicationId === id) { setCreated(false); setConsented(false); setConsentAcknowledged(false); setUploaded(null); setAssessment(null); }
      setMessage(`Deleted ${id} and its stored demo history.`);
    });
  }

  const result = assessment?.result;
  const scorecard = result?.scorecard;
  const trace = result?.trace;
  return <main className="p4-shell">
    <header className="p4-header"><div><p className="p4-kicker">PRISM · CONTROLLED DEMONSTRATION</p><h1>Borrower to lender, with evidence</h1><p>Experimental shadow assessment · synthetic examples · not for lending decisions</p></div><a href="/experimental-credit-evidence-lab">Scoring lab</a></header>
    <aside className="p4-notice"><strong>Higher score means lower model-estimated default risk</strong><span>This UCI-trained scorecard has no external or Indian-market validation. It is not a bureau score or an operational lending threshold.</span></aside>
    <section className="p4-card p4-access"><label>Controlled demo access token<input type="password" autoComplete="off" value={token} onChange={(e) => { setToken(e.target.value); setScenarios([]); setError(""); }} placeholder="Enter the demo token provided by the operator" /></label><label>Scenario<select value={scenario} onChange={(e) => { setScenario(e.target.value); setUploaded(null); setAssessment(null); }}>{scenarios.map((s) => <option key={s.id} value={s.id}>{s.label} · synthetic</option>)}</select></label><button className="p4-button secondary" disabled={!token || busy} onClick={() => run(loadScenario)}>Load synthetic evidence</button></section>
    <div className="p4-grid">
      <section className="p4-card"><h2>1 · Application</h2><label>Application ID<input value={applicationId} onChange={(e) => setApplicationId(e.target.value)} /></label><label>Borrower reference<input value={form.borrower_reference} onChange={(e) => setForm({ ...form, borrower_reference: e.target.value })} /></label><div className="p4-two"><label>Requested amount<input type="number" min="1" value={form.requested_loan_amount} onChange={(e) => setForm({ ...form, requested_loan_amount: e.target.value })} /></label><label>Monthly income<input type="number" min="0" value={form.declared_monthly_income} onChange={(e) => setForm({ ...form, declared_monthly_income: e.target.value })} /></label></div><div className="p4-two"><label>Purpose<input value={form.loan_purpose} onChange={(e) => setForm({ ...form, loan_purpose: e.target.value })} /></label><label>Employment<select value={form.employment_category} onChange={(e) => setForm({ ...form, employment_category: e.target.value })}>{["SALARIED", "SELF_EMPLOYED", "CONTRACT", "OTHER"].map((x) => <option key={x}>{x}</option>)}</select></label></div><button className="p4-button" disabled={busy || !token} onClick={() => run(createApplication)}>Save application</button><span className="p4-state">{created ? "Saved" : "Not saved"}</span></section>
      <section className="p4-card"><h2>2 · Consent and evidence</h2><p>Consent is required before evidence can be uploaded or scoring can run.</p><label className="p4-check"><input type="checkbox" checked={consentAcknowledged} onChange={(e) => setConsentAcknowledged(e.target.checked)} /> I authorize use of credit card statements and bureau repayment history for this experimental demonstration.</label><div className="p4-actions"><button className="p4-button secondary" disabled={!created || busy || !consentAcknowledged || consented} onClick={() => run(recordConsent)}>Record consent</button><button className="p4-button secondary" disabled={!created || busy || !consented} onClick={() => run(withdrawConsent)}>Withdraw consent</button></div><label>Validated evidence JSON<textarea rows="12" value={evidenceText} onChange={(e) => setEvidenceText(e.target.value)} placeholder="Load a synthetic scenario or paste supported evidence JSON" /></label><button className="p4-button" disabled={!created || !consented || busy || !evidenceText} onClick={() => run(submitEvidence)}>Validate and upload evidence</button>{uploaded && <small>Stored · {uploaded.evidence_id || uploaded.sha256 || uploaded.filename} · {uploaded.synthetic_demo ? "packaged synthetic evidence" : "user-supplied evidence"}</small>}</section>
    </div>
    <section className="p4-card p4-assess"><div><h2>3 · Assess and inspect</h2><p>Uses the frozen Phase 2F model after Phase 2E evidence parsing and validation. No score is generated when evidence is insufficient. You can also run before consent or upload to see the fail-closed response.</p></div><button className="p4-button orange" disabled={!created || busy} onClick={() => run(assess)}>Run assessment</button></section>
    {error && <div className="p4-error" role="alert">{error}</div>}{message && <div className="p4-message" role="status">{message}</div>}
    {result && <section className="p4-card p4-results"><div className="p4-result-head"><div><p className="p4-kicker">{result.status || "Assessment"}</p><h2>{scorecard ? "PRISM Experimental Score" : "No score generated"}</h2><p>{assessment.assessed_at || "Saved assessment"} · {result.model_status || "evidence validation result"}</p></div>{scorecard && <div className="p4-score">{Number(scorecard.experimental_shadow_score ?? scorecard.score).toFixed(0)}<small>Higher = lower estimated risk</small></div>}</div>
      {scorecard && <div className="p4-stats"><div><small>Raw model PD</small><b>{pct(scorecard.raw_pd ?? scorecard.pd)}</b></div><div><small>Good-to-bad odds</small><b>{Number(scorecard.good_bad_odds ?? scorecard.odds).toFixed(3)} : 1</b></div><div><small>Model version</small><b>Frozen Phase 2F</b></div><div><small>Evidence</small><b>{result.evidence?.months_validated || 6} months · validated</b></div></div>}
      {result.eligibility?.blocking_reasons?.length > 0 && <p className="p4-error">{result.eligibility.blocking_reasons.join(" · ")}</p>}
      {trace && <><h3>Feature contributions to model logit</h3><div className="p4-table-wrap"><table><thead><tr><th>Feature</th><th>Value</th><th>Bin</th><th>Contribution</th></tr></thead><tbody>{Object.entries(trace.feature_contributions || {}).map(([name, value]) => <tr key={name}><td>{name.replaceAll("_", " ")}</td><td>{result.features?.[name] ?? "—"}</td><td>{trace.bin_assignments?.[name] ?? "—"}</td><td>{Number(value).toFixed(4)}</td></tr>)}</tbody></table></div><h3>Main model reasons</h3><ul>{(result.reason_codes || []).map((reason) => <li key={reason.code}>{reason.label} · {reason.direction} · contribution {Number(reason.contribution).toFixed(4)}</li>)}</ul>{!(result.reason_codes || []).length && <p>No adverse reason codes returned by the scorecard.</p>}</>}
      <h3>Fraud assessment · separate from credit score</h3><pre>{JSON.stringify(result.fraud_risk || { status: "Unavailable" }, null, 2)}</pre><small>Model artifact SHA-256: {trace?.artifact_sha256 || "Not scored"} · Decision use: {result.decision_use || "NOT_FOR_CREDIT_DECISION"}</small></section>}
    <section className="p4-card"><div className="p4-history-head"><div><h2>4 · Lender dashboard and history</h2><p>Applications and results retrieved from the backend database. Refreshing this page does not remove saved history.</p></div><button className="p4-button secondary" disabled={!token || busy} onClick={() => run(refreshHistory)}>Refresh history</button></div>{history.length ? <div className="p4-table-wrap"><table><thead><tr><th>Application</th><th>Created</th><th>Consent</th><th>Evidence</th><th>Latest result</th><th></th></tr></thead><tbody>{history.map((item) => <tr key={item.application_id}><td>{item.application_id}</td><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.consent_state}</td><td>{item.evidence_count}</td><td>{item.latest_status || "Pending"}</td><td><button className="p4-link" onClick={() => openHistory(item.application_id)}>Open</button> · <button className="p4-link" onClick={() => deleteHistory(item.application_id)}>Delete</button></td></tr>)}</tbody></table></div> : <p>No saved applications for this demo token yet.</p>}</section>
    <footer>Evidence and profiles in the included scenarios are synthetic. Demo persistence uses a local SQLite file. Do not enter real borrower documents.</footer>
  </main>;
}
