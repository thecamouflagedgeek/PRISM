"""Phase 2B.6: fold-local constrained WoE/LR robustness evaluation.

This is research-only and deliberately has no imports from production scoring.
All target-informed binning/screening/model fitting is confined to each fit fold.
The dataset and outer 80/20 seed are frozen from Phase 2B.5-R.
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'real_evidence'))
from run_phase2b5r import INPUT, SEED, TARGET, FEATURES, SEM, derive, stratified_split, metrics, sigmoid, fit_lr, calibration
OUT=ROOT/'outputs'/'phase2b6'; OUT.mkdir(parents=True,exist_ok=True)

PRIMARY={'max_bins':5,'min_bad':25,'min_good':25,'min_bin_share':0.02,'iv_floor':0.01,'correlation_cap':0.90,'l2':1.0}
SENSITIVITY=[
    ('primary',PRIMARY),
    ('max_bins_3',{**PRIMARY,'max_bins':3}),
    ('min_events_50',{**PRIMARY,'min_bad':50,'min_good':50}),
    ('without_payment_ratio',{**PRIMARY,'exclude':['payment_to_statement_ratio']}),
]

def raw_bins(s,max_bins):
    q=np.unique(s.dropna().quantile(np.linspace(0,1,max_bins+1)).to_numpy())
    if len(q)<2: return np.array([-np.inf,np.inf])
    q[0]=-np.inf; q[-1]=np.inf
    return q

def group_stats(bin_ids,y,groups):
    out=[]
    for g in groups:
        mask=np.isin(bin_ids,g); bad=int(np.sum(y[mask])); good=int(mask.sum()-bad)
        out.append({'members':list(g),'n':int(mask.sum()),'bad':bad,'good':good,'rate':float(bad/mask.sum()) if mask.sum() else 0.0})
    return out

def pava_merge(stats,direction):
    """Merge adjacent groups until event rates obey the training-selected order."""
    groups=[s['members'][:] for s in stats]
    changed=True
    while changed and len(groups)>1:
        changed=False; now=group_stats_from_members(stats,groups)
        for i in range(len(now)-1):
            violation=(now[i]['rate']>now[i+1]['rate']) if direction=='increasing' else (now[i]['rate']<now[i+1]['rate'])
            if violation:
                groups[i]=groups[i]+groups[i+1]; del groups[i+1]; changed=True; break
    return groups

def group_stats_from_members(initial,groups):
    lookup={member:s for s in initial for member in s['members']}
    result=[]
    for g in groups:
        n=sum(lookup[m]['n'] for m in g); bad=sum(lookup[m]['bad'] for m in g); good=n-bad
        result.append({'members':g[:],'n':n,'bad':bad,'good':good,'rate':bad/n if n else 0.})
    return result

def learn_binner(train,feature,cfg):
    s=train[feature].astype(float); y=train[TARGET].to_numpy(int); edges=raw_bins(s,cfg['max_bins'])
    ids=pd.cut(s,bins=edges,labels=False,include_lowest=True,duplicates='drop').fillna(-1).astype(int).to_numpy()
    k=len(edges)-1; base=[]
    for j in range(k):
        mask=ids==j; bad=int(y[mask].sum()); n=int(mask.sum())
        if n: base.append({'members':[j],'n':n,'bad':bad,'good':n-bad,'rate':bad/n})
    if not base: raise ValueError(f'{feature}: no nonmissing training values')
    # Select monotone event-rate direction solely from fit-fold data; ties are documented as flat/increasing.
    # Direction is chosen by total violation magnitude; this is a train-only constrained binning decision.
    up_violation=sum(max(0,base[i-1]['rate']-base[i]['rate'])**2 for i in range(1,len(base)))
    down_violation=sum(max(0,base[i]['rate']-base[i-1]['rate'])**2 for i in range(1,len(base)))
    direction='increasing' if up_violation<=down_violation else 'decreasing'
    groups=[b['members'][:] for b in base]
    # Enforce class-count and population minima by merging deficient adjacent bins with closest event rate.
    min_n=max(50,int(np.ceil(cfg['min_bin_share']*len(train))))
    while len(groups)>1:
        gs=group_stats_from_members(base,groups)
        deficient=[i for i,z in enumerate(gs) if z['n']<min_n or z['bad']<cfg['min_bad'] or z['good']<cfg['min_good']]
        if not deficient: break
        i=deficient[0]; neighbors=[j for j in (i-1,i+1) if 0<=j<len(groups)]
        j=min(neighbors,key=lambda j:abs(gs[i]['rate']-gs[j]['rate'])*(gs[i]['n']+gs[j]['n']))
        lo=min(i,j); hi=max(i,j); groups[lo]+=groups[hi]; del groups[hi]
    groups=pava_merge(base,direction)
    # Monotone pooling may create/retain deficient groups; repeat adjacent merging, then restore monotonicity.
    while len(groups)>1:
        gs=group_stats_from_members(base,groups)
        deficient=[i for i,z in enumerate(gs) if z['n']<min_n or z['bad']<cfg['min_bad'] or z['good']<cfg['min_good']]
        if not deficient: break
        i=deficient[0]; ns=[j for j in (i-1,i+1) if 0<=j<len(groups)]
        j=min(ns,key=lambda j:abs(gs[i]['rate']-gs[j]['rate'])*(gs[i]['n']+gs[j]['n']))
        lo=min(i,j); hi=max(i,j); groups[lo]+=groups[hi]; del groups[hi]
        groups=pava_merge(base,direction)
    gs=group_stats_from_members(base,groups)
    # A lone unresolved bin is not silently accepted when it violates hard event minima.
    if any(z['n']<min_n or z['bad']<cfg['min_bad'] or z['good']<cfg['min_good'] for z in gs):
        raise ValueError(f'{feature}: no feasible constrained bins under configured minimums')
    raw_to_group={m:i for i,g in enumerate(groups) for m in g}
    # Convert grouped raw quantile bins into cut edges.
    cutidx=[max(g)+1 for g in groups[:-1]]; learned_edges=np.r_[-np.inf,[edges[j] for j in cutidx],np.inf]
    # Missing values require a learned class-supported bin; otherwise fail closed.
    miss=y[s.isna().to_numpy()]; has_missing=bool(s.isna().any())
    if has_missing and (miss.sum()<cfg['min_bad'] or len(miss)-miss.sum()<cfg['min_good']):
        raise ValueError(f'{feature}: missing bin lacks minimum good/default support')
    def assign(values):
        z=pd.cut(values.astype(float),bins=learned_edges,labels=False,include_lowest=True,duplicates='drop').astype('float')
        z[values.isna()]=-1
        return z.astype(int)
    train_ids=assign(s)
    tab=pd.crosstab(train_ids,y).reindex(columns=[0,1],fill_value=0)
    if has_missing and -1 not in tab.index: raise ValueError(f'{feature}: training missing bin absent')
    # Missing bin is separate and not included in numeric monotonicity checks.
    ngood=tab[0]+0.5; nbad=tab[1]+0.5
    pg=ngood/ngood.sum(); pb=nbad/nbad.sum(); woe=np.log(pg/pb)
    mapper={int(ix):float(v) for ix,v in woe.items()}
    rows=[]
    for ix,r in tab.iterrows():
        n=int(r.sum()); rows.append({'feature':feature,'bin_index':int(ix),'lower':None if ix==-1 else float(learned_edges[int(ix)]),'upper':None if ix==-1 else float(learned_edges[int(ix)+1]),'missing_bin':bool(ix==-1),'good':int(r[0]),'bad':int(r[1]),'population':n,'event_rate':float(r[1]/n),'woe_good_over_bad':mapper[int(ix)],'iv_component':float((pg[ix]-pb[ix])*mapper[int(ix)]),'direction':('missing' if ix==-1 else direction),'n_numeric_bins':len(gs),'min_bin_population_required':min_n,'min_good_required':cfg['min_good'],'min_bad_required':cfg['min_bad']})
    def ordered_rates(): return [z['rate'] for z in group_stats_from_members(base,groups)]
    q25,q75=s.quantile([.25,.75]).to_numpy(); iqr=float(q75-q25) or 1.0; median=float(s.median()) if s.notna().any() else 0.0
    normalized=[float((v-median)/iqr) for v in learned_edges[1:-1]]
    return {'edges':learned_edges,'mapping':mapper,'direction':direction,'rows':rows,'iv':float(sum(r['iv_component'] for r in rows)),'numeric_rates':ordered_rates(),'train_ids':train_ids,'normalized_cutpoints':normalized}

def encode_frame(frame,binners):
    out=pd.DataFrame(index=frame.index)
    for f,b in binners.items():
        ids=pd.cut(frame[f].astype(float),bins=b['edges'],labels=False,include_lowest=True,duplicates='drop').astype('float')
        ids[frame[f].isna()]=-1
        ints=ids.astype(int)
        if set(ints.unique())-set(b['mapping']): raise ValueError(f'{f}: evaluation bin not learned')
        out[f]=ints.map(b['mapping']).astype(float)
    return out

def fit_spec(Xtrain,ytrain,Xapply,feature_pool,cfg):
    feature_pool=[f for f in feature_pool if f not in cfg.get('exclude',[])]
    train=Xtrain[feature_pool].copy(); train[TARGET]=np.asarray(ytrain,int)
    binners={f:learn_binner(train,f,cfg) for f in feature_pool}
    iv={f:binners[f]['iv'] for f in feature_pool}
    keep=[f for f in feature_pool if iv[f]>=cfg['iv_floor']]
    keep=sorted(keep,key=lambda f:iv[f],reverse=True)
    # Correlation pruning is fit-only and deterministic; retain higher-IV feature in each redundant pair.
    chosen=[]
    for f in keep:
        redundant=False
        for g in chosen:
            rho=train[[f,g]].corr(method='spearman').iloc[0,1]
            if pd.notna(rho) and abs(rho)>cfg['correlation_cap']:
                redundant=True; break
        if not redundant: chosen.append(f)
    if not chosen: raise ValueError('No semantically eligible features passed fixed training-only IV screen')
    bt={f:binners[f] for f in chosen}; tr=encode_frame(Xtrain[chosen],bt); ap=encode_frame(Xapply[chosen],bt)
    beta=fit_lr(tr,ytrain,l2=cfg['l2'])
    return {'features':chosen,'binners':bt,'train_woe':tr,'apply_woe':ap,'beta':beta,'all_binners':binners}

def predict(spec,x): return sigmoid(np.column_stack([np.ones(len(x)),x.to_numpy(float)])@spec['beta'])

def summarize_stability(folds):
    feat_rows=[]; coef_rows=[]; bin_rows=[]
    for f in FEATURES:
        choices=[z for z in folds if f in z['spec']['features']]
        freq=len(choices)/len(folds)
        signs=[int(np.sign(z['spec']['beta'][1+z['spec']['features'].index(f)])) for z in choices]
        dirs=[z['spec']['all_binners'][f]['direction'] for z in folds]
        feat_rows.append({'feature':f,'semantic_mapping':SEM[f],'selection_count':len(choices),'selection_frequency':freq,'direction_increasing_frequency':dirs.count('increasing')/len(dirs),'direction_decreasing_frequency':dirs.count('decreasing')/len(dirs),'coefficient_sign_consistency':max(signs.count(1),signs.count(-1))/len(signs) if signs else 0,'coefficient_sign':'positive' if signs and sum(signs)>0 else 'negative' if signs else 'not_selected'})
        cs=[z['spec']['beta'][1+z['spec']['features'].index(f)] for z in choices]
        coef_rows.append({'feature':f,'selected_folds':len(cs),'coefficient_mean':float(np.mean(cs)) if cs else None,'coefficient_sd':float(np.std(cs,ddof=1)) if len(cs)>1 else None,'coefficient_abs_median':float(np.median(np.abs(cs))) if cs else None,'sign_consistency':max(signs.count(1),signs.count(-1))/len(signs) if signs else None})
        for z in folds:
            b=z['spec']['all_binners'][f];
            bin_rows.append({'split':z['split'],'feature':f,'selected':f in z['spec']['features'],'numeric_bin_count':b['rows'][0]['n_numeric_bins'],'direction':b['direction'],'numeric_edges_json':json.dumps(b['edges'].tolist()),'normalized_cutpoints_json':json.dumps(b['normalized_cutpoints']),'iv':b['iv'],'numeric_event_rates_json':json.dumps(b['numeric_rates'])})
    return pd.DataFrame(feat_rows),pd.DataFrame(coef_rows),pd.DataFrame(bin_rows)

def run():
    df=pd.read_csv(INPUT); y=df[TARGET].astype(int); X=derive(df)
    if len(df)!=30000 or df.ID.nunique()!=len(df) or int(y.sum())!=6636: raise ValueError('Frozen dataset gate changed; refusing to run')
    dev,test=stratified_split(y,.20,SEED); folds=[]; val=[]; splitrows=[]; allbin=[]
    for k in range(10):
        trrel,varel=stratified_split(y.iloc[dev].to_numpy(),.20,SEED+100+k); tri=dev[trrel]; vai=dev[varel]
        spec=fit_spec(X.iloc[tri],y.iloc[tri],X.iloc[vai],FEATURES,PRIMARY); p=predict(spec,spec['apply_woe'])
        folds.append({'split':k+1,'train_ix':tri,'validation_ix':vai,'spec':spec})
        val.append({'split':k+1,'selected_features':'|'.join(spec['features']),**metrics(y.iloc[vai],p)})
        splitrows.append({'split':k+1,'seed':SEED+100+k,'train_n':len(tri),'validation_n':len(vai),'train_ids_sha256':hashlib.sha256(','.join(map(str,df.ID.iloc[tri])).encode()).hexdigest(),'validation_ids_sha256':hashlib.sha256(','.join(map(str,df.ID.iloc[vai])).encode()).hexdigest(),'selected_features':'|'.join(spec['features'])})
        for f,b in spec['all_binners'].items():
            allbin.extend([{'split':k+1,**r} for r in b['rows']])
    fs,cs,bs=summarize_stability(folds)
    final_feature_set=None
    # Predeclared sensitivity checks use development folds only. They do not choose the primary model.
    sensitivity=[]
    for name,cfg in SENSITIVITY[1:]:
        for z in folds:
            spec=fit_spec(X.iloc[z['train_ix']],y.iloc[z['train_ix']],X.iloc[z['validation_ix']],FEATURES,cfg)
            pp=predict(spec,spec['apply_woe'])
            sensitivity.append({'variant':name,'split':z['split'],'selected_features':'|'.join(spec['features']),**metrics(y.iloc[z['validation_ix']],pp)})
    # Fit primary specification on the complete development set once; final test remains untouched.
    final=fit_spec(X.iloc[dev],y.iloc[dev],X.iloc[test],FEATURES,PRIMARY); final_feature_set=final['features']; testp=predict(final,final['apply_woe'])
    tm=metrics(y.iloc[test],testp); tm.update(calibration(y.iloc[test],testp)); tm.update({'n_test':len(test),'defaults_test':int(y.iloc[test].sum()),'model_features':final['features'],'status':'single final evaluation; no variant selection on test'})
    # Compute explicit bin and sensitivity gates before writing any results.
    bdf=pd.DataFrame(allbin)
    bin_support_ok=bool(((bdf.population>=bdf.min_bin_population_required)&(bdf.good>=bdf.min_good_required)&(bdf.bad>=bdf.min_bad_required)).all())
    monotone_checks=[]
    for (_, _),group in bdf[~bdf.missing_bin].groupby(['split','feature']):
        group=group.sort_values('bin_index'); rates=group.event_rate.to_numpy(); direction=group.direction.iloc[0]
        monotone_checks.append(bool(np.all(np.diff(rates)>=-1e-12) if direction=='increasing' else np.all(np.diff(rates)<=1e-12)))
    monotone_ok=bool(monotone_checks and all(monotone_checks))
    sensdf=pd.DataFrame(sensitivity)
    sens_agg=sensdf.groupby('variant').agg(auc_mean=('auc','mean'),auc_sd=('auc','std'),brier_mean=('brier','mean'),brier_sd=('brier','std'),log_loss_mean=('log_loss','mean'),log_loss_sd=('log_loss','std'),feature_sets=('selected_features',lambda x:' || '.join(sorted(set(x))))).reset_index()
    primary_means={'auc':float(np.mean([z['auc'] for z in val])),'brier':float(np.mean([z['brier'] for z in val])),'log_loss':float(np.mean([z['log_loss'] for z in val]))}
    sensitivity_ok=bool(((sens_agg.auc_mean>=primary_means['auc']-.05)&(sens_agg.brier_mean<=primary_means['brier']+.01)&(sens_agg.log_loss_mean<=primary_means['log_loss']+.03)).all())
    def cutpoint_stability(group):
        arrays=[json.loads(v) for v in group.normalized_cutpoints_json]
        common=min(map(len,arrays)) if arrays else 0
        sd=[float(np.std([a[j] for a in arrays],ddof=1)) if len(arrays)>1 else 0.0 for j in range(common)]
        return pd.Series({'numeric_bins_mean':float(group.numeric_bin_count.mean()),'numeric_bins_sd':float(group.numeric_bin_count.std(ddof=1)),'direction_consistency':float(max((group.direction=='increasing').mean(),(group.direction=='decreasing').mean())),'common_cutpoints':common,'mean_normalized_cutpoint_sd':float(np.mean(sd)) if sd else None})
    bin_stability_summary=bs.groupby('feature').apply(cutpoint_stability,include_groups=False).reset_index()
    final_bin_summary=bin_stability_summary[bin_stability_summary.feature.isin(final_feature_set)]
    bin_stability_ok=bool((final_bin_summary.numeric_bins_sd.fillna(0)<=1.0).all()&(final_bin_summary.mean_normalized_cutpoint_sd.fillna(0)<=.25).all())
    # Acceptance gates are prespecified, not tuned from test AUC.
    vv=pd.DataFrame(val); gate_features=fs[fs.feature.isin(final_feature_set)]
    selected=gate_features.selection_frequency>=0.80
    signok=gate_features.coefficient_sign_consistency>=0.90
    direction_consistency=np.maximum(gate_features.direction_increasing_frequency,gate_features.direction_decreasing_frequency)
    dir_ok=(direction_consistency>=0.80).all()
    metric_sd={m:float(vv[m].std(ddof=1)) for m in ('auc','brier','log_loss')}
    gates={
      'minimum_real_sample_and_events':len(df)>=1000 and int(y.sum())>=100,
      'all_selected_features_semantically_allowed':all(SEM[f] in ('DIRECT','STRONG_PROXY') for f in final['features']),
      'feature_selection_frequency_at_least_80pct':bool(selected.all()),
      'coefficient_sign_consistency_at_least_90pct':bool(signok.all()),
      'binning_direction_consistency_at_least_80pct':bool(dir_ok),
      'all_training_bins_meet_minimum_population_and_event_counts':bin_support_ok,
      'all_numeric_bins_obey_learned_monotone_direction':monotone_ok,
      'selected_feature_cutpoints_stable_across_folds':bin_stability_ok,
      'validation_auc_split_sd_at_most_0_03':metric_sd['auc']<=0.03,
      'predeclared_sensitivity_variants_within_fixed_diagnostic_tolerances':sensitivity_ok,
      'validation_brier_and_logloss_better_than_prevalence_baseline':float(vv.brier.mean())<float(np.mean((y.iloc[dev]-y.iloc[dev].mean())**2)) and float(vv.log_loss.mean())<float(-(y.iloc[dev].mean()*np.log(y.iloc[dev].mean())+(1-y.iloc[dev].mean())*np.log(1-y.iloc[dev].mean()))),
      'test_directionally_consistent_and_brier_better_than_baseline':tm['auc']>0.5 and tm['brier']<(float(y.iloc[dev].mean())*(1-float(y.iloc[dev].mean()))),
      'test_calibration_slope_intercept_in_prespecified_bounds':0.7<=tm['calibration_slope']<=1.3 and abs(tm['calibration_intercept'])<=0.2,
      'temporal_out_of_time_validation_available':False,
      'current_market_or_external_population_replication_available':False,
    }
    status='PHASE_2B6_ACCEPTANCE_PASSED' if all(gates.values()) else 'PHASE_2B6_INCONCLUSIVE'
    pd.DataFrame(splitrows).to_csv(OUT/'split_registry.csv',index=False); vv.to_csv(OUT/'validation_metrics.csv',index=False)
    fs.to_csv(OUT/'feature_stability.csv',index=False); cs.to_csv(OUT/'coefficient_stability.csv',index=False); bs.to_csv(OUT/'bin_stability.csv',index=False)
    pd.DataFrame(allbin).to_csv(OUT/'constrained_binning_summary.csv',index=False); pd.DataFrame(sensitivity).to_csv(OUT/'robustness_sensitivity.csv',index=False)
    sens_agg.to_csv(OUT/'robustness_sensitivity_summary.csv',index=False)
    bin_stability_summary.to_csv(OUT/'bin_stability_summary.csv',index=False)
    (OUT/'test_metrics.json').write_text(json.dumps(tm,indent=2))
    (OUT/'acceptance_gates.json').write_text(json.dumps({'status':status,'criteria':gates,'thresholds':{'selection_frequency_min':.80,'sign_consistency_min':.90,'direction_consistency_min':.80,'validation_auc_sd_max':.03,'test_calibration_slope':[.7,1.3],'test_calibration_intercept_abs_max':.2,'minimum_good_and_bad_per_bin':[PRIMARY['min_good'],PRIMARY['min_bad']],'minimum_bin_population_share':PRIMARY['min_bin_share'],'sensitivity_auc_drop_max':.05,'sensitivity_brier_increase_max':.01,'sensitivity_logloss_increase_max':.03,'bin_count_sd_max':1.0,'normalized_cutpoint_sd_max':.25},'sensitivity_variants_are_diagnostic_only':True,'test_used_for_variant_choice':False},indent=2))
    sm={'status':status,'outer_split_seed':SEED,'input_sha256':hashlib.sha256(INPUT.read_bytes()).hexdigest(),'borrowers':len(df),'defaults':int(y.sum()),'nondefaults':int((y==0).sum()),'primary_config':PRIMARY,'validation':{m:{'mean':float(vv[m].mean()),'sd':float(vv[m].std(ddof=1))} for m in ('auc','gini','ks','brier','log_loss')},'test':tm,'gates':gates,'feature_selection':fs.to_dict(orient='records'),'scope':'hardening and robustness only; no dataset change and no AUC-led variant selection','limitations':['UCI contains no calendar-based out-of-time cohort','single historic Taiwan credit-card population','feature semantics and population do not establish production parser equivalence','bins may be forced to one numeric bin where event minima cannot otherwise be satisfied; recorded bin counts make this visible']}
    (OUT/'phase2b6_summary.json').write_text(json.dumps(sm,indent=2))
    report=f'''# Phase 2B.6 — constrained scorecard hardening\n\n**Status: {status}**\n\n## Frozen scope\n\nThe UCI source file, target, feature derivations, outer 80/20 borrower split seed, production model, production binning, manifest, and application code were not changed. This phase only adds train-fold constrained binning, stability diagnostics, robustness checks, and explicit gates. Candidate models were not ranked by AUC.\n\n## Training-only controls\n\nWithin each development fold, numeric quantile pre-bins are pooled to satisfy minimum population and minimum good/default counts, then adjacent bins are pooled until the observed default rate is monotone. The direction is selected from that fit fold alone by minimum training-only monotonic violation. Missing values require their own supported learned bin; unsupported missing bins or unseen application bins fail closed. WoE uses ln(P(bin|nondefault)/P(bin|default)) with Jeffreys 0.5 smoothing. IV screening (floor {PRIMARY['iv_floor']}) and Spearman redundancy pruning (cap {PRIMARY['correlation_cap']}) are also fit-fold-only.\n\nPrimary minima: at least {PRIMARY['min_good']} nondefaults and {PRIMARY['min_bad']} defaults per numeric bin, and at least {PRIMARY['min_bin_share']:.0%} of training observations. If the data cannot satisfy them, adjacent bins collapse; no test-informed exception is allowed.\n\n## Validation and stability\n\nTen repeated development folds use the previously fixed seeds and split membership process. Validation metrics: {json.dumps(sm['validation'])}. Feature selection frequency, coefficient sign/magnitude, selected monotone direction, bin count, cut points, and training bin event rates are in the CSV outputs.\n\n## Sensitivity checks\n\nThe following were predeclared and run on development validation folds only: maximum three bins; minimum 50 defaults and 50 nondefaults per bin; and removal of the payment-to-statement proxy. They are diagnostics and are not used to select a winner. Results are in `robustness_sensitivity.csv`. The outer test receives only the primary specification once: {json.dumps(tm)}.\n\n## Acceptance\n\nThe criteria and observed pass/fail values are in `acceptance_gates.json`. Empirical acceptance requires all gates, including selection frequency >=80%, coefficient sign consistency >=90%, monotone-direction consistency >=80%, validation AUC SD <=0.03, acceptable probability quality, a directionally consistent untouched test, and calibration within predeclared bounds. Out-of-time and external-population validation are also required for broad empirical support; these are unavailable for this single-vintage UCI dataset, so Phase 2B.6 cannot establish generalizable PRISM empirical support even if the within-sample gates pass.\n\nNo Phase 2C work is started. No production promotion is recommended.\n'''
    (OUT/'phase2b6_report.md').write_text(report)

if __name__=='__main__': run()
