import { useCallback, useEffect, useMemo, useState } from "react";
import { Nav } from "../components/Nav";
import { api } from "../services/api";
import LoanObligationReview from "../components/LoanObligationReview";
import RepaymentTenureComparison from "../components/RepaymentTenureComparison";
import PortfolioSentimentStatus from "../components/PortfolioSentimentStatus";
import "./LenderDashboard.css";

const sections = [
  ["overview", "Overview", "▦"],
  ["applications", "Case queue", "▤"],
  ["portfolio", "Portfolio", "◷"],
  ["activity", "Audit trail", "⌁"],
];
const filters = ["All cases", "New", "In review", "Awaiting documents", "Completed", "Needs attention"];
const statusLabels = { NEW: "New", IN_REVIEW: "In review", AWAITING_DOCUMENTS: "Awaiting documents", COMPLETED: "Completed" };
const readable = value => String(value || "Not recorded").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase());
const formatDate = value => value ? new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";
const formatDateTime = value => value ? new Date(value).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
const formatMoney = (value, currency = "INR") => value == null ? "—" : new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value));
const maskedPhone = value => value ? `${"•".repeat(Math.max(0, String(value).length - 4))}${String(value).slice(-4)}` : "Borrower";
const statusOf = row => row?.review?.review_status || "NEW";
const scoreAvailable = value => value !== null && value !== undefined && Number.isFinite(Number(value));

function Metric({ label, value, detail, tone = "" }) {
  return <article className={`lender-metric ${tone}`}><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</article>;
}

function StatusPill({ status }) {
  const code = status || "NEW";
  return <span className={`lender-status status-${String(code).toLowerCase()}`}>{statusLabels[code] || readable(code)}</span>;
}

function EmptyState({ title, message }) {
  return <div className="lender-empty"><span>◇</span><h3>{title}</h3><p>{message}</p></div>;
}

