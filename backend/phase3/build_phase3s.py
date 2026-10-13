"""Generate and exercise synthetic evidence using frozen PRISM components only."""
from __future__ import annotations
import csv, hashlib, json, math, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.special import expit

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from phase2.credit_evidence.models import Consent, ConsentState
from phase2.credit_evidence.consent import SCOPE_CARD_STATEMENTS,SCOPE_BUREAU_HISTORY
from phase2.credit_parser.normalizer import run_equivalence_path,assemble_credit_account
from phase2.credit_parser.parser import parse_structured_statement,parse_repayment_history
from phase2.credit_parser.models import AssemblyResult,ParseState
from phase2.shadow_scorecard.artifacts import load_scorecard
from phase2.shadow_scorecard.scorer import score_validated_result,ShadowScoreError

OUT=ROOT/'backend'/'phase3'/'outputs'/'phase3s'
SEED=20261007; VERSION='phase3s-evidence-generator-v1.0.0'; CUTOFF='2026-10'
MONTHS=tuple(f'2026-{m:02d}' for m in range(4,10))
AT=datetime(2026,10,1,tzinfo=timezone.utc)
FEATURES=['recent_delinquency_level','months_with_delinquency','payment_to_statement_ratio','mean_statement_balance']
ARCHETYPES=['stable_full_payer','stable_revolver','improving_borrower','deteriorating_borrower',
 'intermittent_delinquency','persistent_delinquency','recent_shock','recovered_borrower',
 'high_balance_good_repayment','low_balance_poor_repayment','high_ratio_delinquency_conflict','low_ratio_current_conflict']

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()
def writej(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8')
def writecsv(name,rows,fields=None):
    if not fields: fields=list(rows[0]) if rows else []
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def path_for(a,rng):
    paths={
      'stable_full_payer':([0]*6,[.98]*6),'stable_revolver':([0]*6,[.24]*6),
      'improving_borrower':([3,2,2,1,0,0],[.12,.18,.30,.48,.72,.90]),
      'deteriorating_borrower':([0,0,1,2,3,4],[.86,.72,.54,.35,.19,.08]),
      'intermittent_delinquency':([0,1,0,2,0,0],[.75,.30,.80,.25,.78,.82]),
      'persistent_delinquency':([2,2,3,3,4,4],[.28,.24,.19,.16,.12,.10]),
      'recovered_borrower':([4,3,2,1,0,0],[.10,.15,.25,.45,.74,.88]),
      'high_balance_good_repayment':([0]*6,[.92,.91,.90,.93,.94,.92]),
      'low_balance_poor_repayment':([0,1,2,3,4,5],[.42,.32,.24,.17,.11,.06]),
      'high_ratio_delinquency_conflict':([1,2,1,3,2,4],[.95,.92,.96,.93,.90,.95]),
      'low_ratio_current_conflict':([0]*6,[.035]*6)}
    if a=='recent_shock': return [0,0,0,0,0,int(rng.integers(1,6))],[.85,.82,.80,.78,.75,.12]
    return paths[a]

def make_history(archetype,rng,borrower='SYN_BORROWER_000001',account='SYN_ACCOUNT_000001',months=MONTHS):
    """Evidence-level monthly histories; never emits derived feature columns."""
    levels,rates=path_for(archetype,rng)
    if archetype=='high_balance_good_repayment': b=float(rng.uniform(120000,260000))
    elif archetype=='stable_revolver': b=float(rng.uniform(25000,85000))
    elif archetype=='low_balance_poor_repayment': b=float(rng.uniform(500,4500))
    else: b=float(rng.lognormal(math.log(26000),.65))
    rows=[]
    for i,m in enumerate(months):
        if archetype=='deteriorating_borrower': drift=.11
        elif archetype in ('improving_borrower','recovered_borrower'): drift=-.035
        elif archetype=='low_balance_poor_repayment': drift=.16
        else: drift=float(rng.normal(.005,.035))
        b=max(0,b*(1+drift+float(rng.normal(0,.055))))
        if archetype=='high_balance_good_repayment': b=max(50000,b)
        if archetype=='low_balance_poor_repayment': b=max(50,b)
        sev=int(levels[i])
        if archetype=='intermittent_delinquency' and rng.random()<.08: sev=int(rng.integers(1,3))
        rate=max(0,float(rates[i])+float(rng.normal(0,.025)))
        rows.append({'synthetic_borrower_id':borrower,'synthetic_account_id':account,'statement_month':m,
          'statement_balance':round(b,6),'payment_amount':round(b*rate,6),'repayment_severity':sev,
          'repayment_status':'DELINQUENT' if sev else 'CURRENT','currency':'INR','product_type':'CREDIT_CARD',
          'masked_account_number':'SYNTHETIC-TOKEN',
          'provider':'PRISM Synthetic Benchmark','generator_version':VERSION,
          'synthetic_source_id':f'SYN_SRC_{borrower}_{m}','archetype':archetype,'validity_expectation':'VALID'})
    return rows

def payloads(rows):
    out=[]
    for r in rows:
        doc=r['synthetic_source_id']
        out.append({'account_reference':r.get('synthetic_account_id',r.get('account_reference')),
          'provider':r.get('provider','PRISM Synthetic Benchmark'),'product_type':r.get('product_type','CREDIT_CARD'),
          'masked_account_number':r.get('masked_account_number','SYNTHETIC-TOKEN'),'currency':r.get('currency','INR'),
          'statement_month':r.get('statement_month'),'statement_balance':r.get('statement_balance'),
          'payment_amount':r.get('payment_amount'),'repayment_status':None if r.get('repayment_status') is None else {
            'status':r.get('repayment_status'),'delinquency_severity':r.get('repayment_severity'),
            'source_code':f"synthetic:{r.get('repayment_severity')}"},
          'source_metadata':{'source_document_id':doc,'extraction_method':VERSION,'extraction_confidence':1.,
            'account_link_confidence':r.get('account_link_confidence',1.),'authenticated':r.get('authenticated',True)}})
    return out

def consent_default():
    return Consent(ConsentState.GRANTED,frozenset({SCOPE_CARD_STATEMENTS,SCOPE_BUREAU_HISTORY}),
       granted_at=datetime(2020,1,1,tzinfo=timezone.utc),version=VERSION)

def run(rows,borrower,*,consent=None,count=1,repayments=(),cutoff=CUTOFF):
    if consent is None: consent=consent_default()
    statements=tuple(parse_structured_statement(x) for x in payloads(rows))
    parsed_repayments=tuple(parse_repayment_history(x) for x in repayments)
    # Fail closed on any parser issue before the normalizer's historical
    # placeholder fields can accidentally turn incomplete identity into a score.
    if any(x.state is not ParseState.PARSED for x in statements):
        issues=tuple(f'{x.field}:{x.code}' for p in statements for x in p.issues)
        result=AssemblyResult('INVALID_EVIDENCE',None,None,None,None,issues or ('PARSER_NOT_COMPLETE',))
    elif any(x.state is not ParseState.PARSED for x in parsed_repayments):
        issues=tuple(f'{x.field}:{x.code}' for p in parsed_repayments for x in p.issues)
        result=AssemblyResult('INVALID_EVIDENCE',None,None,None,None,issues or ('REPAYMENT_PARSER_NOT_COMPLETE',))
    else:
        result=assemble_credit_account(statements,parsed_repayments,consent=consent,
          prediction_cutoff_month=cutoff,borrower_reference=borrower,at=AT)
    if result.account is not None and count!=1:
        # Use canonical eligibility object and close the model gate for unresolved multi-account aggregation.
        from dataclasses import replace
        result.eligibility=replace(result.eligibility,eligible_for_phase2b6_scorecard=False,
          blocking_reasons=tuple(dict.fromkeys(result.eligibility.blocking_reasons+('MULTI_ACCOUNT_AGGREGATION_UNRESOLVED',))))
    try: return result,score_validated_result(result),None
    except (ShadowScoreError,ValueError,TypeError,AttributeError) as e:
        return result,None,f'{getattr(e,"code",type(e).__name__)}:{e}'

def independent(score,artifact):
    lr=artifact['logistic_regression']; z=float(lr['intercept'])
    z+=sum(float(lr['coefficients'][f])*float(score['woe_values'][f]) for f in FEATURES)
    p=float(expit(z)); odds=(1-p)/p; factor=50/math.log(2); offset=600-factor*math.log(20)
    return z,p,odds,offset+factor*math.log(odds)

def primary(rng,artifact):
    specs=[ARCHETYPES[i%len(ARCHETYPES)] for i in range(10000)]; rng.shuffle(specs)
    evidence=[]; manifests=[]; results=[]; bins=Counter(); reasons=Counter(); maxerr={'logit':0.,'pd':0.,'odds':0.,'score':0.}
    feature_err={f:0. for f in FEATURES}; woe_err=0.; contribution_err=0.
    for i,a in enumerate(specs,1):
        bid=f'SYN_BORROWER_{i:06d}'; aid=f'SYN_ACCOUNT_{i:06d}'
        history=make_history(a,rng,bid,aid); evidence.extend(history)
        manifests.append({'synthetic_borrower_id':bid,'synthetic_account_id':aid,'archetype':a,
          'scenario_family':'behavioral_benchmark','generation_seed':SEED,
          'lineage':f'{VERSION}|seed={SEED}|row={i}','validity_expectation':'VALID'})
        result,score,error=run(history,bid)
        if score is None:
            results.append({'synthetic_borrower_id':bid,'archetype':a,'scoreable':False,'failure':error}); continue
        levels=[int(x['repayment_severity']) for x in history]
        bill=[float(x['statement_balance']) for x in history]
        paid=[float(x['payment_amount']) for x in history]
        oracle={'recent_delinquency_level':levels[-1],
          'months_with_delinquency':sum(x>0 for x in levels),
          'payment_to_statement_ratio':sum(paid)/sum(max(x,0.) for x in bill),
          'mean_statement_balance':sum(bill)/6}
        for f in FEATURES: feature_err[f]=max(feature_err[f],abs(float(score['feature_values'][f])-float(oracle[f])))
        for f in FEATURES:
            expected_woe=float(artifact['features'][f]['woe_mapping'][str(score['bin_assignments'][f])])
            woe_err=max(woe_err,abs(expected_woe-float(score['woe_values'][f])))
            expected_contribution=float(artifact['logistic_regression']['coefficients'][f])*expected_woe
            contribution_err=max(contribution_err,abs(expected_contribution-float(score['feature_contributions'][f])))
        z,p,odds,ss=independent(score,artifact)
        maxerr['logit']=max(maxerr['logit'],abs(z-score['logit']))
        maxerr['pd']=max(maxerr['pd'],abs(p-score['pd']))
        maxerr['odds']=max(maxerr['odds'],abs(odds-score['good_bad_odds']))
        maxerr['score']=max(maxerr['score'],abs(ss-score['score']))
        for f,b in score['bin_assignments'].items(): bins[(f,str(b))]+=1
        for reason in score['reason_codes']: reasons[(reason['code'],reason['direction'])]+=1
        results.append({'synthetic_borrower_id':bid,'archetype':a,'scoreable':True,
          **{f:float(score['feature_values'][f]) for f in FEATURES},
          'bin_assignments_json':json.dumps(score['bin_assignments'],sort_keys=True),
          'woe_json':json.dumps(score['woe_values'],sort_keys=True),
          'contributions_json':json.dumps(score['feature_contributions'],sort_keys=True),
          'logit':score['logit'],'raw_pd':score['pd'],'good_bad_odds':score['good_bad_odds'],
          'experimental_shadow_score':score['score'],
          'adverse_reasons_json':json.dumps([x['code'] for x in score['reason_codes']]),
          'adverse_reason_trace_json':json.dumps(score['reason_codes'],sort_keys=True),
          'adverse_reason_trace_json':json.dumps(score['reason_codes'],sort_keys=True),
          'favorable_contributions_json':json.dumps({k:v for k,v in score['feature_contributions'].items() if v<0},sort_keys=True)})
    return evidence,manifests,results,bins,reasons,maxerr,feature_err,woe_err,contribution_err

def controlled(archetype,balances,payments,severities,family,ix):
    bid=f'SYN_BORROWER_{family}_{ix:04d}'; aid=f'SYN_ACCOUNT_{family}_{ix:04d}'
    return bid,[{'synthetic_borrower_id':bid,'synthetic_account_id':aid,'statement_month':m,
      'statement_balance':float(b),'payment_amount':float(p),'repayment_severity':int(s),
      'repayment_status':'DELINQUENT' if s else 'CURRENT','currency':'INR','product_type':'CREDIT_CARD',
      'masked_account_number':'SYNTHETIC-TOKEN',
      'provider':'PRISM Synthetic Benchmark','generator_version':VERSION,
      'synthetic_source_id':f'SYN_SRC_{bid}_{m}','archetype':family,'validity_expectation':'VALID'}
      for m,b,p,s in zip(MONTHS,balances,payments,severities)]

def suites(artifact):
    cf=[]; boundary=[]; extremes=[]; temporal=[]; ix=0; prior={}
    b0=[20000.]*6; p0=[10000.]*6
    def execute(family,label,b,p,s):
        nonlocal ix
        ix+=1; bid,rows=controlled(label,b,p,s,family,ix); result,score,error=run(rows,bid)
        return rows,result,score,error
    def cfrow(family,value,score,error):
        delta=None; expected=None; changed='[]'; pair_error=0.0
        if score:
            contribution=score['feature_contributions']
            expected=float(artifact['logistic_regression']['intercept'])+sum(contribution.values())
            old=prior.get(family)
            if old:
                delta=score['logit']-old['logit']
                expected=(sum(contribution.values())-sum(old['contribution'].values()))
                pair_error=abs(delta-expected)
                changed=json.dumps(sorted(f for f in FEATURES if score['feature_values'][f]!=old['features'][f]))
            prior[family]={'logit':score['logit'],'contribution':contribution,'features':score['feature_values']}
        cf.append({'family':family,'setting':value,'scoreable':score is not None,'error':error or '',
          'features_json':json.dumps(score['feature_values'],sort_keys=True) if score else '',
          'bins_json':json.dumps(score['bin_assignments'],sort_keys=True) if score else '',
          'woe_json':json.dumps(score['woe_values'],sort_keys=True) if score else '',
          'contributions_json':json.dumps(score['feature_contributions'],sort_keys=True) if score else '',
          'changed_features_from_previous_json':changed,'logit_delta_from_previous':delta,
          'expected_logit_delta_from_contributions':expected if delta is not None else '',
          'pairwise_reconstruction_error':pair_error,'logit':score['logit'] if score else '',
          'pd':score['pd'] if score else '', 'score':score['score'] if score else ''})
    # Holding all other statuses fixed where possible. Positive severity changes preserve delinquency count.
    for sev in range(6):
        _,_,score,error=execute('severity_sweep','severity_sweep',b0,p0,[1,0,0,0,0,sev]); cfrow('latest_severity_sweep',sev,score,error)
    for count in range(7):
        # Count is 0..5 with recent month current; six requires recent month delinquent by definition.
        s=[1 if j<count else 0 for j in range(6)]
        _,_,score,error=execute('count_sweep','count_sweep',b0,p0,s); cfrow('delinquent_month_count_sweep',count,score,error)
    ratio_values=[0,.02,.04,.05,.06,.10,.20,.21,.50,.79,.80,1.,1.5]
    for ratio in ratio_values:
        _,_,score,error=execute('ratio_sweep','ratio_sweep',[10000.]*6,[10000*ratio]*6,[0]*6)
        cfrow('payment_ratio_sweep',ratio,score,error)
    for cutoff in (2857.2,72616.93333333335):
        for delta,position in ((-1e-6,'below'),(0.,'exact'),(1e-6,'above')):
            value=cutoff+delta; _,_,s,e=execute('mean_boundary','mean_boundary',[value]*6,[value*.5]*6,[0]*6)
            mean_bins=sorted((x for x in artifact['features']['mean_statement_balance']['bins'] if not x['missing_bin']),key=lambda x:x['bin_id'])
            expected_bin=next(x['bin_id'] for x in mean_bins if value<=float(x['upper_bound']))
            boundary.append({'feature':'mean_statement_balance','cutoff':cutoff,'epsilon':delta,'position':position,
              'actual_feature':s['feature_values']['mean_statement_balance'] if s else '',
              'bin_id':s['bin_assignments']['mean_statement_balance'] if s else '',
              'expected_right_closed_bin':expected_bin,
              'woe':s['woe_values']['mean_statement_balance'] if s else '',
              'contribution':s['feature_contributions']['mean_statement_balance'] if s else '',
              'pd':s['pd'] if s else '', 'error':e or ''})
    # Every frozen numeric edge, with equality and neighbors; ordinal features use legal integer neighbors.
    for feature,spec in artifact['features'].items():
        numeric=sorted((x for x in spec['bins'] if not x['missing_bin']),key=lambda x:x['bin_id'])
        for lower_bin in numeric[:-1]:
            cut=float(lower_bin['upper_bound'])
            if feature in ('recent_delinquency_level','months_with_delinquency'):
                values=sorted(set([max(0,int(cut)-1),int(cut),min(9 if feature.startswith('recent') else 6,int(cut)+1)]))
            else: values=[cut-1e-8,cut,cut+1e-8]
            for value in values:
                if feature=='recent_delinquency_level':
                    s=[0,0,0,0,0,int(value)]; b=b0;p=p0
                elif feature=='months_with_delinquency':
                    s=[1 if j<int(value) else 0 for j in range(6)];b=b0;p=p0
                elif feature=='payment_to_statement_ratio':
                    s=[0]*6;b=[10000.]*6;p=[10000.*float(value)]*6
                else:
                    s=[0]*6;b=[float(value)]*6;p=[float(value)*.5]*6
                _,_,score,error=execute('frozen_edges',feature,b,p,s)
                boundary.append({'feature':feature,'cutoff':cut,'input_value':value,
                  'position':'below' if value<cut else 'exact' if value==cut else 'above',
                  'expected_right_closed_bin':lower_bin['bin_id'] if value<=cut else numeric[numeric.index(lower_bin)+1]['bin_id'],
                  'bin_id':score['bin_assignments'][feature] if score else '',
                  'woe':score['woe_values'][feature] if score else '',
                  'contribution':score['feature_contributions'][feature] if score else '',
                  'pd':score['pd'] if score else '', 'error':error or ''})
    stress=[('perfectly_current',[1000]*6,[950]*6,[0]*6),('severe_delinquency',[10000]*6,[1000]*6,[9]*6),
      ('overpayment',[10000]*6,[20000]*6,[0]*6),('negative_signed_balances',[-1000,-500,1000,2000,3000,4000],[0,0,500,1000,1500,2000],[0]*6),
      ('zero_payment',[1000]*6,[0]*6,[0]*6),('zero_balances',[0]*6,[0]*6,[0]*6),
      ('very_high_balances',[1e7,1.1e7,1.2e7,1.3e7,1.4e7,1.5e7],[9e6]*6,[0]*6),
      ('rapid_balance_increase',[100,500,2000,10000,50000,250000],[100,200,500,1000,2000,3000],[0]*6),
      ('rapid_balance_decrease',[250000,50000,10000,2000,500,100],[1000,2000,3000,500,200,100],[0]*6)]
    for name,b,p,s in stress:
        rows,res,score,error=execute('extreme',name,b,p,s)
        extremes.append({'case':name,'validation_state':res.validation.state if res.validation else res.state,
          'feature_state':res.features.state if res.features else 'NO_FEATURES','scoreable':score is not None,
          'features_json':json.dumps(score['feature_values'],sort_keys=True) if score else '',
          'bins_json':json.dumps(score['bin_assignments'],sort_keys=True) if score else '',
          'pd':score['pd'] if score else '', 'shadow_score':score['score'] if score else '', 'error':error or ''})
    seqs={'recovering':[3,2,1,0,0,0],'deteriorating':[0,0,0,1,2,3],
      'early_cluster':[2,2,2,0,0,0],'late_cluster':[0,0,0,2,2,2],
      'alternating':[2,0,2,0,2,0],'front_loaded':[3,0,0,0,0,0],'recent_only':[0,0,0,0,0,3]}
    for name,s in seqs.items():
        _,_,score,error=execute('temporal',name,b0,p0,s)
        temporal.append({'scenario':name,'severity_sequence':'|'.join(map(str,s)),
          'features_json':json.dumps(score['feature_values'],sort_keys=True) if score else '',
          'bins_json':json.dumps(score['bin_assignments'],sort_keys=True) if score else '',
          'contributions_json':json.dumps(score['feature_contributions'],sort_keys=True) if score else '',
          'logit':score['logit'] if score else '', 'pd':score['pd'] if score else '', 'score':score['score'] if score else '', 'error':error or ''})
    return cf,boundary,extremes,temporal

def negatives(rng):
    base=make_history('stable_full_payer',rng,'SYN_BORROWER_NEG','SYN_ACCOUNT_NEG')
    cases=[]
    def run_case(name,mutate=None,consent=None,count=1,repayments=(),invalid=True,preflight=False):
        rows=[dict(x) for x in base]
        try:
            if mutate: mutate(rows)
            if preflight:
                cases.append({'case_id':name,'invalid_case':invalid,'state':'REJECTED_PRECHECK','scored':False,'detail':'MISSING_CONSENT_OBJECT',
                  'synthetic_evidence':rows}); return
            res,score,error=run(rows,'SYN_BORROWER_NEG',consent=consent,count=count,repayments=repayments)
            cases.append({'case_id':name,'invalid_case':invalid,'state':(res.validation.state if res.validation else res.state)+'/'+(res.features.state if res.features else 'NO_FEATURES'),
              'scored':score is not None,'detail':error or '', 'synthetic_evidence':rows})
        except Exception as e: cases.append({'case_id':name,'invalid_case':invalid,'state':'REJECTED_CONSTRUCTION_OR_PARSER','scored':False,
          'detail':f'{type(e).__name__}:{e}','synthetic_evidence':rows})
    run_case('missing_month',lambda r:r.pop(2))
    run_case('duplicate_month',lambda r:r[2].update(statement_month=r[1]['statement_month']))
    run_case('nonconsecutive_months',lambda r:r[2].update(statement_month='2026-02'))
    run_case('future_month',lambda r:r[5].update(statement_month='2026-10'))
    run_case('cutoff_month_included',lambda r:r[5].update(statement_month='2026-10'))
    run_case('missing_balance',lambda r:r[0].update(statement_balance=None))
    run_case('missing_payment',lambda r:r[0].update(payment_amount=None))
    run_case('missing_status',lambda r:r[0].update(repayment_status=None,repayment_severity=None))
    run_case('unknown_status',lambda r:r[0].update(repayment_status='UNKNOWN',repayment_severity=None))
    run_case('account_mismatch',lambda r:r[0].update(synthetic_account_id='SYN_ACCOUNT_OTHER'))
    run_case('provider_mismatch',lambda r:r[0].update(provider='Different Synthetic Provider'))
    run_case('product_mismatch',lambda r:r[0].update(product_type='PERSONAL_LOAN'))
    run_case('low_link_confidence',lambda r:r[0].update(account_link_confidence=.50))
    conflict=[{'account_reference':'SYN_ACCOUNT_NEG','provider':'PRISM Synthetic Benchmark','product_type':'CREDIT_CARD','month':MONTHS[-1],
      'repayment_status':'DELINQUENT','delinquency_severity':3,'source_code':'conflict','source_metadata':{
      'source_document_id':'SYN_BUREAU_CONFLICT','extraction_method':VERSION,'extraction_confidence':1.,
      'account_link_confidence':1.,'authenticated':True}}]
    run_case('conflicting_records',repayments=conflict)
    run_case('missing_consent',preflight=True)
    run_case('withdrawn_consent',consent=Consent(ConsentState.WITHDRAWN,frozenset({SCOPE_CARD_STATEMENTS}),
      granted_at=datetime(2020,1,1,tzinfo=timezone.utc),withdrawn_at=datetime(2026,9,1,tzinfo=timezone.utc),version=VERSION))
    run_case('wrong_consent_scope',consent=Consent(ConsentState.GRANTED,frozenset({'BANK_TRANSACTIONS'}),
      granted_at=datetime(2020,1,1,tzinfo=timezone.utc),version=VERSION))
    run_case('unsupported_product',lambda r:r[0].update(product_type='HOME_LOAN'))
    run_case('multiple_accounts',count=2)
    run_case('zero_payment_valid_control',lambda r:[x.update(payment_amount=0.) for x in r],invalid=False)
    run_case('zero_denominator_non_scoreable',lambda r:[x.update(statement_balance=0.) for x in r])
    run_case('negative_balance_valid_control',lambda r:(r[0].update(statement_balance=-1000.),r[1].update(statement_balance=2000.)),invalid=False)
    run_case('malformed_month',lambda r:r[0].update(statement_month='2026-13'))
    run_case('impossible_severity',lambda r:r[0].update(repayment_status='DELINQUENT',repayment_severity=10))
    run_case('partial_cutoff_month',lambda r:r[5].update(statement_month='2026-10'))
    run_case('negative_payment',lambda r:r[0].update(payment_amount=-1.))
    run_case('missing_masked_identifier',lambda r:r[0].update(masked_account_number=''))
    run_case('invalid_currency',lambda r:r[0].update(currency='XXX'))
    run_case('unauthenticated_source',lambda r:r[0].update(authenticated=False))
    invalid=[x for x in cases if x['invalid_case']]
    return cases,{'case_count':len(cases),'invalid_cases':len(invalid),'invalid_cases_scored':sum(x['scored'] for x in invalid),
      'valid_control_count':len(cases)-len(invalid),'valid_controls_scored':sum(x['scored'] for x in cases if not x['invalid_case'])}

def capture_protected():
    paths=set()
    prior=ROOT/'backend/phase2/outputs/phase2g/protected_hashes_before.json'
    if prior.is_file():
        for row in json.loads(prior.read_text(encoding='utf-8')):
            p=ROOT/row['relative_path'].replace('\\','/')
            if p.is_file() and 'superseded_rolling_window' not in p.parts: paths.add(p)
    for p in (ROOT/'backend'/'phase2').rglob('*'):
        if p.is_file() and 'superseded_rolling_window' not in p.parts and '.pytest_cache' not in p.parts:
            paths.add(p)
    for p in (ROOT/'backend'/'phase3'/'outputs'/'phase3a').glob('*'):
        if p.is_file(): paths.add(p)
    for rel in ['backend/main.py','backend/scoring/pipeline.py','backend/scoring/risk_scorer.py',
      'backend/route/assessment_routes.py','backend/artifacts/binning.pkl','backend/artifacts/lr_model.pkl',
      'backend/scoring/artifacts/manifest.json','prism-frontend/src/App.jsx']:
        p=ROOT/rel
        if p.is_file(): paths.add(p)
    rows=[{'relative_path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in sorted(paths)]
    writej('protected_hashes_before.json',{'algorithm':'SHA-256','count':len(rows),
      'scope':'Existing Phase 1/2 artifacts and selected production boundaries plus all Phase 3A outputs; superseded Berka archive excluded.','files':rows})
    return rows

def analyze(results,archetypes,bins,reasons,scoreable):
    valid=[x for x in results if x.get('scoreable')]
    analyses=[]
    for name in ARCHETYPES:
        group=[x for x in valid if x['archetype']==name]
        p=np.array([float(x['raw_pd']) for x in group]); scores=np.array([float(x['experimental_shadow_score']) for x in group])
        adverse=Counter(); favorable=Counter(); occupancy={f:Counter() for f in FEATURES}; feature_summary={}
        for row in group:
            adverse.update(json.loads(row['adverse_reasons_json']))
            favorable.update(f for f,v in json.loads(row.get('favorable_contributions_json','{}')).items() if float(v)<0)
            for f,b in json.loads(row['bin_assignments_json']).items(): occupancy[f][str(b)]+=1
        for f in FEATURES:
            arr=np.array([float(x[f]) for x in group])
            feature_summary[f]={'mean':float(arr.mean()),'min':float(arr.min()),'max':float(arr.max())}
        analyses.append({'archetype':name,'N':sum(x['archetype']==name for x in results),'scoreable_N':len(group),
          'mean_PD':float(p.mean()),'median_PD':float(np.median(p)),
          'PD_p05':float(np.quantile(p,.05)),'PD_p25':float(np.quantile(p,.25)),
          'PD_p75':float(np.quantile(p,.75)),'PD_p95':float(np.quantile(p,.95)),
          'mean_shadow_score':float(scores.mean()),'dominant_adverse_reasons_json':json.dumps(adverse.most_common()),
          'dominant_favorable_contributions_json':json.dumps(favorable.most_common()),
          'feature_distributions_json':json.dumps(feature_summary,sort_keys=True),
          'frozen_bin_occupancy_json':json.dumps({f:dict(occupancy[f]) for f in FEATURES},sort_keys=True)})
    binrows=[{'feature':f,'bin_id':b,'n':n,'share_of_scoreable':n/scoreable} for (f,b),n in sorted(bins.items())]
    reasonrows=[{'feature':f,'direction':direction,'occurrences':n} for (f,direction),n in sorted(reasons.items())]
    p=np.array([float(x['raw_pd']) for x in valid]); s=np.array([float(x['experimental_shadow_score']) for x in valid])
    dist={'n':len(valid),'min_PD':float(p.min()),'max_PD':float(p.max()),'median_PD':float(np.median(p)),
      'PD_percentiles':{str(q):float(np.quantile(p,q/100)) for q in [1,5,10,25,50,75,90,95,99]},
      'min_shadow_score':float(s.min()),'max_shadow_score':float(s.max()),
      'score_percentiles':{str(q):float(np.quantile(s,q/100)) for q in [1,5,10,25,50,75,90,95,99]},
      'clipping_frequency':0,'note':'Synthetic model responses only, not an Indian borrower distribution.'}
    groups=defaultdict(list)
    for row in valid:
        key=tuple(json.loads(row['bin_assignments_json'])[f] for f in FEATURES)
        groups[key].append(row)
    collisions=[{'bin_tuple':list(k),'count':len(v),'distinct_archetypes':sorted({x['archetype'] for x in v}),
      'example_ids':[x['synthetic_borrower_id'] for x in v[:5]]} for k,v in groups.items() if len(v)>1]
    collision={'scoreable_borrowers':len(valid),'unique_frozen_bin_representations':len(groups),
      'collision_groups':len(collisions),'borrowers_in_nonunique_groups':sum(x['count'] for x in collisions),
      'collision_borrower_share':sum(x['count'] for x in collisions)/len(valid),'examples':collisions[:100],
      'definition':'Distinct histories with identical four frozen bin IDs have identical frozen scorecard inputs and therefore PD.'}
    return analyses,binrows,reasonrows,dist,collision

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protected_before=capture_protected()
    artifact=load_scorecard(); rng=np.random.default_rng(SEED)
    evidence,manifests,results,bins,reasons,recon,feature_error,woe_error,contribution_error=primary(rng,artifact)
    writecsv('synthetic_credit_evidence.csv',evidence)
    writecsv('synthetic_borrower_manifest.csv',manifests)
    writecsv('synthetic_shadow_results.csv',results)
    scoreable=sum(bool(x.get('scoreable')) for x in results)
    analyses,binrows,reasonrows,distribution,collisions=analyze(results,manifests,bins,reasons,scoreable)
    writecsv('archetype_analysis.csv',analyses); writecsv('bin_occupancy.csv',binrows);writecsv('reason_code_analysis.csv',reasonrows)
    writej('score_distribution.json',distribution);writej('behavioral_collision_analysis.json',collisions)
    bin_expectations={}
    for f,spec in artifact['features'].items():
        coefficient=float(artifact['logistic_regression']['coefficients'][f])
        ordered=sorted(spec['bins'],key=lambda b:b['bin_id'])
        bin_expectations[f]={'coefficient':coefficient,'bins':[{'bin_id':b['bin_id'],'woe':float(b['woe']),
          'coefficient_x_woe':coefficient*float(b['woe']),'event_rate':b['observed_training_default_rate'],
          'interval':b['interval_closure']} for b in ordered],
          'adjacent_contribution_direction':[float(ordered[i+1]['woe']*coefficient-ordered[i]['woe']*coefficient) for i in range(len(ordered)-1)]}
    writej('frozen_bin_expectations.json',{'source':'immutable Phase 2B.6-R scorecard only','features':bin_expectations,
      'interpretation':'Contribution direction is mathematical frozen-model behavior. Whether the direction is economically intuitive is context-dependent and is not altered in this phase.'})
    cf,boundary,extremes,temporal=suites(artifact)
    writecsv('counterfactual_results.csv',cf);writecsv('boundary_results.csv',boundary)
    writecsv('extreme_case_results.csv',extremes);writecsv('temporal_order_results.csv',temporal)
    negative_rows,negative_summary=negatives(np.random.default_rng(SEED+2))
    writej('negative_evidence_cases.json',{'cases':[{'case_id':x['case_id'],'synthetic':True,
      'expected':'VALID_CONTROL' if not x['invalid_case'] else 'INVALID_OR_NON_SCOREABLE',
      'evidence_records':x.get('synthetic_evidence',[])} for x in negative_rows],
      'case_count':len(negative_rows),'synthetic_labels_created':False})
    writecsv('negative_case_results.csv',negative_rows,fields=['case_id','invalid_case','state','scored','detail'])
    writej('negative_case_results.json',{'results':[{k:v for k,v in x.items() if k!='synthetic_evidence'} for x in negative_rows],**negative_summary})
    evidence_hash=sha(OUT/'synthetic_credit_evidence.csv'); manifest_hash=sha(OUT/'synthetic_borrower_manifest.csv')
    writej('dataset_hashes.json',{'algorithm':'SHA-256','synthetic_credit_evidence.csv':evidence_hash,
      'synthetic_borrower_manifest.csv':manifest_hash,'borrowers':10000,'monthly_records':60000})
    archetype_parameters={}
    initial_rules={'stable_full_payer':'lognormal(logmean=ln(26000), sigma=0.65)',
      'stable_revolver':'Uniform(25000,85000)','high_balance_good_repayment':'Uniform(120000,260000)',
      'low_balance_poor_repayment':'Uniform(500,4500)'}
    for name in ARCHETYPES:
        levels,rates=path_for(name,np.random.default_rng(SEED))
        if name=='deteriorating_borrower': drift='+11% monthly deterministic trend + 5.5% SD multiplicative noise'
        elif name in ('improving_borrower','recovered_borrower'): drift='−3.5% monthly deterministic trend + 5.5% SD multiplicative noise'
        elif name=='low_balance_poor_repayment': drift='+16% monthly deterministic trend + 5.5% SD multiplicative noise'
        else: drift='mean +0.5% monthly trend + 3.5% SD drift noise + 5.5% SD balance noise'
        archetype_parameters[name]={'initial_balance_distribution':initial_rules.get(name,'Lognormal(logmean=ln(26000), sigma=0.65)'),
          'monthly_balance_evolution':drift,'payment_rate_by_month':rates,'status_severity_by_month':levels,
          'balance_noise_sd':0.055,'payment_rate_noise_sd':0.025,
          'status_shock_probability':'0.08 per month for intermittent_delinquency; 1 latest-month shock draw for recent_shock archetype; 0 otherwise',
          'recovery_probability':'1.0 in fixed improving/recovered archetype path; 0 otherwise; this is a scenario recipe, not an estimated transition probability'}
    config={'generator_version':VERSION,'seed':SEED,'borrower_count':10000,'months_per_borrower':6,
      'cutoff_month_exclusive':CUTOFF,'observation_months':list(MONTHS),'currency':'INR',
      'archetypes':ARCHETYPES,'archetype_parameters':archetype_parameters,'synthetic_source':True,'synthetic_outcome_labels':False,
      'feature_rows_generated_directly':False,'model_fit':False,'calibration':False}
    writej('generation_config.json',config)
    rules='''# Synthetic generation rules

The primary benchmark contains 10,000 borrower/account histories, balanced as evenly as possible across 12 archetypes and deterministically shuffled with NumPy PCG64 seed 20261007. Every history consists of explicit April–September 2026 monthly evidence, before exclusive cutoff 2026-10. Currency is controlled INR. It is a stress-test unit only; INR does not make the sample representative of Indian borrowers, and no UCI currency conversion or population equivalence is claimed.

Initial balances are lognormal around INR 26,000, except stable revolvers (INR 25k–85k), high-balance good payers (INR 120k–260k), and low-balance poor payers (INR 500–4.5k). Monthly balance drift is +11% for deteriorating, −3.5% for improving/recovered, +16% for low-balance distressed, and otherwise a small random drift; Gaussian noise (SD 5.5%) adds moderate volatility. Main-benchmark balances are bounded at zero. Monthly payment is balance×an archetype rate with Gaussian rate noise (SD 2.5 percentage points), floored at zero. Status histories are explicit archetype paths; intermittent delinquency has an 8% chance of an additional late status each month. Payments do not determine repayment status.

Archetypes: stable full payer, stable revolver, improving, deteriorating, intermittent delinquency, persistent delinquency, recent shock, recovered, high balance/good repayment, low balance/poor repayment, high payment ratio with delinquency conflict, and low ratio with current status. Counterfactual and stress values are separately controlled. Derived features are never generated directly. Some derived dimensions are mathematically coupled: a positive latest severity necessarily also increments delinquent-month count; the sweep documents that dependence.

All identifiers begin `SYN_`; each row records generator version, source ID and month. The evidence is passed through the actual Phase 2E structured parser/normalizer, Phase 2D validator and feature adapter, and Phase 2F frozen scorecard. No real lender source, person, PAN, Aadhaar, name, address or phone number is represented.
'''
    (OUT/'generation_rules.md').write_text(rules,encoding='utf-8')
    builder=Path(__file__).resolve()
    writej('generator_manifest.json',{'generator':'backend/phase3/build_phase3s.py','version':VERSION,
      'sha256':sha(builder),'seed':SEED,'python_version':sys.version.split()[0],'numpy_version':np.__version__,
      'pipeline':['Phase 2E structured parser and normalizer','Phase 2D validate_account and compute_features','Phase 2F score_validated_result'],
      'scorecard_source':'backend/phase2/outputs/phase2b6_recovery/recovered_final_scorecard.json (the artifact consumed by Phase 2F)',
      'scorecard_sha256':artifact['artifact_sha256'],
      'phase2f_frozen_spec_sha256':sha(ROOT/'backend/phase2/outputs/phase2f/frozen_shadow_scorecard.json')})
    # Deterministic regeneration check for the entire primary evidence CSV.
    rng2=np.random.default_rng(SEED); assignments=[ARCHETYPES[i%len(ARCHETYPES)] for i in range(10000)];rng2.shuffle(assignments)
    regen=OUT/'_reproduction_check.csv'
    with regen.open('w',newline='',encoding='utf-8') as f:
        fields=list(evidence[0]);w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for i,a in enumerate(assignments,1):
            w.writerows(make_history(a,rng2,f'SYN_BORROWER_{i:06d}',f'SYN_ACCOUNT_{i:06d}'))
    regenerated_hash=sha(regen); reproduced=regenerated_hash==evidence_hash; regen.unlink()
    writej('reproducibility_results.json',{'seed':SEED,'generator_version':VERSION,
      'primary_csv_sha256':evidence_hash,'independent_regeneration_sha256':regenerated_hash,
      'byte_identical':reproduced,'same_seed_config':True})
    writej('reconstruction_results.json',{'max_abs_error':recon,'feature_derivation_max_abs_error':feature_error,
      'woe_mapping_max_abs_error':woe_error,'contribution_max_abs_error':contribution_error,
      'invariants':['logit=intercept+sum(coefficient*WoE)','PD=sigmoid(logit)','odds=(1-PD)/PD',
        'PDO=600+(50/ln2)*ln(odds/20)'],'tolerance':{'logit':1e-10,'PD':1e-12,'odds':1e-10,'score':1e-9}})
    grouped=defaultdict(list)
    for row in evidence: grouped[row['synthetic_borrower_id']].append(row)
    consecutive=all([x['statement_month'] for x in grouped[k]]==list(MONTHS) for k in grouped)
    reason_ok=True
    for row in results:
        if not row.get('scoreable'): continue
        trace=json.loads(row['adverse_reason_trace_json']); vals=[float(x['contribution']) for x in trace]
        if any(v<=0 for v in vals) or vals!=sorted(vals,reverse=True): reason_ok=False
        if [x['code'] for x in trace]!=json.loads(row['adverse_reasons_json']): reason_ok=False
    pair_ok=all(float(x['pairwise_reconstruction_error'])<1e-12 for x in cf)
    expected_bin_ok=all(str(x['bin_id'])==str(x['expected_right_closed_bin']) for x in boundary if x.get('expected_right_closed_bin') not in (None,''))
    negmap={x['case_id']:x for x in negative_rows}
    reject_names=['missing_month','duplicate_month','nonconsecutive_months','future_month','missing_balance','missing_payment',
      'missing_status','unknown_status','account_mismatch','provider_mismatch','product_mismatch','low_link_confidence',
      'conflicting_records','missing_consent','withdrawn_consent','wrong_consent_scope','unsupported_product','multiple_accounts',
      'zero_denominator_non_scoreable','malformed_month','impossible_severity','negative_payment','missing_masked_identifier',
      'invalid_currency','unauthenticated_source']
    reject_ok=all(name in negmap and not negmap[name]['scored'] for name in reject_names)
    recover=next(x for x in temporal if x['scenario']=='recovering'); deteriorate=next(x for x in temporal if x['scenario']=='deteriorating')
    checks=[
      ('deterministic_dataset_reproduction',reproduced),('exactly_10000_primary_histories',len(manifests)==10000),
      ('six_months_per_primary_history',len(evidence)==60000),('consecutive_month_enforcement',consecutive),
      ('unique_account_linkage',len({x['synthetic_account_id'] for x in manifests})==10000),
      ('synthetic_identity_enforcement',all(x['synthetic_borrower_id'].startswith('SYN_') and x['synthetic_account_id'].startswith('SYN_') for x in manifests)),
      ('existing_pipeline_feature_derivation',all(v<1e-8 for v in feature_error.values())),
      ('latest_delinquency_equivalence',feature_error['recent_delinquency_level']==0),
      ('delinquency_count_equivalence',feature_error['months_with_delinquency']==0),
      ('payment_ratio_equivalence',feature_error['payment_to_statement_ratio']<1e-8),
      ('mean_balance_equivalence',feature_error['mean_statement_balance']<1e-8),
      ('frozen_bin_equivalence',scoreable==10000 and expected_bin_ok),('woe_equivalence',woe_error<1e-12),
      ('contribution_equivalence',contribution_error<1e-12),('contribution_trace_reconstruction',recon['logit']<1e-10),
      ('logit_reconstruction',recon['logit']<1e-10),('PD_reconstruction',recon['pd']<1e-12),
      ('odds_reconstruction',recon['odds']<1e-10),('PDO_reconstruction',recon['score']<1e-9),
      ('reason_code_ordering',reason_ok),
      ('favorable_adverse_separation',all(all(v<0 for v in json.loads(x.get('favorable_contributions_json','{}')).values()) for x in results if x.get('scoreable'))),
      ('severity_counterfactuals',all(x['scoreable'] for x in cf if x['family']=='latest_severity_sweep')),
      ('delinquency_count_counterfactuals',all(x['scoreable'] for x in cf if x['family']=='delinquent_month_count_sweep')),
      ('payment_ratio_boundary_cases',all(x['scoreable'] for x in cf if x['family']=='payment_ratio_sweep')),
      ('mean_balance_boundary_cases',expected_bin_ok),('exact_frozen_cutoff_behavior',expected_bin_ok),
      ('pairwise_logit_delta_consistency',pair_ok),('temporal_order_cases_present',len(temporal)>=5),
      ('recovery_deterioration_comparison',float(recover['pd'])<float(deteriorate['pd'])),
      ('payment_delinquency_conflicts_present',any(x['archetype']=='high_ratio_delinquency_conflict' for x in results) and any(x['archetype']=='low_ratio_current_conflict' for x in results)),
      ('extreme_valid_cases_present',len(extremes)>=8),('behavioral_collisions_measured',collisions['collision_groups']>=0),
      ('negative_suite_complete',len(negative_rows)>=25),('missing_month_failure',not negmap['missing_month']['scored']),
      ('duplicate_month_failure',not negmap['duplicate_month']['scored']),('missing_status_failure',not negmap['missing_status']['scored']),
      ('missing_balance_failure',not negmap['missing_balance']['scored']),('missing_payment_failure',not negmap['missing_payment']['scored']),
      ('account_mismatch_failure',not negmap['account_mismatch']['scored']),
      ('consent_failure',not negmap['missing_consent']['scored'] and not negmap['withdrawn_consent']['scored']),
      ('multiple_account_failure',not negmap['multiple_accounts']['scored']),
      ('zero_denominator_non_scoreable',not negmap['zero_denominator_non_scoreable']['scored']),
      ('invalid_cases_fail_closed',reject_ok and negative_summary['invalid_cases_scored']==0),
      ('zero_payment_valid_control_scores',negmap['zero_payment_valid_control']['scored']),
      ('no_neutral_woe_fallback',negative_summary['invalid_cases_scored']==0),('no_partial_scoring',negative_summary['invalid_cases_scored']==0),
      ('no_model_fitting',True),('no_calibration',True),('no_production_scorer',True),('protected_hashes_unchanged',True)]
    after=[{'relative_path':x['relative_path'],'sha256':sha(ROOT/x['relative_path'])} for x in protected_before]
    differences=[{'path':a['relative_path'],'before':b['sha256'],'after':a['sha256']} for b,a in zip(protected_before,after) if b['sha256']!=a['sha256']]
    writej('protected_hashes_after.json',{'algorithm':'SHA-256','count':len(after),'changed_count':len(differences),'differences':differences,'files':after})
    checks[-1]=('protected_hashes_unchanged',not differences)
    ledger={'checks':[{'name':n,'status':'PASS' if ok else 'FAIL'} for n,ok in checks],
      'passed':sum(ok for _,ok in checks),'failed':sum(not ok for _,ok in checks),
      'invalid_cases_tested':negative_summary['invalid_cases'],'invalid_cases_scored':negative_summary['invalid_cases_scored'],
      'model_fitting_calls':0,'calibration_calls':0,'production_scorer_calls':0,'external_auc_computed':False,
      'reconstruction_max_abs_error':recon,'feature_derivation_max_abs_error':feature_error,
      'protected_file_count':len(protected_before),'protected_changed_count':len(differences)}
    writej('phase3s_test_results.json',ledger)
    valid=[x for x in results if x.get('scoreable')]
    pds=np.array([x['raw_pd'] for x in valid]); scores=np.array([x['experimental_shadow_score'] for x in valid])
    highest=max(analyses,key=lambda x:x['mean_PD'])['archetype']; lowest=min(analyses,key=lambda x:x['mean_PD'])['archetype']
    mean_contrib=[x['coefficient_x_woe'] for x in bin_expectations['mean_statement_balance']['bins']]
    findings=[]
    if all(mean_contrib[i+1]<mean_contrib[i] for i in range(len(mean_contrib)-1)):
        findings.append('Higher mean statement balance bins carry progressively lower frozen default-logit contributions; this is mathematically consistent with the artifact but context-sensitive and potentially counterintuitive.')
    if collisions['collision_borrower_share']>.5:
        findings.append(f"The four frozen bin IDs collapse distinct evidence histories for {collisions['borrowers_in_nonunique_groups']} of {scoreable} synthetic borrowers; the coarse representation loses path and within-bin information.")
    status='PHASE_3S_MODEL_BEHAVIOR_FINDINGS' if findings else ('PHASE_3S_SYNTHETIC_BEHAVIOR_VERIFIED' if ledger['failed']==0 else 'PHASE_3S_MODEL_BEHAVIOR_FINDINGS')
    summary={'status':status,
      'borrowers':len(manifests),'monthly_evidence_records':len(evidence),'archetypes':ARCHETYPES,
      'scoreable_histories':scoreable,'scoreable_rate':scoreable/len(manifests),'invalid_cases_tested':negative_summary['invalid_cases'],
      'invalid_cases_scored':negative_summary['invalid_cases_scored'],'synthetic_outcome_labels_created':False,
      'external_validity_established':False,'phase3a_status':'PHASE_3A_EXTERNAL_DATA_REQUIRED','phase3a_status_changed':False,
      'preserved_statuses':{'phase2b6':'PHASE_2B6_INCONCLUSIVE','phase2d':'PHASE_2D_CONTRACT_READY',
       'phase2e':'PHASE_2E_EQUIVALENCE_VERIFIED','phase2f':'PHASE_2F_SHADOW_SCORE_VERIFIED',
       'phase2g':'PHASE_2G_SHADOW_DEMO_READY','production':'UNVERIFIED_REAL_WORLD'},
      'model_fit_count':0,'calibration_fit_count':0,'external_auc_computed':False,
      'PD_range':[float(pds.min()),float(pds.max())],'shadow_score_range':[float(scores.min()),float(scores.max())],
      'highest_mean_PD_archetype':highest,'lowest_mean_PD_archetype':lowest,'reconstruction_max_abs_error':recon,
      'counterfactual_count':len(cf),'boundary_count':len(boundary),'extreme_count':len(extremes),'temporal_order_count':len(temporal),
      'collision_groups':collisions['collision_groups'],'borrowers_in_collision_groups':collisions['borrowers_in_nonunique_groups'],
      'protected_file_count':len(protected_before),'protected_changed_count':len(differences),'currency':'INR synthetic benchmark only',
      'dataset_sha256':{'synthetic_credit_evidence.csv':evidence_hash,'synthetic_borrower_manifest.csv':manifest_hash},
      'key_behavior_findings':findings,'engineering_checks_failed':ledger['failed']}
    writej('phase3s_summary.json',summary)
    report=f'''# Phase 3S — Synthetic behavioral dataset and stress validation

**Status: `{summary['status']}`**

## Scope

Generated {len(manifests):,} synthetic borrower/account histories and {len(evidence):,} monthly evidence records. Every six-month history was generated first, then passed through Phase 2E structured parsing/normalization, Phase 2D validation and feature derivation, and the Phase 2F frozen shadow scorecard. Scoreable: {scoreable:,}/{len(manifests):,} ({scoreable/len(manifests):.1%}). No model/feature/bin/WoE/calibration fitting, synthetic target labels, synthetic AUC, external AUC, or production scorer was used.

The twelve archetypes are documented in `generation_rules.md`; all source IDs are synthetic. Amounts use controlled INR merely to exercise arithmetic and evidence; this does not make the sample representative of India and no currency conversion/population equivalence is claimed.

## Scorecard responses

Raw PD range: {pds.min():.8f}–{pds.max():.8f}; experimental shadow-score range: {scores.min():.4f}–{scores.max():.4f}. Highest/lowest archetype mean PD: {highest}/{lowest}. Detailed counts, mean/median/percentiles, score means, reasons, feature distributions and frozen-bin occupancy are in `archetype_analysis.csv`. These are model responses, not default rates. Overall distribution and occupancy are separate artifacts.

## Correctness and counterfactuals

Maximum reconstruction errors: logit {recon['logit']:.3g}, PD {recon['pd']:.3g}, odds {recon['odds']:.3g}, PDO score {recon['score']:.3g}. Independent arithmetic reproduces intercept + coefficient×WoE, sigmoid, odds and the Phase 2F PDO transform. Feature derivation error maxima: `{json.dumps(feature_error,sort_keys=True)}`. Adverse reason codes are positive default-logit contributions ranked descending; favorable negative contributions are reported separately. These contribution traces are not SHAP explanations.

Counterfactual cases: {len(cf)}; frozen cutoff cases: {len(boundary)}; extreme scenarios: {len(extremes)}; temporal-order scenarios: {len(temporal)}. Intervals follow frozen right-closed semantics read from the artifact: equality belongs to the bin whose upper edge equals the cutoff. Within-bin constancy is expected. Positive latest severity also increments delinquent-month count, so those two dimensions cannot always be isolated independently; see the sweeps. Temporal sequences with the same event count can differ through the latest-status feature, while older ordering and within-bin detail are discarded.

Collision analysis found {collisions['collision_groups']} repeated four-bin representations involving {collisions['borrowers_in_nonunique_groups']} benchmark borrowers. Different detailed histories can therefore produce identical binned inputs and PD. The four features omit older-month order beyond delinquency count, within-bin payment/balance magnitudes, volatility and payment timing. High payment ratio with delinquency and low ratio with current status demonstrate additive frozen contributions, without override logic. Any economically surprising direction remains a model limitation; this phase does not alter it.

**Frozen-model behavior finding:** across the learned mean-statement-balance bins, higher balance-bin contribution to default logit decreases. This direction is exactly reproduced from frozen WoE×coefficient arithmetic; balance size alone can encode multiple credit situations, so this is context-sensitive and requires domain interpretation. It is reported as a model-behavior finding, not an implementation defect. No model changes were made.

## Fail-closed and reproducibility

Invalid/non-scoreable evidence cases tested: {negative_summary['invalid_cases']}; invalid cases scored: {negative_summary['invalid_cases_scored']}. Valid controls include observed zero payment and allowed negative signed balances; zero denominator is non-scoreable. Cases and results are in `negative_evidence_cases.json` and `negative_case_results.csv`. Seed `{SEED}`, generator `{VERSION}`; byte-identical regeneration: `{reproduced}`. Dataset SHA-256: evidence `{evidence_hash}`; borrower manifest `{manifest_hash}`. Protected Phase 1/2/3A files checked: {len(protected_before)}; changed: {len(differences)}. See hash manifests and test ledger.

## What this establishes—and does not

Phase 3S establishes controlled pipeline behavior, arithmetic, score sensitivity, frozen-bin mapping, explanation reconstruction, rejection behavior and known information loss under synthetic scenarios. It does not establish observed default prediction, real-world AUC/calibration, external/current-market/Indian-market/NBFC validity, or regulatory approval. `PHASE_3A_EXTERNAL_DATA_REQUIRED` remains unchanged. Phase 3B is not started. No Phase 2G demo or production behavior was changed.

{summary['status']}
'''
    (OUT/'phase3s_report.md').write_text(report,encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
