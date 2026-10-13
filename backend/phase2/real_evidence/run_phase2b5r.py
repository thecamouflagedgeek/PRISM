"""Isolated UCI behavioral WoE/LR evidence experiment. No production imports."""
from __future__ import annotations
import json, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import spearmanr

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'real_evidence'/'inputs'/'uci_default_of_credit_card_clients.csv'
OUT=ROOT/'outputs'/'phase2b5r'; OUT.mkdir(parents=True,exist_ok=True)
SEED=20261007
FEATURES=['worst_delinquency_level','months_with_delinquency','recent_delinquency_level','mean_statement_balance','payment_to_statement_ratio']
SEM={FEATURES[0]:'DIRECT',FEATURES[1]:'DIRECT',FEATURES[2]:'DIRECT',FEATURES[3]:'DIRECT',FEATURES[4]:'STRONG_PROXY'}
TARGET='default payment next month'

def sigmoid(x): return expit(np.clip(x,-35,35))
def metrics(y,p):
    y=np.asarray(y,int); p=np.clip(np.asarray(p,float),1e-12,1-1e-12)
    pos=np.sort(p[y==1]); neg=np.sort(p[y==0]);
    # Mann-Whitney rank AUC, ties receive half credit.
    ranks=pd.Series(np.r_[p[y==1],p[y==0]]).rank(method='average').to_numpy()
    n1=(y==1).sum(); n0=(y==0).sum(); auc=(ranks[:n1].sum()-n1*(n1+1)/2)/(n1*n0)
    fpr=np.r_[0,np.arange(1,n0+1)/n0,1]; tpr=np.r_[0,np.arange(1,n1+1)/n1,1]
    # exact KS from unique thresholds
    ks=max(abs((p[y==1,None]>=np.sort(p)[None,:]).mean(axis=0)-(p[y==0,None]>=np.sort(p)[None,:]).mean(axis=0)))
    return {'auc':float(auc),'gini':float(2*auc-1),'ks':float(ks),'brier':float(np.mean((p-y)**2)),'log_loss':float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),'observed_default_rate':float(y.mean()),'mean_predicted_pd':float(p.mean())}
def derive(df):
    # PAY_0 is September, PAY_2..PAY_6 are August..April.
    pays=df[['PAY_0','PAY_2','PAY_3','PAY_4','PAY_5','PAY_6']].astype(float)
    bills=df[[f'BILL_AMT{i}' for i in range(1,7)]].astype(float)
    pays=pays.replace({-2:0,-1:0})
    x=pd.DataFrame(index=df.index)
    x['worst_delinquency_level']=pays.max(axis=1)
    x['months_with_delinquency']=(pays>0).sum(axis=1)
    x['recent_delinquency_level']=pays['PAY_0']
    x['mean_statement_balance']=bills.mean(axis=1)
    # Align recent-to-old monthly arrays; require positive total obligation; missing is explicit.
    pa=df[[f'PAY_AMT{i}' for i in range(1,7)]].astype(float)
    denom=bills.clip(lower=0).sum(axis=1)
    ratio=pa.sum(axis=1)/denom.where(denom>0)
    x['payment_to_statement_ratio']=ratio.replace([np.inf,-np.inf],np.nan)
    return x
def stratified_split(y, test_frac, seed):
    rng=np.random.default_rng(seed); tr=[]; te=[]
    for c in (0,1):
        ix=np.flatnonzero(np.asarray(y)==c); rng.shuffle(ix); n=int(round(len(ix)*test_frac)); te.extend(ix[:n]); tr.extend(ix[n:])
    return np.array(sorted(tr)),np.array(sorted(te))
