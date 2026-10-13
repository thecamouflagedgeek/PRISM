"""Train-only empirical transaction perturbations and ledger checks."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

from phase2.semisynthetic.feature_extraction import FEATURES, extract_behavioral_features

GENERATOR_VERSION = "berka-local-ledger-augmentation-v2"
SIGN = {"PRIJEM": 1.0, "VYDAJ": -1.0, "VYBER KARTOU": -1.0, "VYBER": -1.0}


def _group_key(row):
    cat = row.k_symbol
    cat = "(blank)" if pd.isna(cat) or str(cat) == "" else str(cat)
    return str(row.type).upper(), cat


def fit_generator(training_parents: list[dict], split_seed: int) -> dict:
    """Fit robust within-parent/category log-amount residual pools on train parents."""
    abs_pool, pools = [], {}
    all_events = 0
    parent_ids = []
    for parent in training_parents:
        parent_ids.append(int(parent["parent_loan_id"]))
        tx = parent["transactions"]
        all_events += len(tx)
        if (tx.amount < 0).any() or not np.isfinite(tx.amount).all():
            raise ValueError("Training parent contains invalid amount values")
        work = tx.copy()
        work["log_amount"] = np.log(np.maximum(work.amount.astype(float), 1e-9))
        work["group"] = work.apply(_group_key, axis=1)
        work["parent"] = int(parent["parent_loan_id"])
        for (p_id, group), g in work.groupby(["parent", "group"], sort=False):
            vals = g.log_amount.to_numpy(dtype=float)
            if len(vals) >= 2:
                residuals = vals - np.median(vals)
                pool = np.abs(residuals[np.abs(residuals) > 1e-10])
                if len(pool):
                    pools.setdefault(group, []).extend(pool.tolist())
                    abs_pool.extend(pool.tolist())
    if not abs_pool:
        raise RuntimeError("No within-parent transaction amount variation exists to ground augmentation")
    arr = np.asarray(abs_pool, dtype=float)
    return {
        "version": GENERATOR_VERSION, "fit_parent_ids": sorted(parent_ids),
        "fit_parent_ids_sha256": hashlib.sha256(",".join(map(str, sorted(parent_ids))).encode()).hexdigest(),
        "fit_parent_count": len(parent_ids), "fit_transaction_count": all_events,
        "residual_pools": {k: np.asarray(v, dtype=float) for k, v in pools.items()},
        "global_pool": arr,
        "q50_abs_log_residual": float(np.quantile(arr, .50)),
        "q90_abs_log_residual": float(np.quantile(arr, .90)),
        "q95_abs_log_residual": float(np.quantile(arr, .95)),
        "q99_abs_log_residual": float(np.quantile(arr, .99)),
        "group_pool_sizes": {f"{k[0]}|{k[1]}": len(v) for k,v in pools.items()},
        "group_quantiles": {f"{k[0]}|{k[1]}": {"n":len(v),"q50":float(np.quantile(v,.5)),"q90":float(np.quantile(v,.9)),"q95":float(np.quantile(v,.95))} for k,v in pools.items()},
        "split_seed": int(split_seed),
    }


def training_feature_geometry(training_parents: list[dict]) -> dict:
    frame = pd.DataFrame([p["features"] for p in training_parents], columns=FEATURES)
    med = frame.median(numeric_only=True).reindex(FEATURES).fillna(0).to_numpy(float)
    q1 = frame.quantile(.25, numeric_only=True).reindex(FEATURES).to_numpy(float)
    q3 = frame.quantile(.75, numeric_only=True).reindex(FEATURES).to_numpy(float)
    scale = q3-q1
    sd = frame.std(numeric_only=True).reindex(FEATURES).fillna(0).to_numpy(float)
    scale = np.where(scale > 1e-9, scale, np.where(sd > 1e-9, sd, 1.0))
    matrix = (frame.fillna(pd.Series(med,index=FEATURES)).to_numpy(float)-med)/scale
    if len(matrix) > 1:
        distances = cdist(matrix, matrix, metric="euclidean")
        np.fill_diagonal(distances, np.inf)
        nn = distances.min(axis=1)
        q95_nn = float(np.quantile(nn, .95))
    else:
        q95_nn = 0.0
    return {"median":med,"scale":scale,"parent_nn_q95":q95_nn}


def _ledger_rebuild(tx: pd.DataFrame, opening_balance: float | None = None) -> tuple[pd.DataFrame,float]:
    out = tx.copy().reset_index(drop=True)
    types = out.type.astype(str).str.upper()
    unknown = sorted(set(types)-set(SIGN))
    if unknown:
        raise ValueError(f"Unknown transaction directions cannot be safely reconstructed: {unknown}")
    signed = np.array([SIGN[t] for t in types],dtype=float)*out.amount.to_numpy(dtype=float)
    original = out.balance.to_numpy(dtype=float)
    if not len(out) or not np.isfinite(original).all():
        raise ValueError("Ledger must have transactions and finite observed balances")
    opening = float(original[0]-signed[0]) if opening_balance is None else float(opening_balance)
    rebuilt = opening+np.cumsum(signed)
    out["balance"] = rebuilt
    # Verify the newly reconstructed ledger against its own sequential identity.
    movements=np.diff(np.r_[opening,rebuilt])
    err=float(np.max(np.abs(movements-signed)))
    return out, err


def _source_ledger_error(tx: pd.DataFrame) -> float:
    # Check balances in original Berka file order, since same-day rows can be
    # permuted by the canonical feature pipeline's date sort.
    if "source_order" in tx.columns:
        tx = tx.sort_values("source_order", kind="mergesort")
    types=tx.type.astype(str).str.upper()
    unknown=sorted(set(types)-set(SIGN))
    if unknown: raise ValueError(f"Unknown source transaction directions: {unknown}")
    signed=np.array([SIGN[t] for t in types],float)*tx.amount.to_numpy(dtype=float)
    balance=tx.balance.to_numpy(dtype=float)
    if not len(balance) or not np.isfinite(balance).all(): raise ValueError("Source ledger lacks finite balances")
    movements=np.diff(np.r_[balance[0]-signed[0],balance])
    return float(np.max(np.abs(movements-signed)))


def _history_signature(tx: pd.DataFrame) -> str:
    cols=["date","type","amount","k_symbol"]
    view=tx[cols].copy()
    view["date"]=pd.to_datetime(view.date).dt.strftime("%Y-%m-%d")
    view["k_symbol"]=view.k_symbol.fillna("").astype(str)
    payload=view.to_csv(index=False,float_format="%.10f").encode()
    return hashlib.sha256(payload).hexdigest()


def _feature_distance(parent_features: dict, desc_features: dict, geometry: dict) -> float:
    a=np.array([parent_features.get(f,np.nan) for f in FEATURES],float)
    b=np.array([desc_features.get(f,np.nan) for f in FEATURES],float)
    a=np.where(np.isfinite(a),a,geometry["median"])
    b=np.where(np.isfinite(b),b,geometry["median"])
    return float(np.sqrt(np.mean(((b-a)/geometry["scale"])**2)))


def make_descendant(parent: dict, params: dict, geometry: dict, condition: str,
                    strength: float, seed: int, synthetic_id: str,
                    max_history_distance: float | None = None,
                    max_feature_distance: float | None = None) -> dict:
    rng=np.random.default_rng(seed)
    src=parent["transactions"].copy().reset_index(drop=True)
    source_error=_source_ledger_error(src)
    first_type=str(src.type.iloc[0]).upper()
    opening_balance=float(src.balance.iloc[0]-SIGN[first_type]*src.amount.iloc[0])
    tx=src.copy()
    deltas=[]; operations=[]
    cap=params["q90_abs_log_residual"] if condition=="E1" else params["q95_abs_log_residual"]
    pools=params["residual_pools"]
    for i,row in tx.iterrows():
        group=_group_key(row)
        pool=pools.get(group,params["global_pool"])
        change=float(rng.choice(pool)) if len(pool) else 0.0
        change=min(change,cap)*strength
        if rng.random()<0.5:
            change=-change
        old=float(row.amount)
        new=float(old*np.exp(change))
        if not np.isfinite(new) or new<0:
            raise ValueError("Invalid perturbed transaction amount")
        tx.at[i,"amount"]=new
        deltas.append(change)
        operations.append({"trans_id":int(row.trans_id),"date":str(pd.Timestamp(row.date).date()),"type":str(row.type),"category":"(blank)" if pd.isna(row.k_symbol) or str(row.k_symbol)=="" else str(row.k_symbol),"old_amount":old,"new_amount":new,"log_multiplier":change})
    # Direction, category, transaction count, and within-month timing are invariant.
    if not np.array_equal(src.type.astype(str).to_numpy(),tx.type.astype(str).to_numpy()):
        raise RuntimeError("Augmentation changed transaction direction")
    if not src.k_symbol.fillna("").astype(str).equals(tx.k_symbol.fillna("").astype(str)):
        raise RuntimeError("Augmentation changed transaction category")
    if not pd.to_datetime(tx.date).equals(pd.to_datetime(src.date)):
        raise RuntimeError("Augmentation changed dates")
    if len(tx)!=len(src) or tx.empty:
        raise RuntimeError("Augmentation changed transaction count or produced empty history")
    tx, ledger_error=_ledger_rebuild(tx,opening_balance=opening_balance)
    if ledger_error>1e-6:
        raise ValueError(f"Balance ledger fails reconciliation: {ledger_error}")
    f=extract_behavioral_features(tx,parent["loan_date"],parent["window_start"],parent["window_end_exclusive"],months=3)
    hist_dist=float(np.sqrt(np.mean(np.square(deltas)))) if deltas else 0.0
    feat_dist=_feature_distance(parent["features"],f,geometry)
    sig=_history_signature(tx)
    parent_sig=_history_signature(src)
    if sig==parent_sig:
        raise ValueError("EXACT_DUPLICATE_HISTORY")
    if max_history_distance is not None and hist_dist>max_history_distance:
        raise ValueError(f"HISTORY_DISTANCE_EXCEEDED:{hist_dist:.8g}>{max_history_distance:.8g}")
    if max_feature_distance is not None and feat_dist>max_feature_distance:
        raise ValueError(f"FEATURE_DISTANCE_EXCEEDED:{feat_dist:.8g}>{max_feature_distance:.8g}")
    if (((tx.date<pd.Timestamp(parent["window_start"]))
            | (tx.date>=pd.Timestamp(parent["window_end_exclusive"]))
            | (tx.date>=pd.Timestamp(parent["loan_date"]))).any()):
        raise ValueError("SYNTHETIC_DATE_OUTSIDE_WINDOW")
    if any(not np.isfinite(v) for v in f.values() if pd.notna(v)):
        raise ValueError("NONFINITE_FEATURE")
    return {
        "synthetic_id":synthetic_id,"parent_loan_id":parent["parent_loan_id"],
        "parent_account_id":parent["parent_account_id"],"parent_target":parent["target"],
        "target":parent["target"],"status":parent["status"],"label_source":"PARENT_INHERITED",
        "is_synthetic":True,"augmentation_condition":condition,"augmentation_strength":strength,
        "augmentation_seed":int(seed),"generation_version":GENERATOR_VERSION,
        "transactions":tx,"features":f,"operations":operations,"ledger_error":ledger_error,
        "source_balance_movement_error":source_error,
        "history_distance":hist_dist,"feature_distance":feat_dist,
        "parent_signature":parent_sig,"synthetic_signature":sig,
        "mean_abs_log_amount_change":float(np.mean(np.abs(deltas))),
        "max_abs_log_amount_change":float(np.max(np.abs(deltas))) if deltas else 0.0,
    }


def make_duplicate(parent: dict, condition: str, seed: int, synthetic_id: str) -> dict:
    tx=parent["transactions"].copy(deep=True)
    return {"synthetic_id":synthetic_id,"parent_loan_id":parent["parent_loan_id"],
        "parent_account_id":parent["parent_account_id"],"parent_target":parent["target"],
        "target":parent["target"],"status":parent["status"],"label_source":"PARENT_INHERITED",
        "is_synthetic":True,"augmentation_condition":condition,"augmentation_strength":0.0,
        "augmentation_seed":int(seed),"generation_version":GENERATOR_VERSION,
        "transactions":tx,"features":dict(parent["features"]),"operations":[],"ledger_error":0.0,
        "history_distance":0.0,"feature_distance":0.0,
        "parent_signature":_history_signature(tx),"synthetic_signature":_history_signature(tx),
        "mean_abs_log_amount_change":0.0,"max_abs_log_amount_change":0.0}


def monthly_aggregates(tx: pd.DataFrame, window_start, months=3) -> list[dict]:
    frame=tx.copy(); frame["date"]=pd.to_datetime(frame.date); typ=frame.type.astype(str).str.upper()
    frame["credit"]=np.where(typ=="PRIJEM",frame.amount,0.)
    frame["debit"]=np.where(typ.isin(["VYDAJ","VYBER KARTOU"]),frame.amount,0.)
    frame["net"]=frame.credit-frame.debit; frame["month"]=frame.date.dt.to_period("M")
    index=pd.period_range(pd.Timestamp(window_start).to_period("M"),periods=months,freq="M")
    result=frame.groupby("month").agg(credits=("credit","sum"),debits=("debit","sum"),net=("net","sum"),txn=("amount","size"),bal_end=("balance","last")).reindex(index)
    result[["credits","debits","net","txn"]]=result[["credits","debits","net","txn"]].fillna(0)
    result.index.name="month"
    return result.reset_index().assign(month=lambda x:x.month.astype(str)).to_dict(orient="records")
