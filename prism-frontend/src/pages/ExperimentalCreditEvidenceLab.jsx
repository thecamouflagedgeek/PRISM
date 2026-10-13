import { useState } from "react";
import { API_BASE_URL } from "../api";
import "./ExperimentalCreditEvidenceLab.css";

const reasonLabels = {
  recent_delinquency_level: "Recent repayment delinquency",
  months_with_delinquency: "Repeated repayment delinquency",
  payment_to_statement_ratio: "Payment relative to statement balances",
  mean_statement_balance: "Average statement balance",
};

function downloadAssessmentPdf(result, trace, simulation) {
  const rows = [
    "PRISM SYNTHETIC DEMONSTRATION ASSESSMENT",
    "Experimental shadow scorecard - NOT FOR CREDIT DECISIONS",
    `Assessment reference: ${result.evidence?.account_reference || result.trace_id || "Synthetic example"}`,
    `Generated: ${new Date().toISOString()}`,
    `Status: ${result.model_status} | Use: ${result.decision_use}`,
    "",
    "ORIGINAL MODEL OUTPUT",
    `Experimental shadow score: ${Number(result.scorecard.experimental_shadow_score).toFixed(2)}`,
    `Raw uncalibrated PD: ${(Number(result.scorecard.raw_pd) * 100).toFixed(4)}%`,
    `Good:bad odds: ${Number(result.scorecard.good_bad_odds).toFixed(6)}:1`,
    "",
    "FEATURE-LEVEL WO E / LOGISTIC REGRESSION TRACE",
  ];
  for (const [key, value] of Object.entries(trace?.feature_trace || {})) {
    rows.push(`${reasonLabels[key]} | observed ${value.raw_feature_value} | bin ${value.bin_id} | WoE ${Number(value.woe).toFixed(6)} | coefficient ${Number(value.coefficient).toFixed(6)} | logit contribution ${Number(value.contribution).toFixed(6)}`);
  }
  rows.push("", "ADVERSE REASON CODES (positive coefficient x WoE contributions)");
  for (const reason of result.reason_codes || []) rows.push(`${reason.label}: ${Number(reason.contribution).toFixed(6)} contribution to default log-odds.`);
  rows.push("", "MODEL-LINKED GUIDANCE");
  for (const reason of result.reason_codes || []) rows.push(`${reason.label}: review records and consider consistent on-time repayments. Guidance is not causal and does not guarantee improvement.`);
  rows.push("", "DOCUMENT / FRAUD REVIEW", "This synthetic structured-evidence example includes no uploaded files. Document authenticity and independent fraud checks were not run; no fraud conclusion is available.");
  if (simulation) {
    rows.push("", "HYPOTHETICAL WHAT-IF - SEPARATE FROM ORIGINAL", `Scenario score ${Number(simulation.scenario.scorecard.experimental_shadow_score).toFixed(2)}; change ${Number(simulation.delta.score).toFixed(2)} points.`, `Scenario raw PD ${(Number(simulation.scenario.scorecard.raw_pd) * 100).toFixed(4)}%; change ${(Number(simulation.delta.raw_pd) * 100).toFixed(4)} percentage points.`, "Hypothetical output only; it does not overwrite the original assessment.");
  }
  rows.push("", "MODEL TRANSPARENCY", "WoE + Logistic Regression; frozen Phase 2B.6/2F artifact; six-month Phase 2E evidence path. Four features only. Score formula: 600 + (50 / ln 2) x ln(((1 - PD) / PD) / 20).", "UCI Taiwan held-out metrics: AUC .75786; Gini .51573; KS .42672; Brier .13814; calibration slope 1.00305; intercept .00426.", "Metrics describe the UCI test sample, not Indian borrowers. Model not independently validated for Indian lending; not a bureau score, risk tier, RBI-approved system, or lending decision.", "RBI governance and source links are available in the dashboard Governance tab.");
  const ascii = (value) => String(value).normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^\x20-\x7E]/g, "?");
  const wrapped = rows.flatMap((line) => {
    const text = ascii(line);
    if (!text) return [""];
    const parts = [];
    for (let i = 0; i < text.length; i += 92) parts.push(text.slice(i, i + 92));
    return parts;
  });
  const pageLines = 50;
  const pages = [];
  for (let i = 0; i < wrapped.length; i += pageLines) pages.push(wrapped.slice(i, i + pageLines));
  const objects = [];
  const pageRefs = pages.map((_, i) => `${3 + i * 2} 0 R`).join(" ");
  const fontId = 3 + pages.length * 2;
  objects[1] = "<< /Type /Catalog /Pages 2 0 R >>";
  objects[2] = `<< /Type /Pages /Kids [${pageRefs}] /Count ${pages.length} >>`;
  pages.forEach((lines, i) => {
    const pageId = 3 + i * 2;
    const streamId = pageId + 1;
    const commands = ["BT", "/F1 9 Tf", "48 790 Td", "12 TL", ...lines.map((line) => `(${line.replace(/[\\()]/g, "\\$&")}) Tj T*`), "ET"].join("\n");
    objects[pageId] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 ${fontId} 0 R >> >> /Contents ${streamId} 0 R >>`;
    objects[streamId] = `<< /Length ${commands.length} >>\nstream\n${commands}\nendstream`;
  });
  objects[fontId] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>";
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  for (let i = 1; i < objects.length; i++) { offsets[i] = pdf.length; pdf += `${i} 0 obj\n${objects[i]}\nendobj\n`; }
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length}\n0000000000 65535 f \n`;
  for (let i = 1; i < objects.length; i++) pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  const link = document.createElement("a");
  const objectUrl = URL.createObjectURL(new Blob([pdf], { type: "application/pdf" }));
  link.href = objectUrl;
  link.download = "prism-synthetic-assessment.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

export default function ExperimentalCreditEvidenceLab() {
  const [request, setRequest] = useState(null);
  const [result, setResult] = useState(null);
  const [trace, setTrace] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [scenarioFeatures, setScenarioFeatures] = useState(null);
  const [simulation, setSimulation] = useState(null);
  const [activePanel, setActivePanel] = useState("overview");

  async function runExample() {
    setBusy(true); setError(""); setResult(null); setTrace(null);
    try {
      const fixtureResponse = await fetch(`${API_BASE_URL}/experimental/shadow-golden-request`);
      if (!fixtureResponse.ok) {
        const body = await fixtureResponse.json().catch(() => ({}));
        throw new Error(body.detail?.code || "GOLDEN_FIXTURE_UNAVAILABLE");
      }
      const body = await fixtureResponse.json();
      setRequest(body);
      const response = await fetch(`${API_BASE_URL}/experimental/shadow-assess`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail?.code || "SHADOW_REQUEST_FAILED");
      setResult(payload);
      if (payload.status === "EXPERIMENTAL_SHADOW_SCORE") {
        const traceResponse = await fetch(`${API_BASE_URL}/experimental/shadow-assess/debug`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        const tracePayload = await traceResponse.json();
        if (traceResponse.ok && tracePayload.trace) setTrace(tracePayload.trace);
        setScenarioFeatures(payload.features);
        setSimulation(null);
      }
    } catch (err) {
      setError(err.message || "The experimental service could not be reached.");
    } finally { setBusy(false); }
  }

  async function runSimulation() {
    if (!result?.features || !scenarioFeatures) return;
    setBusy(true); setError(""); setSimulation(null);
    try {
      const response = await fetch(`${API_BASE_URL}/experimental/shadow-simulate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ baseline: result.features, scenario: scenarioFeatures }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail?.message || payload.detail || "Simulation failed");
      setSimulation(payload);
    } catch (err) { setError(String(err.message || "Simulation failed")); }
    finally { setBusy(false); }
  }

  async function inspectTrace() {
    if (!request) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/experimental/shadow-assess/debug`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
      });
      const payload = await response.json();
      if (!response.ok || !payload.trace) throw new Error(payload.detail?.code || "TRACE_UNAVAILABLE");
      setTrace(payload.trace);
    } catch (err) { setError(err.message || "Trace unavailable."); }
    finally { setBusy(false); }
  }

  return (
    <main className="shadow-lab">
      <header className="shadow-lab__header">
        <a className="shadow-lab__back" href="/">← PRISM</a>
        <span className="shadow-lab__badge">EXPERIMENTAL · NON-PRODUCTION</span>
        <h1>PRISM Experimental Credit Evidence Lab</h1>
        <p>Shadow scoring demonstration — not for credit decisions.</p>
      </header>

      <section className="shadow-lab__notice" role="note">
        This research demo accepts controlled structured credit-card evidence and explicit repayment history.
        It does not support arbitrary PDFs, OCR, bureau APIs, approvals, or lending decisions. The model is not externally validated.
      </section>

      <section className="shadow-lab__panel">
        <div>
          <p className="shadow-lab__eyebrow">GOLDEN DEMO · SYNTHETIC FIXTURE</p>
          <h2>Run the verified example</h2>
          <p>Loads the existing six-month Phase 2E fixture and sends evidence through validation, frozen features, and the Phase 2F shadow scorecard.</p>
        </div>
        <button className="shadow-lab__button" onClick={runExample} disabled={busy}>
          {busy ? "Processing…" : "Run Verified Example"}
        </button>
      </section>

      {error && <div className="shadow-lab__error" role="alert">{error === "EXPERIMENTAL_FEATURE_DISABLED" ?
        "The experimental API is disabled. Enable it explicitly on the backend to run this demo." : error}</div>}

      {result && <>
        <div className="shadow-lab__steps" aria-label="Evidence processing stages">
          {["Evidence", "Validation", "Behavioral features", "Experimental risk estimate", "Explanation"].map((step, i) =>
            <div className="shadow-lab__step" key={step}><span>{i + 1}</span>{step}</div>)}
        </div>

        {!result.eligibility.eligible ? <section className="shadow-lab__panel shadow-lab__blocked" role="status">
          <h2>Evidence is not eligible for shadow scoring</h2>
          <ul>{result.eligibility.blocking_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
          <p>No PD, score, or reason codes were generated.</p>
        </section> : <>
          <nav className="shadow-lab__tabs" aria-label="Assessment dashboard sections">
            {["overview", "explain", "simulate", "guidance", "governance"].map((tab) => <button key={tab} aria-pressed={activePanel === tab} onClick={() => setActivePanel(tab)}>{({ overview: "Overview", explain: "Explainability", simulate: "What-if", guidance: "Guidance", governance: "Governance" })[tab]}</button>)}
            <button onClick={() => downloadAssessmentPdf(result, trace, simulation)} className="shadow-lab__print">Download assessment PDF</button>
          </nav>
          {activePanel === "overview" && <>
          <section className="shadow-lab__grid">
            <article className="shadow-lab__panel">
              <p className="shadow-lab__eyebrow">01 · EVIDENCE & VALIDATION</p>
              <h2>Validated account history</h2>
              <dl>
                <dt>Account reference</dt><dd>{result.evidence.account_reference}</dd>
                <dt>Provider</dt><dd>{result.evidence.provider}</dd>
                <dt>Product</dt><dd>{result.evidence.product_type}</dd>
                <dt>Observation window</dt><dd>{result.evidence.months_validated} complete months through {result.evidence.prediction_cutoff}</dd>
                <dt>Repayment history</dt><dd>{result.evidence.repayment_history_source_available ? "Explicit source linked" : "Not supplied"}</dd>
                <dt>Consent</dt><dd>Granted for required evidence scopes</dd>
                <dt>Eligibility</dt><dd>{result.eligibility.eligible ? "Eligible for experimental scoring" : "Ineligible"}</dd>
              </dl>
            </article>
            <article className="shadow-lab__panel">
              <p className="shadow-lab__eyebrow">02 · BEHAVIORAL FEATURES</p>
              <h2>Four frozen variables</h2>
              <dl>
                {Object.entries(result.features).map(([key, value]) => <div className="shadow-lab__feature" key={key}>
                  <dt>{reasonLabels[key] || key.replaceAll("_", " ")}</dt>
                  <dd>{key === "payment_to_statement_ratio" ? Number(value).toFixed(2) :
                    key === "mean_statement_balance" ? Number(value).toFixed(2) : value}</dd>
                </div>)}
              </dl>
            </article>
          </section>
          </>}

          {activePanel === "overview" && <section className="shadow-lab__result shadow-lab__panel">
            <p className="shadow-lab__eyebrow">03 · EXPERIMENTAL RISK ESTIMATE</p>
            <div className="shadow-lab__metrics">
              <div><span>Experimental Default Probability</span><strong>{(result.scorecard.raw_pd * 100).toFixed(2)}%</strong><small>Raw Phase 2B.6 LR PD</small></div>
              <div><span>Experimental Shadow Score</span><strong>{result.scorecard.experimental_shadow_score.toFixed(2)}</strong><small>PDO presentation only · Base 600 · PDO 50 · Base odds 20:1</small></div>
              <div><span>Good:bad odds</span><strong>{result.scorecard.good_bad_odds.toFixed(4)}:1</strong><small>Experimental probability transform</small></div>
            </div>
            <p className="shadow-lab__disclaimer">The shadow score is a presentation scale, not a model-trained, validated, or production credit score. No risk tier or lending decision is produced.</p>
          </section>}

          {activePanel === "explain" && <section className="shadow-lab__panel">
            <p className="shadow-lab__eyebrow">04 · CONTRIBUTION-BASED EXPLANATION</p>
            <h2>Factors increasing estimated default risk</h2>
            {result.reason_codes.length ? <ol className="shadow-lab__reasons">
              {result.reason_codes.map((reason) => <li key={reason.code}><span>{reason.label}</span><strong>+{reason.contribution.toFixed(4)}</strong></li>)}
            </ol> : <p>No adverse contribution reasons were returned.</p>}
            <button className="shadow-lab__text-button" onClick={inspectTrace} disabled={busy}>Inspect calculation trace</button>
            <small>These are coefficient × WoE contributions, not SHAP values.</small>
            {trace && <pre className="shadow-lab__trace">{JSON.stringify({
              trace_id: result.trace_id, feature_trace: trace.feature_trace,
              intercept: trace.intercept, contributions: trace.feature_contributions,
              logit: trace.logit, raw_pd: trace.pd, good_bad_odds: trace.good_bad_odds,
              experimental_shadow_score: trace.score,
            }, null, 2)}</pre>}
          </section>}
          {activePanel === "simulate" && <section className="shadow-lab__panel">
            <p className="shadow-lab__eyebrow">HYPOTHETICAL · DOES NOT CHANGE THE BASELINE ASSESSMENT</p><h2>What-if simulation</h2>
            <p>Adjust the four frozen features. Each comparison runs the same frozen WoE and Logistic Regression inference at the backend.</p>
            <div className="shadow-lab__sim-grid">{Object.entries(result.features).map(([key, base]) => <label key={key}>{reasonLabels[key]}<input type="number" step={key.includes("ratio") || key.includes("balance") ? "any" : "1"} value={scenarioFeatures?.[key] ?? base} onChange={(e) => setScenarioFeatures((prev) => ({ ...prev, [key]: Number(e.target.value) }))} /></label>)}</div>
            <div className="shadow-lab__sim-actions"><button className="shadow-lab__button" disabled={busy} onClick={() => { setScenarioFeatures(result.features); setSimulation(null); }}>Reset</button><button className="shadow-lab__button" disabled={busy} onClick={runSimulation}>{busy ? "Calculating…" : "Compare scenario"}</button></div>
            {simulation && <div className="shadow-lab__metrics"><div><span>Baseline score</span><strong>{simulation.baseline.scorecard.experimental_shadow_score.toFixed(1)}</strong><small>Scenario {simulation.scenario.scorecard.experimental_shadow_score.toFixed(1)} · Δ {simulation.delta.score >= 0 ? "+" : ""}{simulation.delta.score.toFixed(1)}</small></div><div><span>Baseline raw PD</span><strong>{(simulation.baseline.scorecard.raw_pd * 100).toFixed(2)}%</strong><small>Scenario {(simulation.scenario.scorecard.raw_pd * 100).toFixed(2)}% · Δ {(simulation.delta.raw_pd * 100).toFixed(2)} pp</small></div></div>}
            {simulation && <><h3>Scenario explanation</h3><div className="shadow-lab__table-wrap"><table><thead><tr><th>Feature</th><th>Baseline bin</th><th>Scenario bin</th><th>Contribution Δ</th></tr></thead><tbody>{Object.keys(result.features).map((key) => <tr key={key}><td>{reasonLabels[key]}</td><td>{simulation.baseline.feature_trace[key].bin_id}</td><td>{simulation.scenario.feature_trace[key].bin_id}</td><td>{(simulation.scenario.feature_contributions[key] - simulation.baseline.feature_contributions[key]).toFixed(5)}</td></tr>)}</tbody></table></div><h3>Updated adverse reason codes</h3>{simulation.scenario.reason_codes.length ? <ul>{simulation.scenario.reason_codes.map((reason) => <li key={reason.code}>{reason.label} · contribution {Number(reason.contribution).toFixed(5)} to default log-odds</li>)}</ul> : <p>No positive adverse contributions in the scenario.</p>}</>}
            <p className="shadow-lab__disclaimer">What-if scenarios are hypothetical model outputs, not guaranteed future credit scores or lending decisions.</p>
          </section>}
          {activePanel === "guidance" && <section className="shadow-lab__panel"><p className="shadow-lab__eyebrow">MODEL-LINKED, NON-CAUSAL SUGGESTIONS</p><h2>Profile improvement guidance</h2>{result.reason_codes.length ? <ul>{result.reason_codes.map((reason) => <li key={reason.code}><strong>{reason.label}:</strong> {({ recent_delinquency_level: "Review recent repayment records and aim to make upcoming payments on time.", months_with_delinquency: "Build a consistent on-time repayment history across future statement cycles.", payment_to_statement_ratio: "Where affordable, pay a larger share of statement balances by the due date.", mean_statement_balance: "Review outstanding statement balances and repay amounts that are manageable." })[reason.code]} This reflects model association, not a guaranteed or causal score improvement.</li>)}</ul> : <p>The model returned no positive adverse contributions in this scenario.</p>}<h3>Document and fraud review</h3><p>This synthetic structured-evidence scenario has no uploaded files. Document authenticity and independent fraud checks were not run. No fraud conclusion is available.</p><p>Account evidence source records: {(trace?.source_records || []).join(", ") || "see validated synthetic evidence"}</p></section>}
          {activePanel === "governance" && <section className="shadow-lab__panel"><p className="shadow-lab__eyebrow">REVIEWED 9 OCTOBER 2026 · NOT A COMPLIANCE ATTESTATION</p><h2>Regulatory Governance & Responsible Lending</h2><p>Applicability depends on whether a regulated entity and/or its lending service provider performs digital lending functions. PRISM is an experimental prototype, is not RBI approved, and is not independently validated for Indian lending decisions.</p><ul><li><strong>Digital lending safeguards — Partially implemented in the demonstration:</strong> consent scopes and demo audit events exist; regulated-entity disclosures, grievance operations and complete production controls are not established. RBI’s <a href="https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=1436" target="_blank" rel="noreferrer">2024–25 Annual Report</a> records issuance of the Digital Lending Directions, 2025; RBI’s <a href="https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12382" target="_blank" rel="noreferrer">2022 Guidelines on Digital Lending</a> page points readers to the 2025 Directions.</li><li><strong>Credit information reporting — Planned:</strong> this prototype does not furnish or correct credit information with CICs. The same <a href="https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=1436" target="_blank" rel="noreferrer">RBI Annual Report</a> records the Credit Information Reporting Master Direction issued January 6, 2025.</li><li><strong>Consent and purpose limitation — Partially implemented:</strong> experimental consent scopes are explicit; production retention, deletion and data-rights workflows are incomplete.</li><li><strong>Human oversight and grievance redress — Planned:</strong> no operational appeals or staffed grievance service is included.</li><li><strong>Audit and monitoring — Partially implemented:</strong> the controlled demo records events; production monitoring and independent model validation are not implemented.</li></ul><h3>Frozen held-out UCI evaluation</h3><p>AUC 0.75786 · Gini 0.51573 · KS 0.42672 · Brier 0.13814 · Calibration slope 1.00305 · Intercept 0.00426. These describe the frozen UCI held-out evaluation only.</p><h3>Training data and frozen feature definitions</h3><p>Development on the UCI Taiwan 30,000-account credit-card default dataset. These definitions are in the original model feature contract; currency is not assumed to be INR.</p><ul><li><code>recent_delinquency_level</code>: latest observed monthly repayment delinquency level from the six-month history.</li><li><code>months_with_delinquency</code>: count of months with a positive delinquency level in that history.</li><li><code>payment_to_statement_ratio</code>: total payments divided by the sum of non-negative statement balances over the six-month window.</li><li><code>mean_statement_balance</code>: arithmetic mean of the six signed statement balances.</li></ul><p>Score = 600 + (50 / ln 2) × ln(((1 − PD) / PD) / 20). This presentation scale is not a credit-bureau score, lending tier, or decision.</p><p>Official RBI materials reviewed on 9 October 2026. Applicability requires review by the regulated lender and counsel.</p></section>}
          <footer className="shadow-lab__footer">{result.model_status} · NOT EXTERNALLY VALIDATED · NOT CURRENT-MARKET VALIDATED · NOT PRODUCTION APPROVED</footer>
        </>}
      </>}
    </main>
  );
}
