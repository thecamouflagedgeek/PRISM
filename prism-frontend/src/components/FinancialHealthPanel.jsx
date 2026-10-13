const money = (value) => value == null ? "—" : Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });

export default function FinancialHealthPanel({ data }) {
  if (!data || data.status !== "AVAILABLE") return null;
  return <section aria-label="Bank statement financial health" style={{ marginTop: 24, padding: 22, border: "1px solid #CBD5E1", borderRadius: 14, background: "#F8FAFC" }}>
    <div style={{ color: "#0F766E", fontSize: 12, fontWeight: 700, letterSpacing: ".07em" }}>BANK STATEMENT · FINANCIAL HEALTH</div>
    <h2 style={{ margin: "8px 0", color: "#172554" }}>Observed cash-flow summary</h2>
    <p style={{ marginTop: 0, color: "#475569", fontSize: 13 }}>Separate supporting analysis. These indicators do not contribute to the frozen credit-card PD or represent lending thresholds.</p>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
      <Metric label="Months observed" value={data.months_observed} />
      <Metric label="Transactions" value={data.transaction_count} />
      <Metric label="Average observed balance" value={money(data.average_observed_closing_balance)} />
      <Metric label="Cash-flow variability¹" value={data.cash_flow_variability == null ? "—" : Number(data.cash_flow_variability).toFixed(3)} />
      <Metric label="Possible debt-payment matches" value={data.possible_debt_payments?.matching_transaction_count ?? 0} />
      <Metric label="Explicit returned-payment matches" value={data.explicit_returned_payment_indicators?.matching_transaction_count ?? 0} />
      <Metric label="Salary-labelled credit months" value={data.salary_labelled_credits?.months ?? 0} />
      <Metric label="Recurring debit patterns" value={data.recurring_obligation_patterns?.pattern_count ?? 0} />
    </div>
    <div style={{ overflowX: "auto", marginTop: 16 }}><table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead><tr>{["Month", "Income", "Expenses", "Net flow"].map((label) => <th key={label} style={{ textAlign: "left", padding: 8, borderBottom: "1px solid #CBD5E1" }}>{label}</th>)}</tr></thead>
      <tbody>{(data.monthly || []).map((month) => <tr key={month.month}>{[month.month, money(month.income_total), money(month.expense_total), money(month.net_flow)].map((value, index) => <td key={index} style={{ padding: 8, borderBottom: "1px solid #E2E8F0" }}>{value}</td>)}</tr>)}</tbody>
    </table></div>
    <small style={{ display: "block", marginTop: 10, color: "#64748B" }}>¹ Sample standard deviation of monthly net flow divided by mean absolute monthly net flow. “Possible” and “labelled” indicators are keyword-based leads, not verified income or obligations.</small>
  </section>;
}

function Metric({ label, value }) {
  return <div style={{ padding: 12, background: "white", borderRadius: 10, border: "1px solid #E2E8F0" }}><div style={{ color: "#64748B", fontSize: 11 }}>{label}</div><strong style={{ display: "block", marginTop: 5, color: "#0F172A" }}>{value ?? "—"}</strong></div>;
}
