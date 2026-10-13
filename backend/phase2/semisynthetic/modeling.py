"""Parent-weighted training-only WoE and small logistic scorecard."""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize
from scipy.stats import rankdata

from phase2.phase2b import _metrics, score_from_pd
from phase2.semisynthetic.feature_extraction import FEATURES


def _weighted_median(x, w):
    ok=np.isfinite(x)&np.isfinite(w)&(w>0)
    if not ok.any(): return None
    order=np.argsort(x[ok]); xx=x[ok][order]; ww=w[ok][order]
    return float(xx[np.searchsorted(np.cumsum(ww),ww.sum()/2,side="left")])


def _bins(x, cut):
    out=np.full(len(x),-1,dtype=int)
    finite=np.isfinite(x)
    if cut is not None: out[finite]=(x[finite]>cut).astype(int)
    return out


def _weighted_spearman(x, y, weights):
    """Spearman-style correlation with parent-family weights."""
    rx, ry = rankdata(x), rankdata(y)
    w = np.asarray(weights, float)
    w = w / w.sum()
    mx, my = np.sum(w * rx), np.sum(w * ry)
    vx, vy = np.sum(w * (rx-mx)**2), np.sum(w * (ry-my)**2)
    if vx <= 0 or vy <= 0:
        return np.nan
    return float(np.sum(w * (rx-mx) * (ry-my)) / np.sqrt(vx*vy))


def fit_woe(train_records: list[dict], sample_weights: np.ndarray):
    y=np.array([int(r["target"]) for r in train_records],int)
    binners={}; ivs={}; transformed={}
    good_total=float(sample_weights[y==0].sum()); bad_total=float(sample_weights[y==1].sum())
    for feature in FEATURES:
        x=np.array([r["features"].get(feature,np.nan) for r in train_records],float)
        cut=_weighted_median(x,sample_weights)
        group=_bins(x,cut); groups=sorted(set(group.tolist())); k=len(groups); woe={}; iv=0.
        for g in groups:
            m=group==g
            good=float(sample_weights[(y==0)&m].sum()); bad=float(sample_weights[(y==1)&m].sum())
            gd=(good+.5)/(good_total+.5*k); bd=(bad+.5)/(bad_total+.5*k)
            val=math.log(gd/bd); woe[int(g)]=val; iv+=(gd-bd)*val
        binners[feature]={"cut":cut,"woe":woe,"fallback_woe":0.0,"fallback":"training-derived neutral WoE for a validation-only absent bin"}
        ivs[feature]=iv
        transformed[feature]=np.array([woe.get(int(g),0.0) for g in group],float)
    order=sorted(FEATURES,key=lambda f:(-ivs[f],f)); selected=[]
    for feature in order:
        x=transformed[feature]
        if not np.isfinite(x).all() or np.std(x)==0: continue
        if any(abs(_weighted_spearman(x,transformed[f],sample_weights))>=.8 for f in selected):
            continue
        selected.append(feature)
        if len(selected)>=2: break
    if not selected: selected=[order[0]]
    X=np.column_stack([transformed[f] for f in selected])
    return selected,binners,ivs,X,y


def transform(records: list[dict], selected: list[str], binners: dict):
    cols=[]
    for feature in selected:
        x=np.array([r["features"].get(feature,np.nan) for r in records],float)
        groups=_bins(x,binners[feature]["cut"])
        cols.append(np.array([binners[feature]["woe"].get(int(g),binners[feature]["fallback_woe"]) for g in groups],float))
    return np.column_stack(cols)


def fit_logistic(X, y, weights, l2=1.0):
    X1=np.column_stack([np.ones(len(X)),X])
    def obj(beta):
        z=np.clip(X1@beta,-35,35)
        p=1/(1+np.exp(-z))
        loss=np.sum(weights*(np.logaddexp(0,z)-y*z))+.5*l2*np.sum(beta[1:]**2)
        grad=X1.T@(weights*(p-y)); grad[1:]+=l2*beta[1:]
        return float(loss),grad
    res=minimize(obj,np.zeros(X1.shape[1]),jac=True,method="BFGS",options={"maxiter":500,"gtol":1e-8})
    if not np.isfinite(res.x).all(): raise RuntimeError("Nonfinite scorecard coefficient")
    return res.x,bool(res.success),str(res.message)


def scorecard_fit(train_records, sample_weights):
    # Exact weighted compression is algebraically equivalent to repeated rows
    # and makes the no-op duplication control numerically invariant.
    merged={}; unique=[]; merged_weights=[]
    for record,weight in zip(train_records,sample_weights):
        vals=tuple(None if not np.isfinite(record["features"].get(f,np.nan)) else float(record["features"][f]) for f in FEATURES)
        key=(int(record["target"]),vals)
        if key not in merged:
            merged[key]=len(unique); unique.append(record); merged_weights.append(0.0)
        merged_weights[merged[key]]+=float(weight)
    train_records=unique; sample_weights=np.asarray(merged_weights,float)
    selected,binners,ivs,X,y=fit_woe(train_records,sample_weights)
    beta,converged,message=fit_logistic(X,y,sample_weights,l2=1.0)
    return {"selected":selected,"binners":binners,"ivs":ivs,"beta":beta,"converged":converged,"message":message}


def evaluate(model, records):
    X=transform(records,model["selected"],model["binners"])
    z=model["beta"][0]+X@model["beta"][1:]
    p=1/(1+np.exp(-np.clip(z,-35,35)))
    y=np.array([int(r["target"]) for r in records],int)
    return {**_metrics(y,p),"linear_predictors":z,"pd":p,"scores":score_from_pd(p),"woe_matrix":X}


def family_weights(records, naive=False):
    if naive:return np.ones(len(records),float)
    counts={}
    for r in records: counts[r["parent_loan_id"]]=counts.get(r["parent_loan_id"],0)+1
    return np.array([1.0/counts[r["parent_loan_id"]] for r in records],float)


def records_from_parents(parents):
    return [{"parent_loan_id":p["parent_loan_id"],"target":p["target"],"features":p["features"],"is_synthetic":False,"label_source":"OBSERVED_BERKA"} for p in parents]


def records_from_descendants(descendants):
    return [{"parent_loan_id":d["parent_loan_id"],"target":d["target"],"features":d["features"],"is_synthetic":True,"label_source":"PARENT_INHERITED"} for d in descendants]
