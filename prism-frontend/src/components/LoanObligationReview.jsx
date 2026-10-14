export default function LoanObligationReview({ data }) {
  if (!data) return null;
  const streams = data.candidate_payment_streams || [];
  const overlaps = data.overlapping_months || {};
  return <section className="assessment-panel loan-obligation-review" aria-label="Loan obligation review">
    <div className="assessment-eyebrow">Observed transaction signal · human review only</div>
    <h2>Recurring loan-like payments</h2>
    <p><strong>{String(data.status || "INSUFFICIENT_EVIDENCE").replaceAll("_", " ")}</strong> · {data.observed_signal}</p>
    <p>Confirmed loan stacking: no. This review is not a score or lending decision; no calibrated confidence is available.</p>
    {data.status === "NOT_AVAILABLE" ? <p>{data.observed_signal}</p> : streams.length ? streams.map((stream) => <article className="action-step" key={stream.candidate_id}>
      <h3>Candidate stream {stream.candidate_id}</h3>
      <p>{stream.reference_type === "EXPLICIT_LOAN_OR_MANDATE_REFERENCE" ? `Masked reference ${stream.masked_reference}` : "Grouped by normalized narration only; no verified account reference."}</p>
      <p>Observed months: {stream.months_observed.join(", ")}{stream.missing_months.length ? ` · gaps: ${stream.missing_months.join(", ")}` : ""}</p>
      <p>Monthly amounts: {Object.entries(stream.monthly_amounts).map(([month, amount]) => `${month}: ${Number(amount).toLocaleString()}`).join(" · ")}</p>
      <p>Timing review: {stream.timing_pattern.replaceAll("_", " ")} · observed day span {stream.day_of_month_span} days.</p>
      <p>Stable under the uncalibrated 20% review rule: {stream.monthly_amount_stable_under_20pct_rule ? "yes" : "no"}. This is a screening rule, not a confidence estimate.</p>
      <small>{stream.uncertainty}</small>
      <details><summary>Source transaction locations</summary><ul>{stream.source_transaction_ids.map(id => <li key={id}>{id}</li>)}</ul></details>
    </article>) : <p>No recurring candidate stream could be established from the available records.</p>}
    {!streams.length && data.raw_candidate_transactions?.length > 0 && <details><summary>Loan-like debit rows not grouped as recurring streams</summary><ul>{data.raw_candidate_transactions.map((item, index) => <li key={`${item.source_transaction_id}-${index}`}>{item.source_transaction_id} · {item.month} · {Number(item.amount).toLocaleString()} · {item.review_reason}</li>)}</ul><p>These rows are not grouped into recurring streams because evidence across multiple months and a stable signature are required.</p></details>}
    <h3>Overlapping periods</h3>
    {Object.keys(overlaps).length ? Object.entries(overlaps).map(([month, ids]) => <p key={month}>{month}: {ids.join(", ")}</p>) : <p>No multiple candidate streams overlap in the observed months.</p>}
    <details><summary>Coverage, exclusions, and limitations</summary>
      <p>Transaction months: {(data.data_coverage?.transaction_months || []).join(", ") || "Unavailable"}; missing months: {(data.data_coverage?.missing_months || []).join(", ") || "None observed in the available date span"}.</p>
      {!!data.data_coverage?.sufficiency_gaps?.length && <p>Insufficient-evidence reasons: {data.data_coverage.sufficiency_gaps.join(", ")}</p>}
      <pre>{JSON.stringify(data.exclusions || {}, null, 2)}</pre>
      <pre>{JSON.stringify(data.excluded_transaction_ids || {}, null, 2)}</pre>
      <ul>{(data.limitations || []).map(item => <li key={item}>{item}</li>)}</ul>
    </details>
  </section>;
}