def fit_transform_bins(train, apply, feature):
    s=train[feature].astype(float); non=s.dropna(); edges=np.unique(non.quantile(np.linspace(0,1,5)).to_numpy())
    if len(edges)<2: edges=np.array([-np.inf,np.inf])
    else: edges[0]=-np.inf; edges[-1]=np.inf
    def labels(z):
        out=pd.cut(z.astype(float),bins=edges,include_lowest=True,duplicates='drop').astype('object')
        out[z.isna()]='MISSING'; return out.astype(str)
    a=labels(train[feature]); b=labels(apply[feature]); y=train[TARGET].astype(int)
    tab=pd.crosstab(a,y).reindex(columns=[0,1],fill_value=0)
    # Jeffreys smoothing prevents infinite WoE; missing bin is learned only if present in training.
    good=(tab[0]+0.5)/(tab[0].sum()+0.5*len(tab)); bad=(tab[1]+0.5)/(tab[1].sum()+0.5*len(tab))
    w=np.log(good/bad); mapping=w.to_dict()
    unknown=set(b.unique())-set(mapping)
    if unknown: raise ValueError(f'Unlearned bins for {feature}: {unknown}')
    summary=[]
    for k,row in tab.iterrows(): summary.append({'feature':feature,'bin':str(k),'good':int(row[0]),'bad':int(row[1]),'population':int(row.sum()),'event_rate':float(row[1]/row.sum()),'woe_good_over_bad':float(w[k]),'iv_component':float((good[k]-bad[k])*w[k]),'cut_points':json.dumps(edges.tolist())})
    return b.map(mapping).astype(float),mapping,summary
def transform(trainx, applyx, ytrain):
    tmp=trainx.copy(); tmp[TARGET]=np.asarray(ytrain); out=pd.DataFrame(index=applyx.index); trainout=pd.DataFrame(index=trainx.index); maps={}; rows=[]
    for f in FEATURES:
        z,m,r=fit_transform_bins(tmp,applyx,f); out[f]=z
        # Map training values through the same train-derived quantile cuts, including the learned missing bin.
        non=trainx[f].dropna(); edges=np.unique(non.quantile(np.linspace(0,1,5)).to_numpy())
        if len(edges)<2: edges=np.array([-np.inf,np.inf])
        else: edges[0]=-np.inf; edges[-1]=np.inf
        labels=pd.cut(trainx[f].astype(float),bins=edges,include_lowest=True,duplicates='drop').astype('object'); labels[trainx[f].isna()]='MISSING'
        trainout[f]=labels.astype(str).map(m)
        maps[f]=m; rows+=r
    return trainout.astype(float),out.astype(float),maps,rows
def fit_lr(x,y,l2=1.0):
    X=np.column_stack([np.ones(len(x)),x.to_numpy(float)]); y=np.asarray(y,float)
    def loss(b):
        z=X@b; return np.logaddexp(0,z).sum()-y@z+0.5*l2*np.sum(b[1:]**2)
    def grad(b): return X.T@(sigmoid(X@b)-y)+np.r_[0,l2*b[1:]]
    res=minimize(loss,np.zeros(X.shape[1]),jac=grad,method='BFGS')
    if not res.success and np.linalg.norm(grad(res.x))>1e-4: raise RuntimeError(res.message)
    return res.x
def calibration(y,p):
    y=np.asarray(y,int); p=np.clip(p,1e-8,1-1e-8); lp=np.log(p/(1-p))
    def objective(b):
        z=b[0]+b[1]*lp
        return np.logaddexp(0,z).sum()-y@z
    r=minimize(objective,[0,1],method='BFGS')
    return {'calibration_intercept':float(r.x[0]),'calibration_slope':float(r.x[1])}

