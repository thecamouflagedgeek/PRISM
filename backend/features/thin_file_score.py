"""Versioned uploaded-period cash-flow snapshot, separate from V1 history/PD."""
from copy import deepcopy
from features.bank_health_index import calculate_bank_health_index, _score, _recommendations

SNAPSHOT_VERSION = 'PRISM_CASHFLOW_SNAPSHOT_V1'
HISTORY_ONLY = {'AT_LEAST_3_COMPLETE_CALENDAR_MONTHS_REQUIRED',
    'COMPLETE_CALENDAR_MONTH_COVERAGE_NOT_VERIFIED', 'NONCONSECUTIVE_OBSERVATION_MONTHS',
    'STATEMENT_PAGE_COVERAGE_NOT_VERIFIED'}


def calculate_cashflow_snapshot(transactions, *, currency=None, evidence=None, document_count=1):
    """Describe observed rows without inventing months or regularity evidence.

    Unknown page completeness limits scope to supplied pages; it does not certify
    a complete financial history. Extraction/balance/currency/duplicate checks
    remain mandatory. No credit default target or predictive validation exists.
    """
    snapshot_evidence = dict(evidence or {})
    balance_scope = 'DECLARED_OPENING_RUNNING_CLOSING'
    if snapshot_evidence.get('balance_reconciled') is None and snapshot_evidence.get('observed_running_balances_reconciled') is True:
        snapshot_evidence['balance_reconciled'] = True
        balance_scope = 'OBSERVED_SUCCESSIVE_RUNNING_BALANCES'
    result = calculate_bank_health_index(transactions, currency=currency, evidence=snapshot_evidence)
    history_only = set(HISTORY_ONLY)
    if document_count == 1:
        history_only.add('ACCOUNT_REFERENCE_NOT_VERIFIED_ACROSS_STATEMENTS')
    problems = sorted(set(result['evidence_gaps']) - history_only)
    if not result.get('transaction_count'):
        problems.append('NO_READABLE_BANK_TRANSACTIONS')
    if problems:
        raise ValueError('Please upload a readable bank statement with dated debit/credit rows and reconciling transaction balances. Checks requiring correction: '+', '.join(problems))
    result = deepcopy(result)
    scored = _score(result['feature_values'])
    if scored['score'] is None:
        raise ValueError('No measurable cash-flow patterns were extracted. Please upload a clearer bank statement.')
    result.update({'model_name':'PRISM cash-flow snapshot', 'model_version':SNAPSHOT_VERSION,
        'assessment_profile':'snapshot','status':'SCORED','scoreable':True,
        'score':scored['score'],'feature_contributions':scored['contributions'],
        'reason_codes':[row['feature'] for row in scored['contributions'] if row['direction']=='ADVERSE'],
        'evidence_gaps':[], 'validation_status':'OBSERVED_PATTERNS_VERIFIED',
        'recommendations':_recommendations(result['feature_values'])})
    result['coverage'] = {'statement_count':document_count,'months_observed':result['months_observed'],
        'transactions_reviewed':result['transaction_count'],'scope':'Uploaded statement rows only',
        'history_depth':'LIMITED' if result['months_observed'] < 3 else 'EXTENDED',
        'available_factors':sum(value is not None for value in result['feature_values'].values()),
        'total_factors':5,'unknown_factors':[name for name,value in result['feature_values'].items() if value is None],
        'page_completeness_verified':bool((evidence or {}).get('page_coverage_complete')),
        'balance_verification_scope':balance_scope,
        'declared_opening_closing_verified':(evidence or {}).get('balance_reconciled') is True}
    result['methodology'].update({'minimum_history_months':1,'version':SNAPSHOT_VERSION,
        'scope':'Observed-period descriptive score. Complete calendar history is not required or inferred.',
        'validation':'Extraction, dates, currency, balances, duplicates and adjustments must pass.',
        'limitations':['Not a trained or validated credit-risk model, bureau score, PD or lending decision.',
            'Single-month income regularity is unknown and omitted; available weights are renormalized.',
            'Only supplied pages and observed months are described; missing history is not fabricated.']})
    if balance_scope == 'OBSERVED_SUCCESSIVE_RUNNING_BALANCES':
        result['methodology']['limitations'].append('Successive balances are verified; the first transaction has no preceding balance check and declared opening/closing balances are unavailable.')
    return result


def simulate_cashflow_snapshot(baseline, scenario):
    """Preserve unknown snapshot factors unless explicitly supplied in scenario."""
    from features.bank_health_index import simulate_bank_health
    result = simulate_bank_health(baseline, scenario)
    features = result['feature_values']
    if baseline['feature_values'].get('income_regularity') is None and 'income_volatility' not in scenario:
        features['income_regularity'] = None
    # The V1 simulator's invented three-point series must not stand in for history.
    if 'monthly_income' not in scenario and 'monthly_expenses' not in scenario:
        features['surplus_month_rate'] = baseline['feature_values'].get('surplus_month_rate')
    scored = _score(features)
    result.update({'score':scored['score'],'score_delta':scored['score']-baseline['score'],
        'feature_contributions':scored['contributions'],'model_version':SNAPSHOT_VERSION})
    return result