export default function LenderDashboard({ go, lenderSession, setLenderAssessment }) {
  const [applications, setApplications] = useState([]);
  const [events, setEvents] = useState([]);
  const [section, setSection] = useState("overview");
  const [filter, setFilter] = useState("All cases");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [assessment, setAssessment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [statusDraft, setStatusDraft] = useState("IN_REVIEW");
  const [noteDraft, setNoteDraft] = useState("");
  const [requestDraft, setRequestDraft] = useState("");

  const loadApplications = useCallback(async () => {
    if (!lenderSession?.session_id) { go("lenderLogin"); return; }
    setLoading(true);
    setError("");
    try {
      const response = await api.lenderApplications(lenderSession.session_id);
      setApplications(Array.isArray(response) ? response : response?.applications || []);
    } catch (requestError) {
      setError(requestError.message || "Unable to load lender cases.");
      if (requestError.status === 401 || requestError.status === 403) go("lenderLogin");
    } finally { setLoading(false); }
  }, [lenderSession?.session_id, go]);

  const loadEvents = useCallback(async () => {
    if (!lenderSession?.session_id) return;
    try {
      const response = await api.lenderAuditEvents(lenderSession.session_id);
      setEvents(response?.events || []);
    } catch (requestError) { setError(requestError.message || "Unable to load the audit trail."); }
  }, [lenderSession?.session_id]);

  useEffect(() => { loadApplications(); }, [loadApplications]);
  useEffect(() => { loadEvents(); }, [loadEvents]);

  const openCase = async row => {
    setSelected(row);
    setSection("applications");
    setAssessment(null);
    setError("");
    setNotice("");
    setDetailLoading(true);
    try {
      const value = await api.lenderApplication(row.application_id, lenderSession?.session_id);
      setAssessment(value);
      setLenderAssessment(value);
      const status = value.review?.review_status || row.review?.review_status || "NEW";
      setStatusDraft(status === "NEW" ? "IN_REVIEW" : status);
    } catch (requestError) { setError(requestError.message || "Unable to open this case."); }
    finally { setDetailLoading(false); }
  };

  const recordCaseAction = async payload => {
    if (!selected?.application_id || !lenderSession?.session_id) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const response = await api.lenderUpdateCase(selected.application_id, lenderSession.session_id, payload);
      setAssessment(current => current ? { ...current, review: response.review } : current);
      setNotice(response.message || "Update recorded in the audit trail.");
      if (payload.action === "add_note") setNoteDraft("");
      if (payload.action === "request_information") setRequestDraft("");
      await Promise.all([loadApplications(), loadEvents()]);
      const updated = await api.lenderApplication(selected.application_id, lenderSession.session_id);
      setAssessment(updated);
      setLenderAssessment(updated);
    } catch (requestError) { setError(requestError.message || "The case update could not be saved."); }
    finally { setSaving(false); }
  };

  const sortedApplications = useMemo(() => [...applications].sort((a, b) => {
    const order = { NEW: 0, IN_REVIEW: 1, AWAITING_DOCUMENTS: 2, COMPLETED: 3 };
    const workflow = (order[statusOf(a)] ?? 4) - (order[statusOf(b)] ?? 4);
    return workflow || new Date(b.application_date || 0) - new Date(a.application_date || 0);
  }), [applications]);
  const visibleApplications = useMemo(() => sortedApplications.filter(row => {
    const status = statusOf(row);
    const attention = !scoreAvailable(row.bank_health_index) && !scoreAvailable(row.risk_score) || Number(row.bank_fraud_flag_count) > 0;
    const matchesFilter = filter === "All cases" || (filter === "Needs attention" ? attention : statusLabels[status] === filter);
    const query = search.trim().toLowerCase();
    const matchesSearch = !query || String(row.application_id).includes(query) || String(row.borrower_phone || "").toLowerCase().includes(query);
    return matchesFilter && matchesSearch;
  }), [sortedApplications, filter, search]);

  const statusCounts = useMemo(() => applications.reduce((counts, row) => {
    const status = statusOf(row);
    counts[status] = (counts[status] || 0) + 1;
    return counts;
  }, {}), [applications]);
  const scoredBankCases = applications.filter(row => scoreAvailable(row.bank_health_index));
  const meanBankScore = scoredBankCases.length ? Math.round(scoredBankCases.reduce((total, row) => total + Number(row.bank_health_index), 0) / scoredBankCases.length) : null;
  const flaggedCases = applications.filter(row => Number(row.bank_fraud_flag_count) > 0).length;
  const submissionsByMonth = useMemo(() => {
    const grouped = new Map();
    applications.forEach(row => {
      if (!row.application_date) return;
      const month = new Date(row.application_date).toISOString().slice(0, 7);
      grouped.set(month, (grouped.get(month) || 0) + 1);
    });
    return [...grouped].sort(([a], [b]) => a.localeCompare(b));
  }, [applications]);
  const sectionTitle = sections.find(item => item[0] === section)?.[1] || "Overview";
  const bank = assessment?.bank_cashflow_assessment;
  const credit = assessment?.credit_risk;
  const fraud = bank?.fraud_findings || {};
  const assignedToMe = assessment?.review?.assigned_to && assessment.review.assigned_to === lenderSession?.phone_number;

  return <div className="lender-workspace">
    <Nav currentPage="lenderDashboard" onLogoClick={() => setSection("overview")} onLogout={() => go("landing")} />
    <div className="lender-shell">
      <aside className="lender-sidebar">
        <div className="lender-sidebar-brand"><span>PR</span><div><strong>PRISM</strong><small>LENDER WORKSPACE</small></div></div>
        <nav aria-label="Lender workspace navigation">{sections.map(([key, label, icon]) => <button key={key} className={section === key ? "active" : ""} onClick={() => setSection(key)}><span aria-hidden="true">{icon}</span>{label}{key === "applications" && applications.length > 0 && <small>{applications.length}</small>}</button>)}</nav>
        <div className="lender-sidebar-note"><span className="lender-online-dot" />Authenticated lender session<p>{lenderSession?.phone_number || "Secure workspace"}</p></div>
        <button className="lender-sidebar-logout" onClick={() => go("landing")}>Sign out</button>
      </aside>

      <main className="lender-main">
        <header className="lender-page-header"><div><span className="lender-eyebrow">LENDER WORKSPACE / {sectionTitle.toUpperCase()}</span><h1>{section === "overview" ? "Application review, made clear." : sectionTitle}</h1><p>Review borrower evidence, document your process, and keep PRISM outputs in context.</p></div><div className="lender-header-actions"><span className="lender-session-chip"><i />Secure session</span><button className="lender-refresh" onClick={() => { loadApplications(); loadEvents(); }}>↻ <span>Refresh</span></button></div></header>

        {error && <div className="lender-alert" role="alert"><strong>Something needs attention</strong><span>{error}</span></div>}
        {notice && <div className="lender-notice" role="status">{notice}</div>}

        {section === "overview" && <>
          <section className="lender-metrics-grid" aria-label="Portfolio summary">
            <Metric label="Total applications" value={applications.length} detail="All applications in the lender workspace" />
            <Metric label="New cases" value={statusCounts.NEW || 0} detail="Not yet assigned to a reviewer" tone="orange" />
            <Metric label="Awaiting information" value={statusCounts.AWAITING_DOCUMENTS || 0} detail="Request recorded in case history" tone="amber" />
            <Metric label="Bank scores available" value={scoredBankCases.length} detail={meanBankScore == null ? "No observed index yet" : `Mean observed-pattern index ${meanBankScore}`} tone="green" />
          </section>
          <section className="lender-overview-grid">
            <article className="lender-card lender-queue-card"><div className="lender-card-heading"><div><span className="lender-eyebrow">PRIORITIZED QUEUE</span><h2>Cases to review</h2><p>New and unresolved cases appear first.</p></div><button className="lender-link-button" onClick={() => setSection("applications")}>Open full queue →</button></div>
              {loading ? <div className="lender-loading">Loading applications…</div> : sortedApplications.length ? <ApplicationTable rows={sortedApplications.slice(0, 7)} onOpen={openCase} /> : <EmptyState title="No applications yet" message="Borrower applications will appear here when they are submitted and assessed." />}
            </article>
            <aside className="lender-card lender-workflow-card"><span className="lender-eyebrow">REVIEW FLOW</span><h2>Keep every case traceable</h2><ol><li><b>1</b><span>Open a case and check its evidence.</span></li><li><b>2</b><span>Record a reviewer, status, note, or information request.</span></li><li><b>3</b><span>Use the audit trail to see what changed and when.</span></li></ol><div className="lender-boundary-note"><strong>Decision boundary</strong><p>PRISM’s experimental indices are descriptive research outputs. Your institution owns its underwriting decision and rationale.</p></div></aside>
          </section>
        </>}

        {section === "applications" && <section className={`lender-case-layout ${selected ? "has-selection" : ""}`}>
          <article className="lender-card lender-queue-card"><div className="lender-card-heading"><div><span className="lender-eyebrow">APPLICATION QUEUE</span><h2>Borrower cases</h2><p>{loading ? "Refreshing cases…" : `${applications.length} total applications`}</p></div><label className="lender-search"><span aria-hidden="true">⌕</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search ID or phone" aria-label="Search application ID or borrower phone" /></label></div>
            <div className="lender-filters" role="group" aria-label="Filter applications">{filters.map(item => <button key={item} className={filter === item ? "selected" : ""} onClick={() => setFilter(item)}>{item}</button>)}</div>
            {visibleApplications.length ? <ApplicationTable rows={visibleApplications} onOpen={openCase} selectedId={selected?.application_id} /> : <EmptyState title="No matching applications" message="Try another status filter or search term." />}
          </article>
          <article className="lender-card lender-detail-card">
            {!selected ? <EmptyState title="Select a case" message="Choose an application to inspect its scorecards, evidence, integrity checks and review history." /> : detailLoading ? <div className="lender-loading">Loading application evidence…</div> : assessment ? <>
              <CaseHeader detail={assessment} assignedToMe={assignedToMe} />
              <section className="lender-detail-section"><div className="lender-section-title"><span>ASSESSMENT SNAPSHOT</span><h3>Separate evidence views</h3></div><div className="lender-scorecards">
                <Scorecard title="Bank Financial Health Index" score={bank?.score} status={bank?.status} model={bank?.model_version} detail={bank?.months_observed != null ? `${bank.months_observed} observed month${bank.months_observed === 1 ? "" : "s"} · ${bank.transaction_count ?? 0} transactions` : "Bank score not available"} description="Descriptive cash-flow index. Not a bureau score, probability of default, or lending decision." />
                <Scorecard title="Credit research model" score={credit?.risk_score} status={credit?.status} model={credit?.model_metadata?.model_version || credit?.model_metadata?.model_name} detail={credit?.probability_of_default == null ? "No validated probability shown" : `Research output · PD ${(Number(credit.probability_of_default) * 100).toFixed(2)}%`} description="Frozen experimental output. Not validated for Indian lending decisions and not an approval recommendation." />
              </div></section>
              {bank && <LoanObligationReview data={bank.loan_obligation_review || {status: "NOT_AVAILABLE", observed_signal: "This saved assessment predates the recurring payment review. Missing results do not indicate that no obligations exist."}}/>}
              {bank && <RepaymentTenureComparison applicationId={assessment.application_id} assessmentId={bank.assessment_id} session={lenderSession} viewerMode/>}

              <section className="lender-detail-section"><div className="lender-section-title"><span>DOCUMENTS AND SOURCE CHECKS</span><h3>Evidence received</h3></div>
                {bank?.financial_metrics && <div className="lender-cashflow-grid">{[["Average monthly income", bank.financial_metrics.average_monthly_income], ["Average monthly outflow", bank.financial_metrics.average_monthly_expenses], ["Average observed balance", bank.financial_metrics.average_observed_closing_balance ?? bank.financial_metrics.average_balance], ["Identified debt payments", bank.financial_metrics.identified_monthly_debt_payments]].map(([label, value]) => <div key={label}><small>{label}</small><strong>{formatMoney(value, bank.currency || "INR")}</strong></div>)}</div>}
                {assessment.documents?.length ? <div className="lender-document-list">{assessment.documents.map((document, index) => <article key={document.document_id || `${document.file_name}-${index}`}><span className="lender-document-icon">▧</span><div><strong>{document.file_name || readable(document.document_type)}</strong><small>{readable(document.document_type)} · {readable(document.processing_status)} · {formatDateTime(document.upload_timestamp)}</small></div><StatusPill status={document.processing_status === "EXTRACTED" ? "COMPLETED" : "IN_REVIEW"} /></article>)}</div> : <p className="lender-muted-copy">No uploaded documents are attached to this application.</p>}
                {bank?.evidence && <div className="lender-evidence-grid">{[["Account continuity", bank.evidence.account_linked], ["Balance reconciliation", bank.evidence.balance_reconciled], ["Statement pages", bank.evidence.page_coverage_complete], ["Month coverage", bank.evidence.complete_month_coverage], ["Transaction order", bank.evidence.transaction_order_valid]].map(([label, value]) => <div key={label}><span className={value === true ? "pass" : value === false ? "attention" : "unknown"}>{value === true ? "✓" : value === false ? "!" : "—"}</span><small>{label}</small><strong>{value === true ? "Checked" : value === false ? "Review" : "Not reported"}</strong></div>)}</div>}
                {assessment.consent && <p className="lender-consent-line">Recorded consent scope: {Object.entries(assessment.consent).filter(([, value]) => value === true).map(([key]) => readable(key)).join(" · ") || "No active scope reported"}</p>}
              </section>

              <section className="lender-detail-section"><div className="lender-section-title"><span>REASONS AND FACTORS</span><h3>What the assessment used</h3></div>
                {bank?.feature_contributions?.length ? <div className="lender-factor-list">{bank.feature_contributions.map((item, index) => <article key={`${item.feature}-${index}`}><div><strong>{readable(item.feature)}</strong><small>{item.explanation || (item.direction === "FAVORABLE" ? "Favorable observed pattern" : "Pattern to review")}</small></div><div><small>Contribution</small><strong>{item.score_contribution == null ? "—" : Number(item.score_contribution).toFixed(1)}</strong></div></article>)}</div> : credit?.feature_contributions?.length ? <div className="lender-factor-list">{credit.feature_contributions.map((item, index) => <article key={`${item.feature}-${index}`}><div><strong>{readable(item.feature)}</strong><small>{item.explanation || readable(item.direction)}</small></div><div><small>Contribution</small><strong>{item.score_contribution ?? "—"}</strong></div></article>)}</div> : <p className="lender-muted-copy">No score factor contributions are available for this application.</p>}
                {credit?.reason_codes?.length > 0 && <div className="lender-reason-codes"><strong>Research model reason codes</strong><div>{credit.reason_codes.map((reason, index) => <span key={`${reason}-${index}`}>{readable(reason)}</span>)}</div></div>}
                {bank?.recommendations?.length > 0 && <div className="lender-recommendations"><strong>Model-generated borrower guidance</strong><ul>{bank.recommendations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></div>}
              </section>

              <section className="lender-detail-section"><div className="lender-section-title"><span>INDEPENDENT SCREEN</span><h3>Fraud and document integrity</h3><p>Heuristic signals require human review; a signal does not establish fraud.</p></div>
                {fraud.fraud_status ? <div className="lender-fraud-summary"><span className={`lender-fraud-status ${fraud.flags?.length ? "flagged" : "clear"}`}>{readable(fraud.fraud_status)}</span><span>{fraud.flags?.length || 0} signal{fraud.flags?.length === 1 ? "" : "s"}</span><span>{fraud.coverage?.transactions_reviewed ?? bank?.transaction_count ?? "—"} transactions screened</span><small>{fraud.engine_version || "Fraud engine"} · {fraud.score_semantics || "Heuristic signal, not probability"}</small></div> : <p className="lender-muted-copy">No saved bank transaction fraud review is available.</p>}
                {fraud.flags?.length > 0 && <div className="lender-flag-list">{fraud.flags.map((flag, index) => <article key={`${flag.rule || flag.type}-${index}`}><span>{readable(flag.severity || "Review")}</span><div><strong>{readable(flag.rule || flag.type)}</strong><p>{flag.message || flag.detail || "Review the source transaction and surrounding evidence."}</p></div></article>)}</div>}
                {assessment.document_risk && Object.keys(assessment.document_risk).length > 0 && <details className="lender-details"><summary>Document risk findings</summary><pre>{JSON.stringify(assessment.document_risk, null, 2)}</pre></details>}
                {bank?.document_findings?.length > 0 && <details className="lender-details"><summary>Statement extraction findings</summary><pre>{JSON.stringify(bank.document_findings.map(item => ({ file_name: item.file_name, statement_period: item.statement_period, findings: item.findings, validation_result: item.validation_result })), null, 2)}</pre></details>}
              </section>

              <CaseActions detail={assessment} currentLender={lenderSession} statusDraft={statusDraft} setStatusDraft={setStatusDraft} noteDraft={noteDraft} setNoteDraft={setNoteDraft} requestDraft={requestDraft} setRequestDraft={setRequestDraft} saving={saving} onAction={recordCaseAction} />
              <ReviewTimeline events={assessment.review_history || []} />
            </> : null}
          </article>
        </section>}

        {section === "portfolio" && <>
          <section className="lender-metrics-grid lender-portfolio-metrics"><Metric label="Cases in review" value={statusCounts.IN_REVIEW || 0} detail="Assigned review work" /><Metric label="Awaiting information" value={statusCounts.AWAITING_DOCUMENTS || 0} detail="Open information requests" tone="amber" /><Metric label="Cases completed" value={statusCounts.COMPLETED || 0} detail="Marked complete by a lender" tone="green" /><Metric label="Cases with fraud signals" value={flaggedCases} detail="Independent review signals" tone={flaggedCases ? "orange" : "green"} /></section>
          <section className="lender-portfolio-grid"><article className="lender-card"><div className="lender-card-heading"><div><span className="lender-eyebrow">OBSERVED SCORES</span><h2>Bank index coverage</h2><p>Descriptive bank scores only; credit research scores are not combined with them.</p></div></div><div className="lender-portfolio-score"><strong>{meanBankScore ?? "—"}</strong><span>{scoredBankCases.length} of {applications.length} applications have a bank index</span></div>{scoredBankCases.length > 0 && <div className="lender-score-range"><span>Lowest observed: {Math.min(...scoredBankCases.map(row => Number(row.bank_health_index)))}</span><span>Highest observed: {Math.max(...scoredBankCases.map(row => Number(row.bank_health_index)))}</span></div>}</article>
            <article className="lender-card"><div className="lender-card-heading"><div><span className="lender-eyebrow">APPLICATION INTAKE</span><h2>Submissions over time</h2><p>Grouped from application dates in the records.</p></div></div>{submissionsByMonth.length ? <div className="lender-intake-chart">{submissionsByMonth.map(([month, count]) => <div key={month}><span>{count}</span><i style={{ height: `${Math.max(8, count / Math.max(...submissionsByMonth.map(([, value]) => value)) * 130)}px` }} /><small>{new Date(`${month}-01T00:00:00`).toLocaleDateString("en-IN", { month: "short", year: "2-digit" })}</small></div>)}</div> : <EmptyState title="No dated submissions" message="Application intake will appear once application dates are available." />}</article></section>
          <section className="lender-portfolio-grid"><PortfolioSentimentStatus sessionId={lenderSession?.session_id}/></section>
          <section className="lender-card lender-portfolio-table"><div className="lender-card-heading"><div><span className="lender-eyebrow">CASE DISTRIBUTION</span><h2>Workflow status</h2></div></div><div className="lender-status-distribution">{Object.entries(statusLabels).map(([code, label]) => <button key={code} onClick={() => { setFilter(label); setSection("applications"); }}><span>{label}</span><strong>{statusCounts[code] || 0}</strong></button>)}</div></section>
        </>}

        {section === "activity" && <section className="lender-card lender-audit-page"><div className="lender-card-heading"><div><span className="lender-eyebrow">TRACEABLE CASE ACTIVITY</span><h2>Audit trail</h2><p>Recent PRISM and lender workflow events across accessible applications.</p></div><span className="lender-audit-count">{events.length} events loaded</span></div>
          {events.length ? <div className="lender-audit-list">{events.map(event => <article key={event.event_id}><span className={`lender-audit-icon ${event.action?.startsWith("lender_") ? "lender" : "system"}`}>{event.action?.startsWith("lender_") ? "L" : "P"}</span><div className="lender-audit-copy"><strong>{readable(event.action)}</strong><p>Application {event.application_id} · {readable(event.entity)} · {readable(event.status)}</p>{event.details?.note && <blockquote>{event.details.note}</blockquote>}{event.details?.requested_information?.length > 0 && <small>Requested: {event.details.requested_information.join(" · ")}</small>}</div><time>{formatDateTime(event.timestamp)}</time><button onClick={() => { const row = applications.find(item => item.application_id === event.application_id); if (row) openCase(row); }}>Open case →</button></article>)}</div> : <EmptyState title="No audit events yet" message="Opening cases and recording workflow actions will create a traceable activity history." />}
        </section>}

        <footer className="lender-footer"><span>PRISM outputs are experimental decision-support information. They are not a credit bureau score or automated lending decision.</span><span>{lenderSession?.phone_number || "Authenticated lender"}</span></footer>
      </main>
    </div>
  </div>;
}

function ApplicationTable({ rows, onOpen, selectedId }) {
  return <div className="lender-table-wrap"><table className="lender-table"><thead><tr><th>Application</th><th>Borrower</th><th>Workflow</th><th>Bank index</th><th>Credit research</th><th>Documents</th><th>Fraud checks</th><th /></tr></thead><tbody>{rows.map(row => <tr key={row.application_id} className={selectedId === row.application_id ? "selected" : ""} onClick={() => onOpen(row)} tabIndex={0} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpen(row); } }}>
    <td><strong>APP-{row.application_id}</strong><small>{formatDate(row.application_date)}</small></td><td><span>{maskedPhone(row.borrower_phone)}</span></td><td><StatusPill status={statusOf(row)} />{row.review?.assigned_to && <small className="lender-assignee">Assigned · {maskedPhone(row.review.assigned_to)}</small>}</td><td>{scoreAvailable(row.bank_health_index) ? <strong className="lender-table-score">{Number(row.bank_health_index).toFixed(0)}</strong> : <span className="lender-muted-copy">Not available</span>}{row.bank_assessment_status && <small>{readable(row.bank_assessment_status)}</small>}</td><td>{scoreAvailable(row.risk_score) ? <><strong>{Number(row.risk_score).toFixed(1)}</strong><small>Experimental research</small></> : <span className="lender-muted-copy">Not available</span>}</td><td>{row.document_count ?? 0}</td><td>{row.bank_fraud_flag_count > 0 ? <span className="lender-flag-count">{row.bank_fraud_flag_count} signal{row.bank_fraud_flag_count === 1 ? "" : "s"}</span> : row.bank_fraud_status ? <span className="lender-clear-count">No rules flagged</span> : <span className="lender-muted-copy">Not run</span>}</td><td><button className="lender-row-open" tabIndex={-1} aria-label={`Open application ${row.application_id}`}>Review →</button></td>
  </tr>)}</tbody></table></div>;
}

