import { useState } from 'react';
import { api } from '../services/api';

const EMPTY = { principal: '', annual_interest_rate_percent: '', fees: '', monthly_income: '',
  monthly_expenses: '', existing_monthly_obligations: '', max_debt_to_income_ratio: '', tenures_months: '' };
const LABELS = {
  principal: 'Principal', annual_interest_rate_percent: 'Nominal annual interest rate (%)', fees: 'One-time fees',
  monthly_income: 'Monthly net income', monthly_expenses: 'Monthly expenses excluding debt payments',
  existing_monthly_obligations: 'Existing monthly debt obligations',
  max_debt_to_income_ratio: 'Your maximum total debt-to-income ratio (0–1)',
};
const money = value => Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 });

export default function RepaymentTenureComparison({ applicationId, assessmentId, session, viewerMode = false }) {
  const [values, setValues] = useState(EMPTY);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true); setError(''); setResult(null);
    try {
      const payload = Object.fromEntries(Object.entries(values).filter(([key]) => key !== 'tenures_months')
        .map(([key, value]) => [key, Number(value)]));
      payload.tenures_months = values.tenures_months.split(',').map(value => Number(value.trim()));
      const response = viewerMode
        ? await api.lenderTenureComparison(applicationId, payload, session?.session_id)
        : await api.borrowerTenureComparison(payload, session?.session_id);
      setResult(response);
    } catch (requestError) { setError(requestError.message || 'Comparison unavailable.'); }
    finally { setBusy(false); }
  };
  return <section className="assessment-panel repayment-tenure-comparison" aria-label="Repayment tenure comparison">
    <div className="assessment-eyebrow">Hypothetical planning · no saved changes</div>
    <h2>Compare repayment tenures</h2>
    <p>Enter and verify every value. PRISM does not fill missing loan terms or affordability inputs from a score or transaction keyword.</p>
    <div className="assessment-form-grid">{Object.entries(LABELS).map(([key, label]) => <label key={key}>{label}
      <input type="number" min="0" step="any" required value={values[key]} onChange={event => setValues(current => ({ ...current, [key]: event.target.value }))}/>
    </label>)}<label>Compare tenures in months (comma separated)
      <input inputMode="numeric" required value={values.tenures_months} placeholder="Enter offered terms" onChange={event => setValues(current => ({ ...current, tenures_months: event.target.value }))}/>
    </label></div>
    <p>Interest convention: nominal annual rate divided by 12, fixed monthly reducing balance, payments at month end. Fees are one-time and entered separately. The debt-to-income limit is supplied by you and is not PRISM policy.</p>
    <button className="btn-outline" disabled={busy || !session?.session_id || (!viewerMode && !assessmentId) || (viewerMode && !applicationId)} onClick={submit}>{busy ? 'Comparing…' : 'Compare supplied terms'}</button>
    {error && <p role="alert">{error}</p>}
    {result && <div className="simulation-result"><h3>{result.recommendation ? `Lowest-cost eligible term: ${result.recommendation.tenure_months} months` : 'No supplied term meets the supplied constraints'}</h3>
      {result.recommendation && <p>{result.recommendation.reason}</p>}
      <div className="assessment-table-wrap"><table className="assessment-table"><thead><tr><th>Months</th><th>Monthly installment</th><th>Total interest</th><th>Fees</th><th>Total repayment + fees</th><th>Debt / income</th><th>Residual after expenses</th><th>Eligible</th></tr></thead>
        <tbody>{result.comparisons.map(item => <tr key={item.tenure_months}><td>{item.tenure_months}</td><td>{money(item.monthly_installment)}</td><td>{money(item.total_interest)}</td><td>{money(item.fees)}</td><td>{money(item.total_cost_including_fees)}</td><td>{(item.monthly_debt_to_income_ratio * 100).toFixed(1)}%</td><td>{money(item.monthly_residual_after_expenses_and_debt)}</td><td>{item.affordable_under_supplied_constraints ? 'Yes' : 'No'}</td></tr>)}</tbody>
      </table></div><small>Input assumptions are not independently verified. This is not a lending recommendation. Assessment reference: {result.assessment_id || assessmentId}</small>
    </div>}
  </section>;
}
