"""
PRISM – Model, Calibration & Score Validator  (Parts 4, 5, 6)
"""
from __future__ import annotations
import warnings
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss, roc_curve
warnings.filterwarnings("ignore")

_PDO=50; _BASE_SCORE=600; _BASE_ODDS=19
_FACTOR=_PDO/np.log(2); _OFFSET=_BASE_SCORE-_FACTOR*np.log(_BASE_ODDS)
FEATURES=["credit_debit_ratio","cashflow_cv","net_to_gross_ratio","utility_stability","min_balance"]

# ── PART 4 ───────────────────────────────────────────────────

@dataclass
class ModelValidationReport:
    auc: float; gini: float; ks_statistic: float; ks_threshold: float; brier_score: float
    coefficient_table: pd.DataFrame; vif_table: pd.DataFrame
    warnings: List[str] = field(default_factory=list); passed: bool = True

def _ks(y_true, y_prob):
    fpr,tpr,thr = roc_curve(y_true, y_prob)
    idx = np.argmax(tpr-fpr)
    return float(np.max(tpr-fpr)), float(thr[idx])

def _vif(X: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    cols=list(X.columns)
    for col in cols:
        others=[c for c in cols if c!=col]
        if not others: rows.append({"feature":col,"VIF":np.nan}); continue
        r2=LinearRegression().fit(X[others],X[col]).score(X[others],X[col])
        rows.append({"feature":col,"VIF":round(1/(1-r2) if r2<1 else np.inf,3)})
    return pd.DataFrame(rows)

def _wald(model, X, y):
    n=len(X); p_hat=model.predict_proba(X)[:,1]; W=p_hat*(1-p_hat)
    Xm=np.column_stack([np.ones(n),X.values])
    try:
        cov=np.linalg.inv(Xm.T@(W[:,None]*Xm)); se=np.sqrt(np.diag(cov))
    except: se=np.full(X.shape[1]+1,np.nan)
    coef=np.concatenate([[model.intercept_[0]],model.coef_[0]])
    z=coef/se; pv=2*(1-stats.norm.cdf(np.abs(z)))
    names=["intercept"]+list(X.columns)
    return pd.DataFrame({"feature":names,"coefficient":np.round(coef,4),"std_error":np.round(se,4),
        "wald_z":np.round(z,4),"p_value":np.round(pv,4),"odds_ratio":np.round(np.exp(coef),4),
        "ci_lower":np.round(coef-1.96*se,4),"ci_upper":np.round(coef+1.96*se,4),"significant":pv<0.05})

def validate_model(model, X_woe: pd.DataFrame, y_true: np.ndarray) -> ModelValidationReport:
    w,passed=[],True
    y_prob=model.predict_proba(X_woe)[:,1]
    auc=float(roc_auc_score(y_true,y_prob)); gini=2*auc-1
    ks,ks_t=_ks(y_true,y_prob)
    brier=float(brier_score_loss(y_true,y_prob))
    coef_tbl=_wald(model,X_woe,y_true)
    insig=coef_tbl[~coef_tbl["significant"]&(coef_tbl["feature"]!="intercept")]
    if len(insig): w.append(f"Insignificant (p>0.05): {list(insig['feature'])}")
    vif_tbl=_vif(X_woe)
    high_vif=vif_tbl[vif_tbl["VIF"]>5]
    if len(high_vif): w.append(f"High VIF: {list(high_vif['feature'])}")
    if auc<0.65: w.append(f"AUC={auc:.3f} below 0.65"); passed=False
    if ks<0.20: w.append(f"KS={ks:.3f} low discriminatory power"); passed=False
    corr=float(np.corrcoef(model.decision_function(X_woe),y_true)[0,1])
    if corr<0: w.append("Log-odds negatively correlated with target — check encoding"); passed=False
    return ModelValidationReport(round(auc,4),round(gini,4),round(ks,4),round(ks_t,4),
                                  round(brier,4),coef_tbl,vif_tbl,w,passed)

# ── PART 5 ───────────────────────────────────────────────────

@dataclass
class CalibrationReport:
    brier_score: float; ece: float; hl_statistic: float; hl_p_value: float
    hl_passed: bool; calibration_needed: bool
    fraction_of_positives: List[float]; mean_predicted: List[float]
    warnings: List[str] = field(default_factory=list)

def _hl(y_true, y_prob, g=10):
    df=pd.DataFrame({"y":y_true,"p":y_prob})
    df["dec"]=pd.qcut(df["p"],q=g,duplicates="drop",labels=False)
    stat=0.0
    for _,grp in df.groupby("dec"):
        n=len(grp); o1=grp["y"].sum(); e1=grp["p"].sum(); o0=n-o1; e0=n-e1
        if e1>0: stat+=(o1-e1)**2/e1
        if e0>0: stat+=(o0-e0)**2/e0
    pv=float(1-stats.chi2.cdf(stat,g-2))
    return float(stat),pv

def _ece(y_true, y_prob, n_bins=10):
    bps=np.linspace(0,1,n_bins+1); ece=0.0; n=len(y_true)
    for lo,hi in zip(bps[:-1],bps[1:]):
        mask=(y_prob>=lo)&(y_prob<hi)
        if not mask.any(): continue
        ece+=(mask.sum()/n)*abs(y_true[mask].mean()-y_prob[mask].mean())
    return float(ece)

def validate_calibration(model, X_woe, y_true, apply_platt=False):
    from sklearn.calibration import CalibratedClassifierCV
    y_prob=model.predict_proba(X_woe)[:,1]
    brier=float(brier_score_loss(y_true,y_prob))
    ece=_ece(y_true,y_prob); hl,p=_hl(y_true,y_prob)
    frac,mean_p=calibration_curve(y_true,y_prob,n_bins=10)
    w=[]
    if ece>0.10: w.append(f"ECE={ece:.3f} poor calibration")
    if p<0.05:   w.append(f"HL p={p:.4f} calibration rejected")
    if brier>0.20: w.append(f"Brier={brier:.3f} high")
    needs_cal=ece>0.10 or p<0.05
    platt=None
    if needs_cal and apply_platt:
        platt=CalibratedClassifierCV(model,cv="prefit",method="sigmoid")
        platt.fit(X_woe,y_true)
        ece_after=_ece(y_true,platt.predict_proba(X_woe)[:,1])
        w.append(f"Platt applied. ECE after: {ece_after:.3f}")
    return CalibrationReport(round(brier,4),round(ece,4),round(hl,4),round(p,4),
        p>0.05,needs_cal,list(np.round(frac,4)),list(np.round(mean_p,4)),w), platt

# ── PART 6 ───────────────────────────────────────────────────

@dataclass
class ScoreValidationReport:
    min_score: float; max_score: float; mean_score: float; std_score: float
    monotonic: bool; direction_correct: bool
    at_floor_pct: float; at_ceiling_pct: float; saturation_warning: bool
    warnings: List[str] = field(default_factory=list); passed: bool = True

def pd_to_score(pd_val):
    pd_val=np.clip(pd_val,1e-6,1-1e-6)
    return int(np.clip(_OFFSET-_FACTOR*np.log(pd_val/(1-pd_val)),300,900))

def validate_score_scaling(model, X_woe, y_true) -> ScoreValidationReport:
    w,passed=[],True
    y_prob=np.clip(model.predict_proba(X_woe)[:,1],1e-6,1-1e-6)
    z=model.decision_function(X_woe)
    scores=np.array([int(np.clip(_OFFSET-_FACTOR*zi,300,900)) for zi in z])
    corr=float(np.corrcoef(y_prob,scores)[0,1])
    monotonic=corr<-0.95; direction_ok=corr<0
    if not direction_ok:
        w.append(f"Score-PD correlation={corr:.3f} (expected negative)"); passed=False
    at_floor=float((scores==300).mean()); at_ceiling=float((scores==900).mean())
    saturated=(at_floor+at_ceiling)>0.80
    if saturated:
        w.append(f"{(at_floor+at_ceiling)*100:.1f}% at floor/ceiling — saturated"); passed=False
    if scores.max()-scores.min()<200:
        w.append(f"Score range only {scores.max()-scores.min()} pts")
    anchor=pd_to_score(1/(1+_BASE_ODDS))
    if abs(anchor-_BASE_SCORE)>5:
        w.append(f"Anchor check: BASE_ODDS={_BASE_ODDS} → score={anchor} (expected {_BASE_SCORE})"); passed=False
    return ScoreValidationReport(float(scores.min()),float(scores.max()),
        float(scores.mean()),float(scores.std()),monotonic,direction_ok,
        round(at_floor,4),round(at_ceiling,4),saturated,w,passed)