"""Non-production Feature Schema v2 contract for Phase 2C.

This validates a proposed normalized credit-account history contract. It does
not parse uploaded documents and is not wired to the PRISM assessment route.
"""
from __future__ import annotations
from datetime import date
import math
from typing import Any

COMPATIBILITY_CLASSES={
    'DIRECTLY_REPRODUCIBLE',
    'REPRODUCIBLE_WITH_NEW_DOCUMENT_TYPE',
    'STRONG_SEMANTIC_PROXY',
    'WEAK_PROXY',
    'NOT_REPRODUCIBLE',
}
DOCUMENT_TYPES={'credit_card_statement','credit_account_monthly_history','loan_account_statement','bureau_repayment_history'}
FEATURES={
 'recent_delinquency_level':{
   'canonical_name':'recent_delinquency_level','meaning':'Credit-card repayment delay level in the most recent complete observation month.',
   'uci_source_columns':['PAY_0'],'formula':'PAY_0 after the frozen literal recode replace(-2, 0) and replace(-1, 0); PAY_0 is September 2005.',
   'observation_months':['2005-09'],'units':'months past due category (UCI ordinal code; 9 means 9 or more)',
   'aggregation':'Most recent month only.','missingness_policy':'MISSING_REQUIRED_EVIDENCE unless an explicit verified no-facility state is supplied; never zero-fill.',
   'compatibility':'REPRODUCIBLE_WITH_NEW_DOCUMENT_TYPE','required_evidence':['monthly credit-account repayment status or explicit months past due','account/product identity','period month']},
 'months_with_delinquency':{
   'canonical_name':'months_with_delinquency','meaning':'Count of six observed months with a positive UCI repayment-delay category.',
   'uci_source_columns':['PAY_0','PAY_2','PAY_3','PAY_4','PAY_5','PAY_6'],'formula':'sum(1[recode(PAY_m) > 0]); -2 and -1 are recoded to 0 in the frozen experiment.',
   'observation_months':['2005-04','2005-05','2005-06','2005-07','2005-08','2005-09'],'units':'months (integer 0..6)',
   'aggregation':'Count delinquent status across six months.','missingness_policy':'All six ordered observations required; missing month remains MISSING_REQUIRED_EVIDENCE.',
   'compatibility':'REPRODUCIBLE_WITH_NEW_DOCUMENT_TYPE','required_evidence':['six monthly credit-account repayment statuses','account/product identity','period month']},
 'payment_to_statement_ratio':{
   'canonical_name':'payment_to_statement_ratio','meaning':'Sum of six monthly payments divided by the sum of positive monthly statement balances.',
   'uci_source_columns':['PAY_AMT1','PAY_AMT2','PAY_AMT3','PAY_AMT4','PAY_AMT5','PAY_AMT6','BILL_AMT1','BILL_AMT2','BILL_AMT3','BILL_AMT4','BILL_AMT5','BILL_AMT6'],
   'formula':'sum(PAY_AMT1..PAY_AMT6) / sum(max(BILL_AMT1..BILL_AMT6, 0) elementwise); if denominator <= 0, ratio is unavailable, not zero.',
   'observation_months':['2005-04','2005-05','2005-06','2005-07','2005-08','2005-09'],'units':'dimensionless ratio of payment amount to billed balance',
   'aggregation':'Amounts summed across six monthly aligned records before division.','missingness_policy':'All six aligned payment and statement values required; zero denominator yields INSUFFICIENT_DENOMINATOR; no clamping of the ratio.',
   'compatibility':'REPRODUCIBLE_WITH_NEW_DOCUMENT_TYPE','required_evidence':['six credit-card statement balances','six corresponding payment amounts','same account and month alignment']},
 'mean_statement_balance':{
   'canonical_name':'mean_statement_balance','meaning':'Arithmetic mean of the six monthly credit-card billed statement balances.',
   'uci_source_columns':['BILL_AMT1','BILL_AMT2','BILL_AMT3','BILL_AMT4','BILL_AMT5','BILL_AMT6'],
   'formula':'mean(BILL_AMT1..BILL_AMT6), preserving signed source values.',
   'observation_months':['2005-04','2005-05','2005-06','2005-07','2005-08','2005-09'],'units':'source currency units (UCI amount unit; source documentation labels credit limit in NT dollars; balance unit is not separately specified in the variable table)',
   'aggregation':'Arithmetic mean over six monthly statements.','missingness_policy':'All six statement balances required; missing evidence is not zero.',
   'compatibility':'REPRODUCIBLE_WITH_NEW_DOCUMENT_TYPE','required_evidence':['six monthly credit-card statement balances','account/product identity','period month']},
}

