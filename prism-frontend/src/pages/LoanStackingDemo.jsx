import { useState } from "react";
import { API_BASE_URL } from "../api";
import "./LoanStackingDemo.css";

const SCENARIOS = [
  ["overlapping-obligations", "Two recurring payment streams overlap"],
  ["single-loan-repayments", "One loan with repeated instalments"],
  ["duplicates-transfers", "Duplicate, reversal, transfer, and card-payment controls"],
  ["insufficient-evidence", "Loan keywords without distinct references"],
];

async function loadScenario(id) {
  const response = await fetch(`${API_BASE_URL}/demo/loan-stacking/${encodeURIComponent(id)}`);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Demo request failed (${response.status}).`);
  return body;
}

export default function LoanStackingDemo() {
  const [selected, setSelected] = useState(SCENARIOS[0][0]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError("");
    try { setResult(await loadScenario(selected)); }
    catch (e) { setResult(null); setError(e.message); }
    finally { setBusy(false); }
  }

  return <main className="p4-shell loan-demo">
    <header className="p4-header"><div><span className="p4-kicker">DEVELOPMENT DEMONSTRATION · SYNTHETIC ONLY</span>
      <h1>Loan obligation overlap</h1>
      <p>Repeated, separately referenced payment streams can indicate possible overlap. They do not prove loan accounts or confirmed stacking.</p></div></header>
    <section className="p4-card">
      <label htmlFor="loan-demo-scenario">Synthetic scenario</label>
      <div className="loan-demo-controls"><select id="loan-demo-scenario" value={selected} onChange={(event) => { setSelected(event.target.value); setResult(null); setError(""); }}>
        {SCENARIOS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select><button className="p4-button" disabled={busy} onClick={run}>{busy ? "Loading…" : "Run synthetic scenario"}</button></div>
      {error && <p className="p4-error" role="alert">{error}</p>}
    </section>
    {result && <>
      <section className="p4-notice"><strong>{result.status.replaceAll("_", " ")}</strong><span>{result.observed_signal}</span>
        <span>Confirmed loan stacking: no. Candidate payment streams require human review.</span></section>
      <section className="p4-card"><h2>Synthetic transaction input</h2>
        <p>Fictional references and amounts; no borrower, lender, or account data is used.</p>
        <div className="p4-table-wrap"><table><thead><tr><th>Date</th><th>Direction</th><th>Amount</th><th>Masked reference</th><th>Description</th><th>Evidence ID</th></tr></thead>
          <tbody>{result.transactions.map((row, index) => <tr key={`${row.transaction_id}-${index}`}><td>{row.date}</td><td>{row.direction}</td><td>{row.amount.toLocaleString()}</td><td>{row.reference || "Unlinked"}</td><td>{row.narration}{row.reversal_of ? ` · reversal of ${row.reversal_of}` : ""}</td><td>{row.transaction_id}</td></tr>)}</tbody></table></div>
        {result.income_evidence && <p>Affordability denominator: {result.income_evidence} · {result.repayment_burden?.monthly_income.toLocaleString() || "unavailable"} per month.</p>}
      </section>
      <section className="p4-card"><h2>Candidate repayment obligations</h2>
        {result.candidate_obligations.length ? result.candidate_obligations.map((item) => <article className="loan-demo-obligation" key={item.candidate_reference}>
          <h3>{item.candidate_reference} · candidate recurring stream</h3><p>{item.grouping_reason}</p><p>Observed months: {item.months_observed.join(", ")} · transactions: {item.transaction_count}</p>
          <p>Monthly amounts: {Object.entries(item.monthly_amounts).map(([month, amount]) => `${month}: ${amount.toLocaleString()}`).join(" · ")}</p>
          <small>{item.uncertainty}</small>
        </article>) : <p>No distinct recurring obligation can be established. Keyword matches alone are insufficient.</p>}
      </section>
      <section className="p4-grid loan-demo-grid">
        <article className="p4-card"><h2>Overlapping periods</h2>
          {Object.keys(result.overlapping_months).length ? Object.entries(result.overlapping_months).map(([month, refs]) => <p key={month}><strong>{month}</strong>: {refs.join(" + ")} · aggregate {result.overlap_monthly_obligations[month].toLocaleString()}</p>) : <p>No month contains multiple candidate recurring streams.</p>}
        </article>
        <article className="p4-card"><h2>Repayment burden</h2>
          {result.repayment_burden ? <><p>{result.repayment_burden.monthly_obligations.toLocaleString()} per month / {result.repayment_burden.monthly_income.toLocaleString()} income</p><strong>{(result.repayment_burden.obligation_to_income_ratio * 100).toFixed(1)}% observed ratio</strong><p>{result.repayment_burden.interpretation}</p></> : <p>Unavailable: recurring obligations or monthly income evidence is insufficient.</p>}
        </article>
      </section>
      <section className="p4-card"><h2>Uncertainty and exclusions</h2>
        <p>{Object.entries(result.excluded_or_uncertain_evidence).map(([name, count]) => `${name.replaceAll("_", " ")}: ${count}`).join(" · ")}</p>
        <ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>
    </>}
    <footer>Demo data is generated in memory, is not persisted, and is never sent to ordinary borrower assessment or lender routes.</footer>
  </main>;
}
