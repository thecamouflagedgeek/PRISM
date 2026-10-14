import { useEffect, useState } from 'react';
import { api } from '../services/api';

export default function PortfolioSentimentStatus({ sessionId }) {
  const [state, setState] = useState({ loading: true, data: null, error: '' });
  useEffect(() => {
    let active = true;
    api.lenderPortfolioSentiment(sessionId)
      .then(data => active && setState({ loading: false, data, error: '' }))
      .catch(error => active && setState({ loading: false, data: null, error: error.message || 'Status unavailable.' }));
    return () => { active = false; };
  }, [sessionId]);
  return <article className="lender-card">
    <div className="lender-card-heading"><div><span className="lender-eyebrow">EXPERIMENTAL TEXT ANALYSIS</span><h2>Portfolio sentiment</h2></div></div>
    {state.loading ? <p role="status">Checking feature availability…</p> : state.error ? <p role="alert">{state.error}</p> : <>
      <strong>{state.data.status}</strong><p>{state.data.reason}</p>
      <p>Sentiment tone is not a credit-risk or default-probability estimate. No portfolio score is available.</p>
      <details><summary>Validation required</summary><ul>{state.data.required_before_enablement.map(item => <li key={item}>{item}</li>)}</ul><ul>{state.data.limitations.map(item => <li key={item}>{item}</li>)}</ul></details>
    </>}
  </article>;
}