def main():
    df=pd.read_csv(INPUT); y=df[TARGET].astype(int); X=derive(df)
    if df['ID'].nunique()!=len(df) or df[TARGET].isna().any(): raise ValueError('Borrower key/target validation failed')
    # Deterministic untouched borrower-level stratified holdout; no external time cohort exists.
    dev_ix,test_ix=stratified_split(y,.20,SEED); splits=[]; valrows=[]; selected=[]; coefs=[]; allbin=[]; allwoe=[]
    for k in range(10):
        trrel,varel=stratified_split(y.iloc[dev_ix].to_numpy(),.20,SEED+100+k); tri=dev_ix[trrel]; vai=dev_ix[varel]
        tx,vx,maps,bins=transform(X.iloc[tri],X.iloc[vai],y.iloc[tri]); model=fit_lr(tx,y.iloc[tri]); p=sigmoid(np.column_stack([np.ones(len(vx)),vx.to_numpy()])@model)
        valrows.append({'split':k+1,**metrics(y.iloc[vai],p)})
        splits.append({'split':k+1,'train_ids_sha256':hashlib.sha256(','.join(map(str,df.ID.iloc[tri])).encode()).hexdigest(),'validation_ids_sha256':hashlib.sha256(','.join(map(str,df.ID.iloc[vai])).encode()).hexdigest(),'train_n':len(tri),'validation_n':len(vai),'seed':SEED+100+k})
        selected.extend(FEATURES); allbin+=bins
        for j,f in enumerate(FEATURES): coefs.append({'split':k+1,'feature':f,'coefficient':float(model[j+1]),'sign':int(np.sign(model[j+1]))})
    # Final model is fit once on all development records; test is used only for final evaluation.
    tx,vx,maps,bins=transform(X.iloc[dev_ix],X.iloc[test_ix],y.iloc[dev_ix]); beta=fit_lr(tx,y.iloc[dev_ix]); p=sigmoid(np.column_stack([np.ones(len(vx)),vx.to_numpy()])@beta)
    testm=metrics(y.iloc[test_ix],p); testm.update(calibration(y.iloc[test_ix],p)); testm.update({'n_test':len(test_ix),'defaults_test':int(y.iloc[test_ix].sum()),'status':'untouched borrower-level stratified holdout; no separate calibrator'})
    pd.DataFrame(splits).to_csv(OUT/'split_registry.csv',index=False)
    pd.DataFrame(valrows).to_csv(OUT/'validation_metrics.csv',index=False)
    pd.DataFrame(allbin+bins).to_csv(OUT/'binning_summary.csv',index=False)
    pd.DataFrame(allbin+bins).to_csv(OUT/'woe_summary.csv',index=False)
    fs=pd.DataFrame({'feature':FEATURES,'semantic_mapping':[SEM[f] for f in FEATURES],'selection_count':['NOT_ESTIMATED']*len(FEATURES),'selection_frequency':['NOT_ESTIMATED']*len(FEATURES),'selection_basis':['predeclared compact semantic candidate set; no fold-local feature selection was claimed']*len(FEATURES)})
    fs.to_csv(OUT/'feature_selection_stability.csv',index=False)
    cf=pd.DataFrame(coefs); cf.groupby('feature').agg(coefficient_mean=('coefficient','mean'),coefficient_sd=('coefficient','std'),sign_consistency=('sign',lambda z:max((z>0).mean(),(z<0).mean()))).reset_index().to_csv(OUT/'coefficient_stability.csv',index=False)
    (OUT/'test_metrics.json').write_text(json.dumps(testm,indent=2))
    # Calibration table on test, descriptive deciles.
    cal=pd.DataFrame({'pd':p,'y':y.iloc[test_ix].to_numpy()}); cal['decile']=pd.qcut(cal.pd,10,labels=False,duplicates='drop')+1
    cal.groupby('decile',observed=True).agg(n=('y','size'),mean_pd=('pd','mean'),observed_default_rate=('y','mean')).assign(calibration_gap=lambda d:d.observed_default_rate-d.mean_pd).reset_index().to_csv(OUT/'calibration_analysis.csv',index=False)
    # Score convention: score=600 + 50/ln2*ln(good:bad odds / 20).
    odds=(1-p)/p; scores=600+50/np.log(2)*np.log(odds/20)
    anchors={str(o):float(600+50/np.log(2)*np.log(o/20)) for o in (20,40,10)}
    traces=[]; reason=[]
    for ix in test_ix[:5]:
        _,applied,_,_=transform(X.iloc[dev_ix],X.iloc[[ix]],y.iloc[dev_ix]); row=X.iloc[ix]; w={f:float(applied[f].iloc[0]) for f in FEATURES}; terms={f:float(beta[j+1]*w[f]) for j,f in enumerate(FEATURES)}
        logit=float(beta[0]+sum(terms.values())); pdhat=float(sigmoid(logit)); score=float(600+50/np.log(2)*np.log(((1-pdhat)/pdhat)/20))
        traces.append({'borrower_id':int(df.ID.iloc[ix]),'raw_history':{c:float(df.iloc[ix][c]) for c in ['PAY_0','PAY_2','PAY_3','PAY_4','PAY_5','PAY_6','BILL_AMT1','BILL_AMT2','BILL_AMT3','BILL_AMT4','BILL_AMT5','BILL_AMT6','PAY_AMT1','PAY_AMT2','PAY_AMT3','PAY_AMT4','PAY_AMT5','PAY_AMT6']},'aggregated_features':{f:None if pd.isna(row[f]) else float(row[f]) for f in FEATURES},'woe':w,'coefficients':{f:float(beta[j+1]) for j,f in enumerate(FEATURES)},'contributions_logit':terms,'intercept':float(beta[0]),'reconstructed_logit':logit,'pd':pdhat,'good_bad_odds':float((1-pdhat)/pdhat),'score':score})
        reason.append({'borrower_id':int(df.ID.iloc[ix]),'reason_codes':[{'feature':f,'raw_value':None if pd.isna(row[f]) else float(row[f]),'woe':w[f],'coefficient':float(beta[j+1]),'adverse_logit_contribution':terms[f]} for j,f in sorted(enumerate(FEATURES),key=lambda z:terms[z[1]],reverse=True) if terms[f]>0][:3]})
    (OUT/'score_traces.json').write_text(json.dumps({'anchors':anchors,'traces':traces},indent=2)); (OUT/'reason_code_traces.json').write_text(json.dumps(reason,indent=2))
    (OUT/'dataset_selection.md').write_text('# Dataset selection\n\nSelected the UCI Default of Credit Card Clients workbook after rejecting Home Credit 2024 and AmEx for this primary experiment: the former is competition-use restricted and unavailable locally; the latter has anonymized predictor semantics and is also competition-governed. UCI is locally available, CC BY 4.0, documents monthly payment and statement behavior, has 30,000 unique customers and 6,636 defaults. It is a single 2005 cohort, so it supports point-in-time behavioral validation but not out-of-time generalization or current-market validation.\n')
    schema={'version':'2','target':TARGET,'prediction_cutoff':'After September 2005 statement; October 2005 next-month interpretation is inferred from documentation.','features':[{'name':f,'mapping':SEM[f],'concept':{'worst_delinquency_level':'payment behavior / worst delinquency','months_with_delinquency':'payment behavior / delinquency frequency','recent_delinquency_level':'payment behavior / recent delinquency','mean_statement_balance':'outflow / obligation burden','payment_to_statement_ratio':'payment-to-obligation ratio'}[f]} for f in FEATURES],'excluded':['ID','SEX','EDUCATION','MARRIAGE','AGE','target'],'woe_convention':'ln(P(bin|nondefault)/P(bin|default)); Jeffreys 0.5 smoothing'}
    (OUT/'feature_schema_v2.json').write_text(json.dumps(schema,indent=2))
    forb={'forbidden':['ID','default payment next month','any variables recorded after September 2005 prediction cutoff','target-derived aggregates','post-outcome collection/recovery/write-off fields'],'missing_policy':'missing is a distinct learned bin; unseen evaluation bin raises error; no WoE=0 fallback'}
    (OUT/'forbidden_features.json').write_text(json.dumps(forb,indent=2))
    audit={'dataset':'UCI Default of Credit Card Clients','source_sha256':'30c6be3abd8dcfd3e6096c828bad8c2f011238620f5369220bd60cfc82700933','rows':len(df),'unique_borrowers':int(df.ID.nunique()),'defaults':int(y.sum()),'nondefaults':int((y==0).sum()),'event_rate':float(y.mean()),'missing_cells':int(df.isna().sum().sum()),'duplicate_rows':int(df.duplicated().sum()),'history':'April through September 2005 monthly repayment status, bill statements, and payment amounts','outcome':'default payment next month; October 2005 is inferred from source variable chronology','longitudinal_rows_per_borrower':1,'independent_monthly_observations':6,'temporal_design':'random stratified borrower holdout; pre-outcome feature history fixed for all records; no out-of-time cohort','source_license':'CC BY 4.0','feature_semantics':'UCI documentation identifies payment status, statement balances, and payments; demographic fields excluded'}
    (OUT/'dataset_audit.json').write_text(json.dumps(audit,indent=2))
    (OUT/'dataset_audit.md').write_text('# Dataset and leakage audit\n\n'+json.dumps(audit,indent=2)+'\n\nThe source is cross-sectional at borrower level but each borrower has six ordered monthly history fields. The target is future relative to this fixed history. No actual origination/event timestamps or independent calendar cohorts are provided; October 2005 outcome month is inferred, and temporal generalization cannot be tested.\n')
    vv=pd.DataFrame(valrows); agg={c:{'mean':float(vv[c].mean()),'sd':float(vv[c].std(ddof=1))} for c in ['auc','gini','ks','brier','log_loss']}
    summary={'status':'PHASE_2B5R_INCONCLUSIVE','dataset':audit['dataset'],'validation':agg,'test':testm,'features':FEATURES,'no_separate_calibrator':'NO_SEPARATE_CALIBRATOR_RECOMMENDED','score_anchors':anchors,'model':'L2 Logistic Regression on fold-local WoE features, fixed L2 penalty=1.0; 10 repeated development splits','limitations':['single vintage/population; no out-of-time cohort','fixed prediction cutoff; outcome-month mapping inferred','feature selection stability is not estimated; five semantic candidates were predeclared','minimal quantile bins are learned fold-locally; monotonicity/minimum-bin-event constraints not enforced','no separate calibration subset or calibrator; raw PD assessed only','the UCI dataset does not establish production feature/parser equivalence']}
    (OUT/'phase2b5r_summary.json').write_text(json.dumps(summary,indent=2))
    report=f'''# Phase 2B.5-R report\n\n## Status: {summary['status']}\n\n1. **Dataset:** UCI Default of Credit Card Clients ([UCI dataset page](https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients)), chosen for locally available, documented, real next-month default outcomes and six months of meaningful payment/statement history. Home Credit 2024 ([competition rules](https://www.kaggle.com/c/home-credit-credit-risk-model-stability/rules)) and AmEx ([competition data](https://www.kaggle.com/competitions/amex-default-prediction/data?select=train_labels.csv)) were not selected: competition use/access restrictions and unavailable local files; AmEx's anonymized features also prevent direct semantic mapping.\n2. **Borrowers/events:** {len(df):,} unique borrowers; {int(y.sum()):,} defaults; {int((y==0).sum()):,} nondefaults ({y.mean():.2%}). This is about {len(df)/231:.1f}x the Berka borrower count and {int(y.sum())/31:.1f}x its default count.\n3. **Outcome/time:** default payment next month; observed predictors are April–September 2005 payment status, statement balance, and payment amount. October 2005 is inferred from the documented chronology.\n4. **Mapped features:** {', '.join(FEATURES)}. Direct maps cover delinquency status/frequency, statement balance; payment-to-statement ratio is a strong proxy. Demographics (age, sex, education, marriage), ID, and target excluded.\n5. **Leakage:** fixed pre-outcome monthly history; borrower-level stratified test holdout, with all bin edges/WoE/model fit on development folds only. No post-cutoff columns used. No out-of-time cohort exists.\n6. **Repeated validation:** {json.dumps(agg)}. Test: {json.dumps(testm)}. Test cohort untouched until final scoring.\n7. **Stability:** coefficients and fold metrics are reported. Feature-selection frequency is explicitly not estimated because five candidates were predeclared; bin minimum-count and monotonic constraints were not enforced. Dataset does not offer calendar cohorts; results establish only within-vintage random-holdout stability.\n8. **Calibration:** raw LR PD assessed; no separate calibrator recommended. Calibration coefficients/reliability deciles are diagnostic, not proof of temporal calibration.\n9. **Score/reasons:** score is reconstructible from PD using base 600, PDO 50, base good:bad odds 20:1; anchors are {anchors}. Five test traces and contribution-based reason traces are saved. Contributions use beta×WoE, not SHAP.\n10. **Berka comparison:** substantially more independent events and lower observed sampling uncertainty are available, but no raw AUC equivalence is claimed. Berka's real longitudinal loan cohort has stronger origination-linked semantic context; UCI has a single old Taiwan credit-card vintage and only one borrower row each.\n11. **Phase 2C:** do not proceed. Status remains inconclusive because there is no out-of-time validation, no current-market replication, and feature-selection/bin stability evidence is limited. Phase 2C production/parser equivalence is not authorized by this result.\n12. **Limits:** historical population (Taiwan, 2005), one outcome definition, no calendar event cohort, ratio feature is a proxy, quantile bins need further governance, and environment's pinned 3.12 test restoration failed.\n\nProduction model/scorer/artifacts were not edited by this experiment. Phase 2B remains INCONCLUSIVE and Phase 2B.5-S remains INCONCLUSIVE.\n'''
    (OUT/'phase2b5r_report.md').write_text(report)
if __name__=='__main__': main()