def validate_compatibility(value: str) -> str:
    if value not in COMPATIBILITY_CLASSES:
        raise ValueError(f'Invalid compatibility classification: {value}')
    return value

def expected_months(cutoff_month: str, months: int=6) -> list[str]:
    try: year,month=map(int,cutoff_month.split('-'))
    except Exception as exc: raise ValueError('cutoff_month must be YYYY-MM') from exc
    if not 1<=month<=12 or months<1: raise ValueError('invalid month or window length')
    out=[]
    for back in range(months,0,-1):
        ordinal=year*12+(month-1)-back
        y,m=divmod(ordinal,12); out.append(f'{y:04d}-{m+1:02d}')
    return out

def validate_provenance(record: dict[str,Any]) -> None:
    p=record.get('provenance') or {}
    required=('document_id','document_type','page_or_record_id','period_month','raw_field_map','normalized_field_map','extraction_method','extraction_confidence')
    missing=[k for k in required if p.get(k) in (None,'',{})]
    if missing: raise ValueError('PROVENANCE_INCOMPLETE:'+','.join(missing))
    if p['document_type'] not in DOCUMENT_TYPES: raise ValueError('UNSUPPORTED_DOCUMENT_TYPE')
    if not 0<=float(p['extraction_confidence'])<=1: raise ValueError('INVALID_EXTRACTION_CONFIDENCE')

def normalize_uci_repayment_status(value: Any) -> int:
    """Match frozen Phase 2B.6 recode: -2/-1 -> 0; 0..9 retain as integers."""
    try: x=float(value)
    except (TypeError,ValueError) as exc: raise ValueError('INVALID_REPAYMENT_STATUS') from exc
    if not math.isfinite(x) or x!=int(x) or int(x) not in {-2,-1,0,1,2,3,4,5,6,7,8,9}:
        raise ValueError('INVALID_REPAYMENT_STATUS')
    return 0 if int(x) in (-2,-1) else int(x)

def ratio_from_six_months(payment_amounts: list[Any], statement_balances: list[Any]) -> dict[str,Any]:
    if len(payment_amounts)!=6 or len(statement_balances)!=6:
        return {'value':None,'feature_state':'MISSING_REQUIRED_EVIDENCE'}
    try: pa=[float(v) for v in payment_amounts]; bal=[float(v) for v in statement_balances]
    except (TypeError,ValueError): return {'value':None,'feature_state':'MISSING_REQUIRED_EVIDENCE'}
    if not all(math.isfinite(v) for v in pa+bal): return {'value':None,'feature_state':'MISSING_REQUIRED_EVIDENCE'}
    if any(v<0 for v in pa): return {'value':None,'feature_state':'INVALID_EVIDENCE'}
    # Explicit frozen formula clips negative statement balances only in denominator.
    denom=sum(max(v,0.0) for v in bal)
    if denom<=0: return {'value':None,'feature_state':'INSUFFICIENT_DENOMINATOR'}
    return {'value':sum(pa)/denom,'feature_state':'VALID'}

