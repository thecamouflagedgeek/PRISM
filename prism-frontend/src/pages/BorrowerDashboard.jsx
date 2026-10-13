import { useEffect, useMemo, useState } from 'react';
import { Nav } from '../components/Nav';
import { api } from '../services/api';
import './BorrowerDashboard.css';

const tabs = [
  ['overview', 'Overview', '▦'], ['monthly', 'Monthly scores', '◷'],
  ['patterns', 'Spending patterns', '⌁'], ['history', 'Upload history', '▤'],
  ['fraud', 'Fraud checks', '◇'], ['whatif', 'What-if simulator', '↗'],
  ['rbi', 'RBI guidance', '◎'], ['knowmore', 'Know more', 'i'],
];
const scenarioFields = [
  ['monthly_income', 'Monthly income', 'Average income from this statement period.'],
  ['monthly_expenses', 'Monthly spending', 'Average spending from this statement period.'],
  ['monthly_debt_obligations', 'Monthly debt payments', 'Optional. Include only identified monthly loan or EMI payments.'],
  ['average_balance', 'Average account balance', 'Average closing balance from the uploaded statement.'],
  ['income_volatility', 'Income variation (0–0.99)', 'Optional. Enter a decimal such as 0.2 for 20% variation.'],
];
const money = (value, currency = 'INR') => value == null ? '—' : new Intl.NumberFormat('en-IN', {
  style: 'currency', currency, maximumFractionDigits: 0,
}).format(Number(value));
const readable = value => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
const dateTime = value => value ? new Date(value).toLocaleString('en-IN', {
  day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
}) : 'Date unavailable';
const monthName = value => value ? new Date(`${value}-01T00:00:00`).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' }) : '—';