function Scorecard({ title, score, status, model, detail, description }) {
  return <article className="lender-scorecard"><div><span className="lender-scorecard-label">{title}</span><StatusPill status={status === "SCORED" || status === "EXPERIMENTAL_SHADOW_SCORE" ? "COMPLETED" : status || "NEW"} /></div><strong className="lender-score-value">{scoreAvailable(score) ? Number(score).toFixed(0) : "—"}</strong><small>{detail}</small><p>{description}</p>{model && <span className="lender-model-version">{model}</span>}</article>;
}

function CaseHeader({ detail, assignedToMe }) {
  const application = detail.application || {};
  return <div className="lender-case-header"><div><span className="lender-eyebrow">CASE FILE</span><h2>Application {detail.application_id}</h2><p>{maskedPhone(application.borrower_phone)} · Submitted {formatDate(application.application_date)}</p></div><div className="lender-case-header-meta"><StatusPill status={detail.review?.review_status || "NEW"} />{assignedToMe && <span className="lender-assigned-chip">Assigned to me</span>}</div></div>;
}

function CaseActions({ detail, currentLender, statusDraft, setStatusDraft, noteDraft, setNoteDraft, requestDraft, setRequestDraft, saving, onAction }) {
  return <section className="lender-detail-section lender-actions-section"><div className="lender-section-title"><span>REVIEW WORKFLOW</span><h3>Case actions</h3><p>Actions are recorded in PRISM’s audit trail. Information requests are recorded for the case; PRISM does not contact the borrower.</p></div>
    <div className="lender-action-top"><button className="lender-primary-button" disabled={saving || detail.review?.assigned_to === currentLender?.phone_number} onClick={() => onAction({ action: "assign_to_me" })}>{detail.review?.assigned_to ? detail.review.assigned_to === currentLender?.phone_number ? "Assigned to me" : `Reassign from ${maskedPhone(detail.review.assigned_to)}` : "Assign to me"}</button><label>Status<select value={statusDraft} onChange={event => setStatusDraft(event.target.value)}>{Object.entries(statusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><button className="lender-secondary-button" disabled={saving || statusDraft === detail.review?.review_status} onClick={() => onAction({ action: "set_status", review_status: statusDraft })}>{saving ? "Saving…" : "Update status"}</button></div>
    <div className="lender-action-grid"><form onSubmit={event => { event.preventDefault(); onAction({ action: "add_note", note: noteDraft }); }}><label htmlFor="lender-review-note">Reviewer note</label><textarea id="lender-review-note" value={noteDraft} onChange={event => setNoteDraft(event.target.value)} maxLength={4000} placeholder="Record a concise, evidence-based review note"/><small>{noteDraft.length}/4000 characters · Stored in audit history</small><button className="lender-secondary-button" disabled={saving || !noteDraft.trim()}>Save note</button></form><form onSubmit={event => { event.preventDefault(); onAction({ action: "request_information", requested_information: requestDraft.split(/\n|,/).map(item => item.trim()).filter(Boolean) }); }}><label htmlFor="lender-information-request">Information needed</label><textarea id="lender-information-request" value={requestDraft} onChange={event => setRequestDraft(event.target.value)} placeholder="One item per line, for example: statement page 2"/><small>Recording a request changes the case to Awaiting documents.</small><button className="lender-secondary-button" disabled={saving || !requestDraft.trim()}>Record information request</button></form></div>
  </section>;
}

function ReviewTimeline({ events }) {
  return <section className="lender-detail-section lender-timeline"><div className="lender-section-title"><span>APPLICATION AUDIT HISTORY</span><h3>What happened and when</h3></div>{events.length ? <div className="lender-timeline-list">{events.map(event => <article key={event.event_id}><i /><div><strong>{readable(event.action)}</strong><p>{event.note || (event.requested_information?.length ? `Information requested: ${event.requested_information.join(" · ")}` : event.review_status ? `Status set to ${statusLabels[event.review_status] || readable(event.review_status)}` : "Application evidence opened for review.")}</p><small>{formatDateTime(event.timestamp)} · {maskedPhone(event.performed_by)}</small></div></article>)}</div> : <p className="lender-muted-copy">No lender review actions have been recorded for this case yet.</p>}</section>;
}