def derive_from_monthly_credit_history(records: list[dict[str,Any]], cutoff_month: str, facility_status: str='ACTIVE', facility_evidence: dict[str,Any]|None=None) -> dict[str,Any]:
    """Evaluate a normalized six-month evidence contract; no OCR/parser included."""
    names=list(FEATURES)
    if facility_status=='NO_CREDIT_FACILITY':
        if not facility_evidence or not facility_evidence.get('verified') or not facility_evidence.get('source_id'):
            return {'feature_states':{n:'MISSING_REQUIRED_EVIDENCE' for n in names},'values':{n:None for n in names},'reason':'NOT_APPLICABLE_REQUIRES_VERIFIED_FACILITY_EVIDENCE'}
        return {'feature_states':{n:'NOT_APPLICABLE' for n in names},'values':{n:None for n in names},'compatibility':'REQUIRES_NEW_EVIDENCE_TYPE'}
    if facility_status!='ACTIVE':
        return {'feature_states':{n:'MISSING_REQUIRED_EVIDENCE' for n in names},'values':{n:None for n in names},'compatibility':'REQUIRES_NEW_EVIDENCE_TYPE'}
    months=expected_months(cutoff_month,6)
    if not records: return {'feature_states':{n:'MISSING_REQUIRED_EVIDENCE' for n in names},'values':{n:None for n in names},'missing_months':months}
    bymonth={}
    for r in records:
        validate_provenance(r)
        if r['provenance']['document_type'] not in DOCUMENT_TYPES: raise ValueError('UNSUPPORTED_DOCUMENT_TYPE')
        month=str(r.get('statement_month') or r['provenance']['period_month'])
        if month>=cutoff_month: raise ValueError('FUTURE_PERIOD_REJECTED')
        if month in bymonth: raise ValueError('DUPLICATE_ACCOUNT_MONTH')
        bymonth[month]=r
    missing=[m for m in months if m not in bymonth]
    if missing: return {'feature_states':{n:'MISSING_REQUIRED_EVIDENCE' for n in names},'values':{n:None for n in names},'missing_months':missing}
    ordered=[bymonth[m] for m in months]
    account_ids={r.get('account_id') for r in ordered}
    products={r.get('product_type') for r in ordered}
    if None in account_ids or None in products: return {'feature_states':{n:'MISSING_REQUIRED_EVIDENCE' for n in names},'values':{n:None for n in names},'missing_months':[]}
    if len(account_ids)!=1 or len(products)!=1: raise ValueError('ACCOUNT_OR_PRODUCT_MISMATCH')
    required_fields=('repayment_delay_months','statement_balance','payment_amount')
    if any(any(r.get(k) is None for k in required_fields) for r in ordered):
        return {'feature_states':{n:'MISSING_REQUIRED_EVIDENCE' for n in names},'values':{n:None for n in names},'missing_months':[]}
    try:
        raw_delays=[float(r['repayment_delay_months']) for r in ordered]
        bills=[float(r['statement_balance']) for r in ordered]
        pays=[float(r['payment_amount']) for r in ordered]
    except KeyError:
        return {'feature_states':{n:'MISSING_REQUIRED_EVIDENCE' for n in names},'values':{n:None for n in names},'missing_months':[]}
    except (TypeError,ValueError) as exc:
        raise ValueError('INVALID_EVIDENCE_VALUE') from exc
    if any(not math.isfinite(d) or d!=int(d) for d in raw_delays): raise ValueError('INVALID_EVIDENCE_VALUE')
    delays=[int(d) for d in raw_delays]
    if any(d<0 or d>9 for d in delays) or any(not math.isfinite(v) for v in bills+pays) or any(p<0 for p in pays):
        raise ValueError('INVALID_EVIDENCE_VALUE')
    ratio=ratio_from_six_months(pays,bills)
    values={'recent_delinquency_level':delays[-1],'months_with_delinquency':sum(d>0 for d in delays),'payment_to_statement_ratio':ratio['value'],'mean_statement_balance':sum(bills)/6}
    states={n:'VALID' for n in names}; states['payment_to_statement_ratio']=ratio['feature_state']
    lineage={n:[{'document_id':r['provenance']['document_id'],'page_or_record_id':r['provenance']['page_or_record_id'],'period_month':m,'raw_field_map':r['provenance']['raw_field_map'],'normalized_field_map':r['provenance']['normalized_field_map']} for m,r in zip(months,ordered)] for n in names}
    return {'feature_states':states,'values':values,'lineage':lineage,'observation_months':months}