export default function BorrowerDashboard({ session, go, setResult, setError, setFiles, setAssessmentInput }) {
  const [active, setActive] = useState('overview');
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(null);
  const [refresh, setRefresh] = useState(0);
  const [scenario, setScenario] = useState({});
  const [simulation, setSimulation] = useState(null);
  const [simulationError, setSimulationError] = useState('');
  const [simulating, setSimulating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!session?.session_id) { go('login'); return undefined; }
    setLoading(true);
    api.borrowerBankHistory(session.session_id).then(value => {
      if (!cancelled) { setDashboard(value); setLoading(false); }
    }).catch(error => {
      if (!cancelled) {
        setLoading(false);
        if (error.status === 401) go('login');
        else if (error.status === 403) go('consent');
        else setError(error.message);
      }
    });
    return () => { cancelled = true; };
  }, [session?.session_id, refresh, go, setError]);

  const bankAssessments = dashboard?.assessments?.filter(item => item.assessment_type === 'BANK_CASHFLOW_EXPERIMENTAL') || [];
  const latest = bankAssessments[0] || null;
  const latestAssessmentId = latest?.assessment_id;
  const latestFinancialMetrics = latest?.financial_metrics;
  useEffect(() => {
    if (!latestAssessmentId) return;
    const metrics = latestFinancialMetrics || {};
    setScenario({
      monthly_income: metrics.average_monthly_income ?? '',
      monthly_expenses: metrics.average_monthly_expenses ?? '',
      monthly_debt_obligations: metrics.identified_monthly_debt_payments ?? '',
      average_balance: metrics.average_observed_closing_balance ?? '',
      income_volatility: metrics.monthly_income_coefficient_of_variation ?? '',
    });
    setSimulation(null);
    setSimulationError('');
  }, [latestAssessmentId, latestFinancialMetrics]);
  const recentActivity = dashboard?.activity?.length ? dashboard.activity.slice(0, 4).map(event => ({
    ...event, assessment: bankAssessments.find(item => item.assessment_id === event.assessment_id),
  })) : dashboard?.assessments?.slice(0, 4).map(item => ({ ...item, checked_at: item.assessment_timestamp, assessment: item })) || [];
  const monthlyScores = dashboard?.monthly_scores || [];
  const currency = latest?.financial_metrics?.currency || latest?.currency || 'INR';
  const maxMonthScore = Math.max(900, ...monthlyScores.map(item => Number(item.score) || 0));
  const highestExpense = useMemo(() => latest?.monthly?.reduce((best, item) =>
    !best || Number(item.expense_total) > Number(best.expense_total) ? item : best, null), [latest]);

  const openAssessment = async item => {
    if (item.assessment_type === 'BANK_CASHFLOW_EXPERIMENTAL') {
      setOpening(item.assessment_id);
      try { setResult(await api.borrowerBankCashflow(session.session_id, item.assessment_id)); go('results'); }
      catch (error) { setError(error.message); }
      finally { setOpening(null); }
    } else if (item.assessment_type === 'CREDIT_ACCOUNT_EXPERIMENTAL') {
      setOpening(item.assessment_id);
      try { setResult(await api.borrowerAssessment(item.assessment_id, session.session_id)); go('results'); }
      catch (error) { setError(error.message); }
      finally { setOpening(null); }
    }
  };

  const recommendations = latest?.recommendations?.length ? latest.recommendations : [
    'Upload a fresh statement when you want to compare a new observation period.',
    'Keep the same account selected so month-to-month cash-flow patterns remain comparable.',
  ];
  const startNewAssessment = () => {
    setFiles({ bankStatements: [], creditCards: [], salary: [], utility: [], bank: null });
    setAssessmentInput(null);
    go('upload');
  };
  const runSimulation = async event => {
    event.preventDefault();
    if (!latest?.assessment_id) return;
    const values = Object.fromEntries(Object.entries(scenario)
      .filter(([, value]) => value !== '' && value != null)
      .map(([key, value]) => [key, Number(value)]));
    if (!Object.keys(values).length || Object.values(values).some(value => !Number.isFinite(value) || value < 0)) {
      setSimulationError('Enter at least one non-negative amount to explore a scenario.');
      return;
    }
    setSimulating(true);
    setSimulationError('');
    try { setSimulation(await api.bankCashflowWhatIf(latest.assessment_id, session.session_id, values)); }
    catch (error) { setSimulationError(error.message || 'The scenario could not be calculated.'); }
    finally { setSimulating(false); }
  };

  return <div className="borrower-dashboard-page">
    <Nav currentPage="dashboard" onLogoClick={() => setActive('overview')} onLogout={() => go('landing')} />
    <div className="borrower-dashboard-frame">
      <aside className="borrower-sidebar">
        <div className="borrower-side-brand"><span className="borrower-brand-mark">P</span><span>PRISM</span></div>
        <div className="borrower-side-caption">YOUR FINANCIAL SPACE</div>
        <nav aria-label="Borrower dashboard">
          {tabs.map(([key, label, icon]) => <button key={key} className={active === key ? 'active' : ''}
            onClick={() => setActive(key)}><span>{icon}</span>{label}</button>)}
        </nav>
        <div className="borrower-side-help"><span className="help-orb">↗</span><strong>Your next step</strong>
          <p>Small, steady money habits build a clearer picture over time.</p>
          <button onClick={() => setActive('patterns')}>View your patterns</button>
        </div>
        <div className="borrower-side-foot">Application {dashboard?.application_id || session?.application_id || '—'}</div>
      </aside>

      <main className="borrower-dashboard-main">
        <header className="borrower-dashboard-header">
          <div><div className="borrower-kicker">BORROWER DASHBOARD</div>
            <h1>{active === 'overview' ? 'Your money, made clearer.' : tabs.find(tab => tab[0] === active)?.[1]}</h1>
            <p>{active === 'overview' ? 'Welcome back. Your activity is organized by the dates found in your statements.' : active === 'fraud' ? 'Review independent transaction and document integrity signals.' : active === 'whatif' ? 'Explore cash-flow scenarios without changing your saved assessment.' : active === 'rbi' ? 'Practical borrower protections and official RBI resources.' : active === 'knowmore' ? 'Understand how PRISM describes the patterns in your statements.' : 'Explore the figures extracted from your uploaded statements.'}</p>
          </div>
          <div className="borrower-header-actions">
            <button className="borrower-icon-button" title="Refresh dashboard" onClick={() => setRefresh(value => value + 1)}>↻</button>
            <button className="borrower-new-assessment" onClick={startNewAssessment}>＋ New assessment</button>
          </div>
        </header>

        {loading ? <div className="borrower-loading"><span />Loading your saved assessments…</div> : !dashboard?.assessment_count ?
          <section className="borrower-empty"><div className="borrower-empty-icon">↗</div><h2>Your dashboard starts with a statement</h2>
            <p>Upload a bank statement to see an observed cash-flow score, monthly patterns and practical next steps.</p>
            <button className="borrower-new-assessment" onClick={startNewAssessment}>Start your first assessment →</button>
          </section> : <>
          {active === 'overview' && <>
            <section className="borrower-overview-grid">
              <article className="borrower-score-card"><div className="borrower-card-title"><span>OBSERVED CASH-FLOW SCORE</span><span className="borrower-live-dot">● Saved</span></div>
                {latest?.score != null ? <><div className="borrower-score-row"><strong>{latest.score}</strong><div><span>out of 900</span><small>{latest.months_observed || 0} months observed · {latest.transaction_count || 0} transactions</small></div></div>
                  <div className="borrower-score-track"><span style={{ left: `${Math.max(0, Math.min(100, ((Number(latest.score) - 300) / 600) * 100))}%` }} /></div>
                  <div className="borrower-score-limits"><span>300</span><span>450</span><span>600</span><span>750</span><span>900</span></div>
                  <p>This describes patterns in the statement rows you shared. It is not a bureau score or lending decision.</p>
                </> : <p>Your latest saved assessment does not contain a score.</p>}
                <button className="borrower-text-button" onClick={() => latest && openAssessment(latest)} disabled={!latest || opening === latest?.assessment_id}>{opening === latest?.assessment_id ? 'Opening…' : 'View assessment details →'}</button>
              </article>
              <article className="borrower-stat-card lavender"><span>MONTHS IN VIEW</span><strong>{monthlyScores.length}</strong><small>Read from statement transaction dates</small><div className="borrower-stat-decoration">◷</div></article>
              <article className="borrower-stat-card mint"><span>SAVED ASSESSMENTS</span><strong>{dashboard.assessment_count}</strong><small>Across this borrower profile</small><div className="borrower-stat-decoration">▤</div></article>
              <article className="borrower-stat-card peach"><span>AVERAGE MONTHLY SPEND</span><strong>{money(latest?.financial_metrics?.average_monthly_expenses, currency)}</strong><small>Across the latest observed period</small><div className="borrower-stat-decoration">⌁</div></article>
            </section>

            <section className="borrower-content-grid">
              <article className="borrower-panel borrower-month-chart"><div className="borrower-panel-heading"><div><span className="borrower-kicker">YOUR MONTHLY JOURNEY</span><h2>Cash-flow score by month</h2></div><button className="borrower-small-link" onClick={() => setActive('monthly')}>See all months →</button></div>
                {monthlyScores.length ? <div className="borrower-bars" role="img" aria-label="Observed cash-flow score by month">
                  {monthlyScores.map(item => <button className={`borrower-bar-column ${item.score == null ? 'no-score' : ''}`} key={item.month} title={`${monthName(item.month)}: ${item.score ?? 'not enough observed patterns'}`} onClick={() => setActive('monthly')}>
                    <span className="borrower-bar-score">{item.score ?? '—'}</span><span className="borrower-bar" style={{ height: `${item.score == null ? 8 : Math.max(8, Number(item.score) / maxMonthScore * 150)}px` }} /><small>{monthName(item.month)}</small>
                  </button>)}
                </div> : <div className="borrower-chart-empty">Monthly scores will appear when the statement has enough observed activity for a month-level comparison.</div>}
                <div className="borrower-chart-note">Each month is calculated from its own dated transaction patterns. Month scores are descriptive snapshots; an empty month is not invented.</div>
              </article>
              <article className="borrower-panel borrower-activity-panel"><div className="borrower-panel-heading"><div><span className="borrower-kicker">RECENT ACTIVITY</span><h2>Your assessment history</h2></div><button className="borrower-small-link" onClick={() => setActive('history')}>View all →</button></div>
                <div className="borrower-activity-list">{recentActivity.map((item,index) => <button key={`${item.assessment_id}-${item.checked_at}-${index}`} className="borrower-activity-item" onClick={() => item.assessment && openAssessment(item.assessment)} disabled={!item.assessment || !['BANK_CASHFLOW_EXPERIMENTAL','CREDIT_ACCOUNT_EXPERIMENTAL'].includes(item.assessment.assessment_type) || opening === item.assessment_id}>
                  <span className="borrower-activity-symbol">↗</span><span className="borrower-activity-copy"><strong>{item.source_document_count ? `${item.source_document_count} statement${item.source_document_count===1?'':'s'} checked` : 'Bank cash-flow assessment'}</strong><small>{dateTime(item.checked_at)}</small></span><span className="borrower-activity-score">{item.assessment?.score ?? '—'} <small>{item.assessment?.score != null ? 'score' : item.status || 'saved'}</small></span>
                </button>)}</div>
              </article>
            </section>

            <section className="borrower-content-grid lower">
              <article className="borrower-panel borrower-pattern-panel"><div className="borrower-panel-heading"><div><span className="borrower-kicker">SPENDING PATTERNS</span><h2>One useful thing to notice</h2></div><span className="borrower-insight-spark">✳</span></div>
                {highestExpense ? <><p>Your highest-spend observed month was <strong>{monthName(highestExpense.month)}</strong> at <strong>{money(highestExpense.expense_total, currency)}</strong>. Your latest average monthly income was {money(latest?.financial_metrics?.average_monthly_income, currency)}.</p>
                  <div className="borrower-pattern-metrics"><div><small>Latest monthly outflow</small><strong>{money(latest?.financial_metrics?.average_monthly_expenses, currency)}</strong></div><div><small>Observed months with positive net flow</small><strong>{latest?.financial_metrics?.surplus_month_rate == null ? '—' : `${Math.round(latest.financial_metrics.surplus_month_rate * 100)}%`}</strong></div></div></> : <p>Upload another statement period to compare income, spending and net flow over time.</p>}
              </article>
              <article className="borrower-panel borrower-guidance-panel"><div className="borrower-panel-heading"><div><span className="borrower-kicker">PERSONALIZED NEXT STEPS</span><h2>Small steps to try</h2></div><span className="borrower-guidance-icon">✓</span></div>
                <ol>{recommendations.slice(0, 3).map((item, index) => <li key={`${index}-${item}`}><span>{index + 1}</span><p>{item}</p></li>)}</ol>
                <button className="borrower-small-link" onClick={() => latest && openAssessment(latest)}>Explore your explanation →</button>
              </article>
            </section>
          </>}

          {active === 'monthly' && <section className="borrower-panel borrower-full-panel"><div className="borrower-panel-heading"><div><span className="borrower-kicker">DERIVED FROM DATED TRANSACTIONS</span><h2>Month-by-month view</h2><p>Income, spending, net flow and the observed-pattern score for each month found in your uploaded statements.</p></div></div>
            <div className="borrower-table-wrap"><table className="borrower-table"><thead><tr><th>Statement month</th><th>Observed score</th><th>Income</th><th>Spending</th><th>Net flow</th><th>Transactions</th></tr></thead><tbody>{monthlyScores.map(item => <tr key={item.month}><td>{monthName(item.month)}</td><td>{item.score == null ? <span className="borrower-unscored-month">Not enough observed patterns</span> : <span className="borrower-score-chip">{item.score}</span>}</td><td>{money(item.income_total, currency)}</td><td>{money(item.expense_total, currency)}</td><td className={Number(item.net_flow) >= 0 ? 'positive' : 'negative'}>{money(item.net_flow, currency)}</td><td>{item.transaction_count}</td></tr>)}</tbody></table></div>
            <p className="borrower-chart-note">Scores use the same observed-pattern factors each month where at least two factors can be calculated. Income regularity needs multiple months and is not inferred from a single month.</p>
          </section>}

          {active === 'patterns' && <section className="borrower-content-grid borrower-pattern-page"><article className="borrower-panel"><span className="borrower-kicker">CASH-FLOW SUMMARY</span><h2>How your money moved</h2><div className="borrower-big-metrics"><div><small>Average monthly income</small><strong>{money(latest?.financial_metrics?.average_monthly_income, currency)}</strong></div><div><small>Average monthly spending</small><strong>{money(latest?.financial_metrics?.average_monthly_expenses, currency)}</strong></div><div><small>Average observed balance</small><strong>{money(latest?.financial_metrics?.average_balance, currency)}</strong></div></div><p>These figures summarize transactions found in your latest uploaded assessment. They do not classify purchases into merchant categories.</p></article>
            <article className="borrower-panel"><span className="borrower-kicker">MONTHLY COMPARISON</span><h2>Your spending by month</h2><div className="borrower-spend-list">{(latest?.monthly || []).map(item => <div key={item.month}><span>{monthName(item.month)}</span><div className="borrower-spend-track"><i style={{ width: `${Math.max(2, Math.min(100, Number(item.expense_total) / Math.max(1, ...latest.monthly.map(row => Number(row.expense_total))) * 100))}%` }} /></div><strong>{money(item.expense_total, currency)}</strong></div>)}</div></article></section>}

          {active === 'history' && <section className="borrower-panel borrower-full-panel"><div className="borrower-panel-heading"><div><span className="borrower-kicker">EVERY SAVED CHECK</span><h2>Assessment and statement history</h2><p>Assessment time shows when PRISM processed the upload. Statement dates come from the document itself.</p></div></div>
            <div className="borrower-history-list">{dashboard.assessments.map(item => <article className="borrower-history-card" key={`${item.assessment_type}-${item.assessment_id}`}>
              <div className="borrower-history-head"><div><strong>{item.assessment_type === 'BANK_CASHFLOW_EXPERIMENTAL' ? 'Bank cash-flow assessment' : 'Credit account assessment'}</strong><small>Application {item.application_id} · {dateTime(item.assessment_timestamp)}</small></div><div className="borrower-history-score">{item.score ?? '—'}<small>{item.score != null ? 'observed score' : item.status}</small></div></div>
              {item.documents?.length > 0 && <div className="borrower-documents">{item.documents.map(doc => <div key={doc.document_id}><span>▧</span><div><strong>{doc.file_name}</strong><small>Statement period: {doc.statement_period?.start || 'date not found'} – {doc.statement_period?.end || 'date not found'} · Uploaded {dateTime(doc.uploaded_at)}</small></div></div>)}</div>}
              <div className="borrower-history-foot"><span>{item.months_observed || 0} observed months · {item.transaction_count ?? '—'} transactions · checked {item.checked_at?.length || 1} time{(item.checked_at?.length || 1)===1?'':'s'}</span><button className="borrower-small-link" onClick={() => openAssessment(item)} disabled={!['BANK_CASHFLOW_EXPERIMENTAL','CREDIT_ACCOUNT_EXPERIMENTAL'].includes(item.assessment_type) || opening === item.assessment_id}>Open details →</button></div>
              {item.checked_at?.length > 0 && <p className="borrower-check-times">Upload checks: {item.checked_at.map(dateTime).join(' · ')}</p>}
            </article>)}</div>
          </section>}

          {active === 'fraud' && <section className="borrower-panel borrower-full-panel borrower-tool-page"><div className="borrower-panel-heading"><div><span className="borrower-kicker">LATEST BANK ASSESSMENT</span><h2>Fraud and integrity checks</h2><p>Independent heuristic checks surface patterns for review. A flag is not proof of fraud and does not change your cash-flow score.</p></div></div>
            {latest?.fraud_findings ? <>
              <div className="borrower-tool-metrics"><div><small>Review status</small><strong className={`borrower-fraud-status ${latest.fraud_findings.fraud_status === 'CLEAR' ? 'clear' : 'review'}`}>{readable(latest.fraud_findings.fraud_status)}</strong></div><div><small>Signals to review</small><strong>{latest.fraud_findings.flags?.length ?? latest.fraud_findings.rule_count ?? 0}</strong></div><div><small>Transactions checked</small><strong>{latest.fraud_findings.coverage?.transactions_reviewed ?? latest.transaction_count ?? '—'}</strong></div><div><small>Engine</small><strong>{latest.fraud_findings.engine_version || 'Recorded'}</strong></div></div>
              {latest.fraud_findings.flags?.length ? <div className="borrower-fraud-list">{latest.fraud_findings.flags.map((flag, index) => <article key={`${flag.rule || flag.type}-${index}`}><span className="borrower-fraud-tag">{readable(flag.severity || 'Review')}</span><h3>{readable(flag.rule || flag.type || 'Transaction signal')}</h3><p>{flag.message || flag.detail || 'The transaction engine marked this pattern for review.'}</p></article>)}</div> : <div className="borrower-tool-note positive"><strong>No transaction rules were triggered.</strong><p>This is a rule-based screen of uploaded rows, not a guarantee that a statement is authentic.</p></div>}
              <div className="borrower-tool-note"><strong>Coverage boundary</strong><p>{latest.fraud_findings.coverage?.identity_and_loan_stacking || 'Identity verification and loan stacking are not assessed by this transaction review.'}</p><small>{latest.fraud_findings.score_semantics || 'Heuristic weighted rule score; not a calibrated probability.'}</small></div>
            </> : <div className="borrower-chart-empty">Fraud review details are not available for this saved assessment.</div>}
          </section>}

          {active === 'whatif' && <section className="borrower-panel borrower-full-panel borrower-tool-page"><div className="borrower-panel-heading"><div><span className="borrower-kicker">HYPOTHETICAL ONLY</span><h2>What-if cash-flow simulator</h2><p>Change monthly values to see how the existing cash-flow formula responds. Your saved score will not be edited.</p></div></div>
            {latest?.score != null ? <form className="borrower-scenario-form" onSubmit={runSimulation}><div className="borrower-scenario-fields">{scenarioFields.map(([key, label, hint]) => <label key={key}>{label}<input type="number" min="0" step={key === 'income_volatility' ? '0.01' : '100'} max={key === 'income_volatility' ? '0.99' : undefined} value={scenario[key] ?? ''} onChange={event => { setScenario(current => ({ ...current, [key]: event.target.value })); setSimulation(null); }} placeholder="Not observed"/><small>{hint}</small></label>)}</div>
              {simulationError && <p className="borrower-simulation-error" role="alert">{simulationError}</p>}
              <button className="borrower-new-assessment" disabled={simulating}>{simulating ? 'Calculating…' : 'Calculate scenario →'}</button>
            </form> : <div className="borrower-chart-empty">A saved score is required to run a scenario. Complete a bank statement assessment first.</div>}
            {simulation && <div className="borrower-simulation-result"><div className="borrower-tool-metrics"><div><small>Saved score</small><strong>{simulation.original_score ?? latest.score}</strong></div><div><small>Scenario score</small><strong>{simulation.score ?? '—'}</strong></div><div><small>Change</small><strong className={Number(simulation.score_delta) >= 0 ? 'positive-text' : 'negative-text'}>{simulation.score_delta > 0 ? '+' : ''}{simulation.score_delta ?? '—'} points</strong></div></div><p>Hypothetical output from the current experimental formula. It is not a prediction of lender approval or repayment.</p>{simulation.recommendations?.length > 0 && <ul>{simulation.recommendations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>}</div>}
          </section>}

          {active === 'rbi' && <section className="borrower-panel borrower-full-panel borrower-tool-page"><div className="borrower-panel-heading"><div><span className="borrower-kicker">BORROWER INFORMATION</span><h2>RBI guidance and your rights</h2><p>PRISM’s observed-pattern score has no RBI-defined eligibility band. These resources describe general protections and do not imply RBI approval of PRISM.</p></div></div>
            <div className="borrower-guidance-context"><strong>{latest?.score != null ? `Your observed-pattern score is ${latest.score}.` : 'Your observed-pattern score is not available yet.'}</strong><p>RBI rules do not map this experimental cash-flow score to a lending decision. Lenders apply their own policies and assess the full application.</p></div>
            <div className="borrower-rbi-grid"><article><span>01</span><h3>Check your credit report</h3><p>Individuals with credit history can request one free full credit report per calendar year from each credit information company that holds their data. Review entries and raise errors with the relevant institution.</p><a href="https://rbi.org.in/commonperson/English/Scripts/Notification.aspx?Id=1884" target="_blank" rel="noreferrer">RBI: Free Annual Credit Report ↗</a></article><article><span>02</span><h3>Read the loan’s key facts</h3><p>Before accepting a covered loan, read the lender’s Key Facts Statement and compare the annual percentage rate, fees, repayment schedule and other terms.</p><a href="https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12848&Mode=0" target="_blank" rel="noreferrer">RBI: Digital Lending Directions, 2025 ↗</a></article><article><span>03</span><h3>Use the complaint route</h3><p>Contact the regulated lender first. If the issue remains unresolved, check the current eligibility and process for the Reserve Bank–Integrated Ombudsman Scheme.</p><a href="https://cms.rbi.org.in/" target="_blank" rel="noreferrer">RBI Complaint Management System ↗</a></article></div>
            <small className="borrower-source-note">RBI source pages checked 12 October 2026. Guidance is general information, not legal advice.</small>
          </section>}

          {active === 'knowmore' && <section className="borrower-panel borrower-full-panel borrower-tool-page"><div className="borrower-panel-heading"><div><span className="borrower-kicker">TRANSPARENT METHODOLOGY</span><h2>Know more about your result</h2><p>See what was measured, how the descriptive score is formed and where its limits are.</p></div></div>
            <div className="borrower-knowmore-summary"><div><small>Assessment method</small><strong>{latest?.model_name || latest?.model_version || 'No saved assessment'}</strong></div><div><small>Observation period</small><strong>{latest?.months_observed ?? 0} month{latest?.months_observed === 1 ? '' : 's'}</strong></div><div><small>Statement rows reviewed</small><strong>{latest?.transaction_count ?? '—'}</strong></div></div>
            <div className="borrower-knowmore-columns"><article><h3>What affects the index</h3><p>Available measures come from dated credits, debits and balances in your bank statement. A measure that cannot be observed stays unknown; it is not treated as zero.</p>{Object.keys(latest?.methodology?.weights || {}).length > 0 && <ul className="borrower-weight-list">{Object.entries(latest.methodology.weights).map(([key, weight]) => <li key={key}><span>{readable(key)}</span><strong>{Math.round(Number(weight) * 100)}%</strong></li>)}</ul>}{latest?.feature_contributions?.length > 0 && <div className="borrower-contribution-list"><h4>Latest observed factors</h4>{latest.feature_contributions.map(row => <div key={row.feature}><span>{readable(row.feature)}</span><strong>{row.direction === 'FAVORABLE' ? 'Favorable pattern' : 'Needs attention'}</strong></div>)}</div>}</article><article><h3>How to read this score</h3><p>The displayed range summarizes cash-flow patterns found in supplied statement rows. It is experimental and is not a bureau score, probability of default, or lending recommendation.</p><p>Fraud checks run separately. A heuristic flag prompts review of the underlying record; it does not establish wrongdoing.</p><p>Use the monthly view to compare observed periods and the simulator to explore hypothetical changes. Neither modifies a saved assessment.</p></article></div>
            {latest?.methodology?.limitations?.length > 0 && <div className="borrower-tool-note"><strong>Known limits</strong><ul>{latest.methodology.limitations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></div>}
          </section>}
        </>}
        <footer className="borrower-dashboard-footer">PRISM scores describe observed patterns in the documents you shared. They are experimental, not bureau scores or lending decisions.<span>Secure session · Application {dashboard?.application_id || session?.application_id || '—'}</span></footer>
      </main>
    </div>
  </div>;
}
