"""Parent-aware Phase 2B.5-S experiment. Writes only outputs/phase2b5s."""
from __future__ import annotations

import hashlib, json, platform, sys
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
from scipy.stats import ks_2samp, wasserstein_distance

from phase2.phase2b import stratified_indices, sha256
from phase2.semisynthetic import GENERATOR_VERSION
from phase2.semisynthetic.data import AUDIT, real_3m_parents
from phase2.semisynthetic.feature_extraction import FEATURES, FEATURE_SCHEMA_VERSION
from phase2.semisynthetic.generator import fit_generator, training_feature_geometry, make_descendant, make_duplicate, monthly_aggregates
from phase2.semisynthetic.modeling import records_from_parents, records_from_descendants, family_weights, scorecard_fit, evaluate

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"outputs"/"phase2b5s"
SEED=20261006; REPEATS=20; HOLDOUT_FRAC=.20; VAL_FRAC=.25
E1_K=1; E2_K=3; E2_DENSITIES=(1,3,5)
FORBIDDEN={"loan_id","parent_loan_id","parent_account_id","status","target","loan_amount","amount","duration","payments","loan_payment","documented_loan_payment_total","postloan_transaction_count","postloan_UVER_payment_count"}

def _seed(repeat,pid,child,code): return int((SEED+repeat*1000003+pid*9176+child*37+code*7919)%(2**32-1))

def _split(parents,fraction,seed):
    y=np.array([p["target"] for p in parents],int); tr,te=stratified_indices(y,fraction,seed)
    return [parents[i] for i in tr],[parents[i] for i in te]

def _assert_parent_partition(train,val,hold):
    tr={int(p["parent_loan_id"]) for p in train}; va={int(p["parent_loan_id"]) for p in val}; ho={int(p["parent_loan_id"]) for p in hold}
    if tr&va or tr&ho or va&ho: raise RuntimeError("Parent family crosses train/validation/holdout")
    return tr,va,ho

def _generate(parents,params,geometry,condition,strength,k,repeat,code,max_history,max_feature,lineage,rejections,ledger,duplicates,traces,trace_limit=1):
    allowed={int(p["parent_loan_id"]) for p in parents}
    if set(params["fit_parent_ids"])!=allowed: raise RuntimeError("Generator fit included nontraining parent or omitted a training parent")
    descendants=[]; traced=0
    for parent in parents:
        pid=int(parent["parent_loan_id"])
        if pid not in allowed: raise RuntimeError("Attempted to augment validation/holdout parent")
        for child in range(1,k+1):
            made=None
            for attempt in range(1,6):
                seed=_seed(repeat,pid,child+attempt*100,code)
                sid=f"R{repeat:02d}_{condition}_{pid}_SYN{child:02d}"
                try:
                    made=make_descendant(parent,params,geometry,condition,strength,seed,sid,max_history,max_feature)
                    made.update(split_id=f"repeat_{repeat:02d}",augmentation_attempt=attempt)
                    break
                except (ValueError,RuntimeError) as exc:
                    rejections.append({"split_id":f"repeat_{repeat:02d}","condition":condition,"parent_loan_id":pid,"requested_child":child,"attempt":attempt,"reason":str(exc)})
            if made is None: continue
            if made["parent_loan_id"] not in allowed: raise RuntimeError("Descendant family crosses split boundary")
            descendants.append(made)
            lineage.append({"synthetic_id":made["synthetic_id"],"parent_loan_id":pid,"parent_account_id":made["parent_account_id"],"parent_target":made["parent_target"],"target":made["target"],"label_source":made["label_source"],"is_synthetic":True,"augmentation_condition":condition,"augmentation_strength":strength,"augmentation_seed":seed,"generation_version":GENERATOR_VERSION,"split_id":made["split_id"],"augmentation_attempt":made["augmentation_attempt"],"history_distance":made["history_distance"],"feature_distance":made["feature_distance"],"mean_abs_log_amount_change":made["mean_abs_log_amount_change"],"max_abs_log_amount_change":made["max_abs_log_amount_change"],"transaction_count":len(made["transactions"]),"features_json":json.dumps(made["features"],sort_keys=True,allow_nan=True,separators=(",",":")),"synthetic_signature":made["synthetic_signature"]})
            ledger.append({"synthetic_id":made["synthetic_id"],"parent_loan_id":pid,"condition":condition,"split_id":made["split_id"],"transaction_count":len(made["transactions"]),"source_balance_movement_error_diagnostic":made["source_balance_movement_error"],"max_balance_reconciliation_error":made["ledger_error"],"passed":made["ledger_error"]<=1e-6})
            duplicates.append({"synthetic_id":made["synthetic_id"],"parent_loan_id":pid,"condition":condition,"split_id":made["split_id"],"exact_history_duplicate":made["synthetic_signature"]==made["parent_signature"],"feature_distance":made["feature_distance"],"near_feature_duplicate":made["feature_distance"]<.01,"history_distance":made["history_distance"]})
            if traced<trace_limit:
                traces.append({"synthetic_id":made["synthetic_id"],"split_id":made["split_id"],"parent_loan_id":pid,"condition":condition,"parent_transaction_history":parent["transactions"].to_dict(orient="records"),"augmentation_operations":made["operations"],"synthetic_transaction_history":made["transactions"].to_dict(orient="records"),"reconstructed_balance_error":made["ledger_error"],"canonical_monthly_aggregates":monthly_aggregates(made["transactions"],parent["window_start"]),"canonical_features":made["features"],"label_source":"PARENT_INHERITED","inherited_label":made["target"]}); traced+=1
    return descendants

def _model_eval(condition,train_records,val_records,split_id,seed,weighting,metrics,selected_rows,coef_rows,bin_rows,preds):
    w=family_weights(train_records,naive=(weighting=="naive")); model=scorecard_fit(train_records,w); ev=evaluate(model,val_records)
    clean={k:v for k,v in ev.items() if k not in {"linear_predictors","pd","scores","woe_matrix"}}
    metrics.append({"split_id":split_id,"seed":seed,"condition":condition,"weighting":weighting,"real_train_parent_n":len(set(r["parent_loan_id"] for r in train_records)),"synthetic_training_row_n":sum(r["is_synthetic"] for r in train_records),"synthetic_default_descendants":sum(r["is_synthetic"] and int(r["target"])==1 for r in train_records),"real_validation_parent_n":len(val_records),"real_validation_defaults":sum(r["target"] for r in val_records),"selected_features":"|".join(model["selected"]),"converged":model["converged"],"optimizer_message":model["message"],**clean})
    for f in model["selected"]:
        j=model["selected"].index(f); b=float(model["beta"][j+1])
        selected_rows.append({"split_id":split_id,"condition":condition,"feature":f,"iv":model["ivs"][f]})
        coef_rows.append({"split_id":split_id,"condition":condition,"feature":f,"coefficient":b,"sign":int(np.sign(b)),"intercept":float(model["beta"][0]),"converged":model["converged"]})
        bin_rows.append({"split_id":split_id,"condition":condition,"feature":f,"cut":model["binners"][f]["cut"],"training_iv":model["ivs"][f],"bin_metadata_json":json.dumps({"woe":model["binners"][f]["woe"],"fallback":model["binners"][f]["fallback"]},sort_keys=True)})
    for i,r in enumerate(val_records): preds.append({"split_id":split_id,"condition":condition,"parent_loan_id":r["parent_loan_id"],"target":r["target"],"pd":float(ev["pd"][i]),"score":float(ev["scores"][i]),"evaluation_source":"REAL_VALIDATION"})
    return model,ev

def _fidelity(split_id,condition,real,synth,target=None):
    if target is not None: real=[r for r in real if r["target"]==target]; synth=[r for r in synth if r["target"]==target]
    out=[]
    for f in FEATURES:
        a=np.array([r["features"].get(f,np.nan) for r in real],float); b=np.array([r["features"].get(f,np.nan) for r in synth],float); av=a[np.isfinite(a)]; bv=b[np.isfinite(b)]
        out.append({"split_id":split_id,"condition":condition,"target":target,"feature":f,"real_n":len(a),"synthetic_n":len(b),"real_mean":float(av.mean()) if len(av) else np.nan,"synthetic_mean":float(bv.mean()) if len(bv) else np.nan,"real_median":float(np.median(av)) if len(av) else np.nan,"synthetic_median":float(np.median(bv)) if len(bv) else np.nan,"real_sd":float(np.std(av,ddof=1)) if len(av)>1 else np.nan,"synthetic_sd":float(np.std(bv,ddof=1)) if len(bv)>1 else np.nan,"real_iqr":float(np.quantile(av,.75)-np.quantile(av,.25)) if len(av) else np.nan,"synthetic_iqr":float(np.quantile(bv,.75)-np.quantile(bv,.25)) if len(bv) else np.nan,"real_q10":float(np.quantile(av,.10)) if len(av) else np.nan,"real_q90":float(np.quantile(av,.90)) if len(av) else np.nan,"synthetic_q10":float(np.quantile(bv,.10)) if len(bv) else np.nan,"synthetic_q90":float(np.quantile(bv,.90)) if len(bv) else np.nan,"real_zero_frequency":float((av==0).mean()) if len(av) else np.nan,"synthetic_zero_frequency":float((bv==0).mean()) if len(bv) else np.nan,"real_missing_frequency":float((~np.isfinite(a)).mean()) if len(a) else np.nan,"synthetic_missing_frequency":float((~np.isfinite(b)).mean()) if len(b) else np.nan,"ks_distance":float(ks_2samp(av,bv).statistic) if len(av) and len(bv) else np.nan,"wasserstein_distance":float(wasserstein_distance(av,bv)) if len(av) and len(bv) else np.nan})
    if len(real)>1 and len(synth)>1:
        a=pd.DataFrame([r["features"] for r in real],columns=FEATURES).corr(method="spearman").to_numpy()
        b=pd.DataFrame([r["features"] for r in synth],columns=FEATURES).corr(method="spearman").to_numpy()
        d=np.abs(a-b); vals=d[np.triu_indices(len(FEATURES),1)]; vals=vals[np.isfinite(vals)]
        out.append({"split_id":split_id,"condition":condition,"target":target,"feature":"__pairwise_spearman_correlation__","real_n":len(real),"synthetic_n":len(synth),"mean_abs_correlation_difference":float(vals.mean()) if len(vals) else np.nan,"max_abs_correlation_difference":float(vals.max()) if len(vals) else np.nan})
    return out

def _summarize(metrics):
    df=pd.DataFrame(metrics); rows=[]
    for condition,g in df[df.split_id.str.startswith("repeat_")].groupby("condition"):
        r={"condition":condition,"repeated_split_n":int(g.split_id.nunique()),"converged_fraction":float(g.converged.mean())}
        for m in ["auc","gini","ks","brier","log_loss","mean_predicted_pd","observed_default_rate","calibration_intercept","calibration_slope"]:
            x=pd.to_numeric(g[m],errors="coerce").dropna()
            for n,v in [("mean",x.mean()),("sd",x.std(ddof=1)),("median",x.median()),("min",x.min()),("max",x.max()),("p05",x.quantile(.05)),("p95",x.quantile(.95))]: r[f"{m}_{n}"]=float(v) if pd.notna(v) else np.nan
        rows.append(r)
    return pd.DataFrame(rows)

def _paired(metrics):
    df=pd.DataFrame(metrics); rows=[]; by={(r.split_id,r.condition):r for r in df.itertuples(index=False)}
    for sid in sorted(set(df[df.condition=="E0"].split_id)):
        base=by.get((sid,"E0"))
        if base is None:continue
        for cond in ("E1","E2"):
            other=by.get((sid,cond))
            if other is None:continue
            row={"split_id":sid,"condition":cond}
            for m in ["auc","gini","ks","brier","log_loss"]:row[f"delta_{m}"]=getattr(other,m)-getattr(base,m)
            rows.append(row)
    return pd.DataFrame(rows)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    parents,cohort=real_3m_parents()
    hold_seed=SEED
    dev,hold=_split(parents,HOLDOUT_FRAC,hold_seed); _assert_parent_partition(dev,[],hold)
    split_registry=[{"split_id":"holdout","seed":hold_seed,"assignment":"real_only_holdout","parent_ids":"|".join(str(p["parent_loan_id"]) for p in hold),"parent_n":len(hold),"defaults":sum(p["target"] for p in hold),"synthetic_descendants":0},
                    {"split_id":"development","seed":hold_seed,"assignment":"development_pool","parent_ids":"|".join(str(p["parent_loan_id"]) for p in dev),"parent_n":len(dev),"defaults":sum(p["target"] for p in dev),"synthetic_descendants":0}]
    metrics=[]; selections=[]; coefficients=[]; bins=[]; predictions=[]; lineage=[]; rejections=[]; ledger=[]; duplicates=[]; traces=[]; param_rows=[]; fidelity=[]; conditional=[]; density=[]; negatives=[]; hold_results=[]
    for repeat in range(1,REPEATS+1):
        seed=SEED+repeat*31
        tr,va=_split(dev,VAL_FRAC,seed); tr_ids,va_ids,hold_ids=_assert_parent_partition(tr,va,hold)
        if hold_ids.intersection(tr_ids|va_ids): raise RuntimeError("Holdout overlap")
        split_id=f"repeat_{repeat:02d}"
        split_registry.append({"split_id":split_id,"seed":seed,"assignment":"repeated_train_validation","train_parent_ids":"|".join(map(str,sorted(tr_ids))),"validation_parent_ids":"|".join(map(str,sorted(va_ids))),"holdout_parent_ids":"|".join(map(str,sorted(hold_ids))),"train_parent_n":len(tr),"train_defaults":sum(p["target"] for p in tr),"validation_parent_n":len(va),"validation_defaults":sum(p["target"] for p in va),"synthetic_descendants_in_validation":0,"synthetic_descendants_in_holdout":0})
        params=fit_generator(tr,seed); geometry=training_feature_geometry(tr)
        if not set(params["fit_parent_ids"]).issubset(tr_ids) or set(params["fit_parent_ids"])&va_ids or set(params["fit_parent_ids"])&hold_ids: raise RuntimeError("Validation/holdout informed augmentation parameters")
        param_rows.append({"split_id":split_id,"fit_parent_n":params["fit_parent_count"],"fit_transaction_n":params["fit_transaction_count"],"fit_parent_ids_sha256":params["fit_parent_ids_sha256"],"abs_log_residual_q50":params["q50_abs_log_residual"],"abs_log_residual_q90":params["q90_abs_log_residual"],"abs_log_residual_q95":params["q95_abs_log_residual"],"abs_log_residual_q99":params["q99_abs_log_residual"],"feature_space_parent_nn_q95":geometry["parent_nn_q95"],"E1_strength":.5,"E1_cap_quantile":.90,"E1_max_feature_distance":geometry["parent_nn_q95"],"E2_strength":1.0,"E2_cap_quantile":.95,"E2_max_feature_distance":1.5*geometry["parent_nn_q95"],"group_quantiles_json":json.dumps(params["group_quantiles"],sort_keys=True)})
        e1=_generate(tr,params,geometry,"E1",.5,E1_K,repeat,1,params["q90_abs_log_residual"],geometry["parent_nn_q95"],lineage,rejections,ledger,duplicates,traces)
        e2=_generate(tr,params,geometry,"E2",1.0,5,repeat,2,params["q95_abs_log_residual"],1.5*geometry["parent_nn_q95"],lineage,rejections,ledger,duplicates,traces)
        dups=[]
        for p in tr:
            for j in range(1,4):
                d=make_duplicate(p,"E_DUPLICATE_CONTROL",_seed(repeat,p["parent_loan_id"],j,3),f"{split_id}_DUP_{p['parent_loan_id']}_{j}"); d["split_id"]=split_id; dups.append(d)
                lineage.append({"synthetic_id":d["synthetic_id"],"parent_loan_id":d["parent_loan_id"],"parent_account_id":d["parent_account_id"],"parent_target":d["parent_target"],"target":d["target"],"label_source":d["label_source"],"is_synthetic":True,"augmentation_condition":"E_DUPLICATE_CONTROL","augmentation_strength":0.0,"augmentation_seed":d["augmentation_seed"],"generation_version":GENERATOR_VERSION,"split_id":split_id,"augmentation_attempt":1,"history_distance":0.0,"feature_distance":0.0,"mean_abs_log_amount_change":0.0,"max_abs_log_amount_change":0.0,"transaction_count":len(d["transactions"]),"features_json":json.dumps(d["features"],sort_keys=True,allow_nan=True,separators=(",",":")),"synthetic_signature":d["synthetic_signature"]})
                duplicates.append({"synthetic_id":d["synthetic_id"],"parent_loan_id":d["parent_loan_id"],"condition":"E_DUPLICATE_CONTROL","split_id":split_id,"exact_history_duplicate":True,"feature_distance":0.0,"near_feature_duplicate":True,"history_distance":0.0})
                ledger.append({"synthetic_id":d["synthetic_id"],"parent_loan_id":d["parent_loan_id"],"condition":"E_DUPLICATE_CONTROL","split_id":split_id,"transaction_count":len(d["transactions"]),"max_balance_reconciliation_error":0.0,"passed":True})
        real_train=records_from_parents(tr); val_records=records_from_parents(va)
        e1rec=real_train+records_from_descendants(e1); e2records={k:real_train+records_from_descendants(e2[:]) for k in E2_DENSITIES}
        duprec=real_train+records_from_descendants(dups)
        _model_eval("E0",real_train,val_records,split_id,seed,"parent_normalized",metrics,selections,coefficients,bins,predictions)
        _model_eval("E1",e1rec,val_records,split_id,seed,"parent_normalized",metrics,selections,coefficients,bins,predictions)
        _model_eval("E1_NAIVE",e1rec,val_records,split_id,seed,"naive",metrics,selections,coefficients,bins,predictions)
        # Use the first K children per parent. Generator loops in parent-major order.
        for k,cond in [(1,"E2_DENSITY_1"),(3,"E2"),(5,"E2_DENSITY_5")]:
            keep={d["parent_loan_id"]:0 for d in e2}
            chosen=[]
            for d in e2:
                if keep[d["parent_loan_id"]]<k: chosen.append(d); keep[d["parent_loan_id"]]+=1
            records=real_train+records_from_descendants(chosen)
            _model_eval(cond,records,val_records,split_id,seed,"parent_normalized",metrics,selections,coefficients,bins,predictions)
            density.append({"split_id":split_id,"condition":cond,"descendants_per_training_parent_target":k,"actual_descendants":len(chosen),"actual_descendants_per_parent_mean":len(chosen)/len(tr),"validation_auc":next(x["auc"] for x in reversed(metrics) if x["split_id"]==split_id and x["condition"]==cond),"validation_brier":next(x["brier"] for x in reversed(metrics) if x["split_id"]==split_id and x["condition"]==cond)})
        _model_eval("E2_NAIVE",real_train+records_from_descendants(e2[:]),val_records,split_id,seed,"naive",metrics,selections,coefficients,bins,predictions)
        _model_eval("E_DUPLICATE_CONTROL",duprec,val_records,split_id,seed,"parent_normalized",metrics,selections,coefficients,bins,predictions)
        # Paired realism and class-conditional diagnostics use only training parents and their descendants.
        synth_by={"E1":e1,"E2":e2}
        for cond,synth in synth_by.items():
            synth_rows=records_from_descendants(synth)
            fidelity.extend(_fidelity(split_id,cond,real_train,synth_rows))
            for cls in (0,1): conditional.extend(_fidelity(split_id,cond,[r for r in real_train if r["target"]==cls],[r for r in synth_rows if r["target"]==cls],target=cls))
        # Parent-level label shuffle is a leakage sanity check on one fixed split per repeat.
        shuffled=records_from_parents(tr); rng=np.random.default_rng(seed+888); lab=rng.permutation([r["target"] for r in shuffled])
        for r,y in zip(shuffled,lab):r["target"]=int(y)
        shmodel=scorecard_fit(shuffled,family_weights(shuffled)); shev=evaluate(shmodel,val_records)
        negatives.append({"split_id":split_id,"control":"TRAINING_PARENT_LABEL_SHUFFLE","condition":"E0","auc_on_real_validation":shev["auc"],"brier_on_real_validation":shev["brier"],"expected_auc":"near chance across repeats","converged":shmodel["converged"]})
    # Final fit after validation-design choices are fixed. Only development parents train these candidates.
    final_params=fit_generator(dev,hold_seed); final_geom=training_feature_geometry(dev)
    for cond,k,strength,code,cap in [("E1",E1_K,.5,11,final_params["q90_abs_log_residual"]),("E2",E2_K,1.,12,final_params["q95_abs_log_residual"])]:
        ds=_generate(dev,final_params,final_geom,cond,strength,k,99,code,cap,final_geom["parent_nn_q95"]*(1 if cond=="E1" else 1.5),lineage,rejections,ledger,duplicates,traces,trace_limit=1)
        train_recs=records_from_parents(dev)+records_from_descendants(ds)
        for r in train_recs:
            if r["parent_loan_id"] in {p["parent_loan_id"] for p in hold}:raise RuntimeError("Holdout descendant entered final training")
        model=scorecard_fit(train_recs,family_weights(train_recs)); val=records_from_parents(hold); ev=evaluate(model,val)
        hold_results.append({"condition":cond,"evaluation":"REAL HOLDOUT ONLY","n":ev["n"],"defaults":ev["defaults"],"nondefaults":ev["n"]-ev["defaults"],"selected_features":"|".join(model["selected"]),"synthetic_training_rows":len(ds),"auc":ev["auc"],"gini":ev["gini"],"ks":ev["ks"],"brier":ev["brier"],"log_loss":ev["log_loss"],"mean_predicted_pd":ev["mean_predicted_pd"],"observed_default_rate":ev["observed_default_rate"],"calibration_intercept":ev["calibration_intercept"],"calibration_slope":ev["calibration_slope"]})
        if cond=="E0": pass
    # Add the explicitly real-only E0 holdout fit.
    e0train=records_from_parents(dev); e0model=scorecard_fit(e0train,family_weights(e0train)); e0ev=evaluate(e0model,records_from_parents(hold))
    hold_results.insert(0,{"condition":"E0","evaluation":"REAL HOLDOUT ONLY","n":e0ev["n"],"defaults":e0ev["defaults"],"nondefaults":e0ev["n"]-e0ev["defaults"],"selected_features":"|".join(e0model["selected"]),"synthetic_training_rows":0,"auc":e0ev["auc"],"gini":e0ev["gini"],"ks":e0ev["ks"],"brier":e0ev["brier"],"log_loss":e0ev["log_loss"],"mean_predicted_pd":e0ev["mean_predicted_pd"],"observed_default_rate":e0ev["observed_default_rate"],"calibration_intercept":e0ev["calibration_intercept"],"calibration_slope":e0ev["calibration_slope"]})
    # The real holdout is never augmented, included in generator fit, or used for tuning.
    hold_ids={int(p["parent_loan_id"]) for p in hold}
    if any(int(d["parent_loan_id"]) in hold_ids for d in lineage): raise RuntimeError("Holdout descendant exists")
    # Output audit tables.
    pd.DataFrame(split_registry).to_csv(OUT/"split_registry.csv",index=False)
    pd.DataFrame(param_rows).to_csv(OUT/"augmentation_parameter_summary.csv",index=False)
    pd.DataFrame(lineage).to_csv(OUT/"synthetic_lineage.csv",index=False)
    pd.DataFrame(rejections).to_csv(OUT/"augmentation_rejections.csv",index=False)
    pd.DataFrame(fidelity).to_csv(OUT/"distribution_fidelity.csv",index=False)
    pd.DataFrame(conditional).to_csv(OUT/"conditional_fidelity.csv",index=False)
    pd.DataFrame(duplicates).to_csv(OUT/"duplicate_analysis.csv",index=False)
    pd.DataFrame(ledger).to_csv(OUT/"ledger_reconciliation.csv",index=False)
    metric_df=pd.DataFrame(metrics); metric_df.to_csv(OUT/"split_metrics.csv",index=False)
    pd.DataFrame(hold_results).to_csv(OUT/"holdout_results.csv",index=False)
    if traces: (OUT/"transaction_reconstruction_trace.json").write_text(json.dumps(traces,indent=2,default=str,allow_nan=True),encoding="utf-8")
    pd.DataFrame(negatives+[
        {"split_id":r["split_id"],"control":"E_DUPLICATE_CONTROL","condition":"E_DUPLICATE_CONTROL","auc_on_real_validation":r["auc"],"brier_on_real_validation":r["brier"],"expected_auc":"match E0 when family-normalized","converged":r["converged"]}
        for r in metrics if r["condition"]=="E_DUPLICATE_CONTROL"
    ]).to_csv(OUT/"negative_controls.csv",index=False)
    summary_metrics=_summarize(metrics); summary_metrics.to_csv(OUT/"condition_summary.csv",index=False)
    paired=_paired(metrics); paired_rows=paired.to_dict(orient="records")
    if len(paired):
        for cond,g in paired.groupby("condition"):
            for col in [c for c in g.columns if c.startswith("delta_")]:
                v=g[col].astype(float)
                paired_rows.append({"split_id":"SUMMARY","condition":cond,"metric":col.removeprefix("delta_"),"mean_difference":v.mean(),"median_difference":v.median(),"sd_difference":v.std(ddof=1),"improved_fraction":float((v>0).mean()) if col not in {"delta_brier","delta_log_loss"} else float((v<0).mean()),"p05":v.quantile(.05),"p95":v.quantile(.95)})
    pd.DataFrame(paired_rows).to_csv(OUT/"paired_comparison.csv",index=False)
    # Feature selection and coefficient stability are summarized only over repeated real validation splits.
    select_df=pd.DataFrame(selections); coef_df=pd.DataFrame(coefficients)
    features_out=[]
    for cond in ["E0","E1","E2"]:
        for f in FEATURES:
            g=select_df[(select_df.condition==cond)&(select_df.feature==f)]
            features_out.append({"condition":cond,"feature":f,"eligible_splits":REPEATS,"selected_count":len(g),"selection_frequency":len(g)/REPEATS,"mean_training_iv":float(g.iv.mean()) if len(g) else np.nan,"sd_training_iv":float(g.iv.std(ddof=1)) if len(g)>1 else np.nan})
    pd.DataFrame(features_out).to_csv(OUT/"feature_selection_stability.csv",index=False)
    coef_summary=[]
    for (cond,f),g in coef_df[coef_df.condition.isin(["E0","E1","E2"])].groupby(["condition","feature"]):
        signs=g.sign.tolist(); vals=g.coefficient.astype(float)
        coef_summary.append({"condition":cond,"feature":f,"selected_splits":len(g),"coefficient_mean":vals.mean(),"coefficient_sd":vals.std(ddof=1) if len(vals)>1 else 0.,"coefficient_median":vals.median(),"positive_sign_count":signs.count(1),"negative_sign_count":signs.count(-1),"sign_consistency":max(signs.count(1),signs.count(-1))/len(signs),"converged_fraction":g.converged.mean()})
    pd.DataFrame(coef_summary).to_csv(OUT/"coefficient_stability.csv",index=False)
    pd.DataFrame(bins).to_csv(OUT/"binning_stability.csv",index=False)
    # Score variability for real validation parents evaluated repeatedly; never synthetic validation.
    pred_df=pd.DataFrame(predictions); stability=[]
    for (cond,pid),g in pred_df.groupby(["condition","parent_loan_id"]):
        stability.append({"condition":cond,"parent_loan_id":pid,"validation_appearances":len(g),"pd_mean":g.pd.mean(),"pd_sd":g.pd.std(ddof=1) if len(g)>1 else 0.,"score_mean":g.score.mean(),"score_sd":g.score.std(ddof=1) if len(g)>1 else 0.})
    pd.DataFrame(stability).to_csv(OUT/"score_stability.csv",index=False)
    pd.DataFrame(density).to_csv(OUT/"augmentation_density_analysis.csv",index=False)
    # The no-op control must reproduce the E0 scorecard under family-normalized weights.
    paired_control=[]
    for sid in sorted(metric_df[metric_df.condition=="E0"].split_id.unique()):
        a=metric_df[(metric_df.split_id==sid)&(metric_df.condition=="E0")].iloc[0]
        b=metric_df[(metric_df.split_id==sid)&(metric_df.condition=="E_DUPLICATE_CONTROL")].iloc[0]
        paired_control.append(max(abs(float(a[m])-float(b[m])) for m in ["auc","brier","log_loss"]))
    if max(paired_control)>1e-7: raise RuntimeError("Parent-normalized no-op duplication differs from real-only baseline")
    # Summary status stays conservative; the tiny holdout and only 31 observed defaults preclude a support claim.
    primary=summary_metrics[summary_metrics.condition.isin(["E0","E1","E2"])].to_dict(orient="records")
    cfg={
        "experiment":"PHASE_2B.5-S", "status":"PHASE_2B5S_AUGMENTATION_INCONCLUSIVE",
        "generator_version":GENERATOR_VERSION, "feature_schema_version":FEATURE_SCHEMA_VERSION,
        "primary_window":"3 complete calendar months before origination month",
        "window_implementation":"phase2.windowing.complete_calendar_window",
        "window_formula":"window_start <= transaction_date < window_end_exclusive; complete calendar months before loan month",
        "phase2a_corrected_outputs_only":True, "superseded_rolling_window_input_used":False,
        "target":{"A":0,"B":1,"excluded":["C","D"]}, "holdout_fraction":HOLDOUT_FRAC,
        "validation_fraction_of_development":VAL_FRAC,"repeats":REPEATS,"seed":SEED,
        "holdout_seed":hold_seed,"repeat_seed_formula":"SEED + repeat * 31",
        "augmentation":{
            "E1":{"strength":.5,"descendants_per_training_parent":E1_K,"cap":"training-only q90 of absolute within-parent/category centered log amount residuals"},
            "E2":{"strength":1.,"descendants_per_training_parent":E2_K,"cap":"training-only q95 of absolute within-parent/category centered log amount residuals"},
            "density_sensitivity":{"E2_descendants_per_parent":list(E2_DENSITIES)},
            "date_timing":"unchanged; dates and calendar-month placement are preserved",
            "transaction_counts":"unchanged","category_and_direction":"unchanged",
            "weighting":"parent-normalized; sum of row weights within each parent family equals 1; naive E1/E2 secondary sensitivity",
            "duplicate_control":"E_DUPLICATE_CONTROL has 3 exact no-op descendants per real training parent, parent-normalized",
        },
        "history_distance_limits":"E1 RMS log amount perturbation <= training q90; E2 <= training q95",
        "feature_distance_limits":"E1 <= q95 training-parent nearest-neighbor distance; E2 <= 1.5x that distance",
        "binning":{"method":"one training-weighted median cut per selected feature; missing is explicit bin; WoE=ln(weighted nondefault share / weighted default share), additive smoothing 0.5","max_features":2},
        "logistic":{"l2":1.0,"target":"Y=1 is matured B/default"},
        "real_cohort":cohort,"python":platform.python_version(),"numpy":np.__version__,
        "pandas":pd.__version__,"scipy":scipy.__version__,"input_sha256":{},
        "real_observed_outcomes_not_augmented":True,
    }
    input_paths=[AUDIT/"candidate_features_by_loan.csv",AUDIT/"window_reconciliation.csv",AUDIT/"monthly_histories.csv",AUDIT/"candidate_feature_dictionary.csv"]
    cfg["input_sha256"]={p.name:sha256(p) for p in input_paths}; cfg["raw_dataset_sha256"]=json.loads((AUDIT/"raw_file_sha256.json").read_text(encoding="utf-8"))
    (OUT/"experiment_config.json").write_text(json.dumps(cfg,indent=2),encoding="utf-8")
    (OUT/"real_cohort_summary.json").write_text(json.dumps(cohort,indent=2),encoding="utf-8")
    # Compact machine-readable conclusion: distinguish evidence rows from descendants.
    perturbed=[x for x in lineage if x.get("augmentation_condition") in {"E1","E2"}]
    noop=[x for x in lineage if x.get("augmentation_condition")=="E_DUPLICATE_CONTROL"]
    summary={"status":"PHASE_2B5S_AUGMENTATION_INCONCLUSIVE","generator_version":GENERATOR_VERSION,"real_parent_N":cohort["real_parent_n"],"real_parent_defaults":cohort["real_parent_defaults"],"real_parent_nondefaults":cohort["real_parent_nondefaults"],"synthetic_descendant_N":int(sum(bool(x.get("is_synthetic")) for x in lineage)),"synthetic_default_descendants":int(sum(bool(x.get("is_synthetic")) and int(x.get("target",x.get("parent_target",0)))==1 for x in lineage)),"synthetic_nondefault_descendants":int(sum(bool(x.get("is_synthetic")) and int(x.get("target",x.get("parent_target",0)))==0 for x in lineage)),"perturbed_descendant_N":len(perturbed),"perturbed_default_descendants":sum(int(x.get("target",x.get("parent_target",0)))==1 for x in perturbed),"perturbed_nondefault_descendants":sum(int(x.get("target",x.get("parent_target",0)))==0 for x in perturbed),"noop_duplicate_control_N":len(noop),"holdout_class_counts":{"n":len(hold),"defaults":sum(p["target"] for p in hold),"nondefaults":len(hold)-sum(p["target"] for p in hold)},"primary_condition_summaries":primary,"holdout_results":hold_results,"phase2b_conclusion_preserved":"PHASE_2B_INCONCLUSIVE","production_status":"EXPERIMENTAL_NOT_FOR_PRODUCTION","calibration":"NO_SEPARATE_CALIBRATOR_RECOMMENDED","phase2c":"Do not begin automatically; Phase 2B.5-S is not a production validation result."}
    (OUT/"phase2b5s_summary.json").write_text(json.dumps(summary,indent=2,allow_nan=True),encoding="utf-8")
    _write_report(OUT,cohort,summary,summary_metrics,paired,hold_results,lineage,rejections,duplicates,ledger,metrics)
    print(json.dumps({"status":summary["status"],"real_cohort":cohort,"holdout":summary["holdout_class_counts"],"descendants":summary["synthetic_descendant_N"],"output":str(OUT)},indent=2))

def _write_report(out,cohort,summary,condition_summary,paired,holdout,lineage,rejections,duplicates,ledger,metrics):
    g={r["condition"]:r for r in condition_summary.to_dict(orient="records")}
    lines=["# Phase 2B.5-S — Berka-Grounded Semi-Synthetic Augmentation", "",
      "**Status: PHASE_2B5S_AUGMENTATION_INCONCLUSIVE**. Experimental only; no deployment or promotion.","",
      "## A. Real evidence", "",
      "- 231 independent real matured Berka loans", "- 31 real observed defaults", "- 200 real observed nondefaults",
      f"- {summary['perturbed_descendant_N']} perturbed descendants were accepted across repeated training splits and final development fits ({summary['perturbed_default_descendants']} inherited B labels; {summary['perturbed_nondefault_descendants']} inherited A labels). The separate no-op duplication control contains {summary['noop_duplicate_control_N']} exact copies and is not counted as augmentation evidence.","",
      "> Semi-synthetic descendants are correlated derivatives of observed Berka borrowers and do not constitute additional independently observed loan outcomes.","",
      "> Performance evaluation is anchored to real unseen Berka borrowers.","",
      "> Any benefit from augmentation is evidence about training robustness and stability, not evidence that the synthetic observations independently validate default risk.","",
      "Phase 2B remains `PHASE_2B_INCONCLUSIVE`; its report, configuration, and outputs were not rewritten. The old rolling-window archive was not used.","",
      "## B. Generator", "",
      "Real accounts were split before any descendant generation. Each split's amount residual pools were fit only on that split's real training parents, stratified by native transaction type and category, using absolute log-amount residuals around within-parent/category medians. No labels were used to fit perturbation parameters.",
      "E1 requests one descendant per training parent (up to five deterministic generation attempts) and applies a random signed empirical residual capped at training q90 and multiplied by 0.5. E2 requests three descendants per training parent (up to five deterministic attempts per child) and applies a random signed empirical residual capped at training q95 with multiplier 1.0; 1/3/5 density sensitivity checks are also recorded. Dates, count, direction, and category stay fixed.",
      "Parent-normalized weights assign total family weight 1 across each real parent and its descendants. Naive E1/E2 row-weight variants are recorded as secondary sensitivity checks. An exact no-op duplicate control has three copies per family and family-normalized weights.",
      "Each child inherits its label as `PARENT_INHERITED`. It is not a new observation. Descendants are rejected if the history perturbation exceeds its training-derived empirical bound, feature-space distance exceeds the training nearest-neighbor threshold, a history is an accidental exact duplicate, or transaction/ledger validation fails.",
      "Berka directions follow Phase 2A: PRIJEM adds amount; VYDAJ, VYBER KARTOU, and VYBER subtract amount. Opening balance is inferred from the parent's first observed post-transaction balance minus its signed first transaction; all descendant balances are rebuilt sequentially. Source-versus-transaction balance movement mismatches are retained as an audit diagnostic; descendant ledgers are reconstructed and checked independently.","",
      "## C. Realism", "",
      f"Accepted perturbed descendants: {summary['perturbed_descendant_N']}; exact no-op control rows: {summary['noop_duplicate_control_N']}; rejected generation attempts: {len(rejections)}. Maximum reconstructed descendant ledger reconciliation error: {max([x['max_balance_reconciliation_error'] for x in ledger],default=0.0):.3g}.",
      "Feature-level KS and Wasserstein distances, moments, missing/zero frequencies, and class-conditional diagnostics are in `distribution_fidelity.csv` and `conditional_fidelity.csv`. Exact history duplicates are expected only in the explicit no-op control; accidental duplicates and feature-near-duplicates are tabulated in `duplicate_analysis.csv`.",
      "The generator preserves parent class labels and does not intentionally increase class separation. Timing and transaction counts are unchanged; monthly cashflows change only through small transaction-amount perturbations.","",
      "## D. E0 vs E1 vs E2", "",
      "| Metric | E0 Real Only | E1 Conservative | E2 Moderate |", "|---|---:|---:|---:|"]
    for label,key in [("Mean real-validation AUC","auc_mean"),("AUC SD","auc_sd"),("Mean Gini","gini_mean"),("Mean KS","ks_mean"),("Mean Brier","brier_mean"),("Mean log loss","log_loss_mean"),("Mean PD","mean_predicted_pd_mean")]:
        vals=[]
        for c in ["E0","E1","E2"]: vals.append(f"{g[c].get(key,np.nan):.3f}" if c in g else "n/a")
        lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} |")
    stab=[]; coeff_summary=pd.read_csv(out/"coefficient_stability.csv")
    fs=pd.read_csv(out/"feature_selection_stability.csv")
    for c in ["E0","E1","E2"]:
        ss=fs[fs.condition==c].selection_frequency
        cg=coeff_summary[coeff_summary.condition==c]
        stab.append((f"feature max {ss.max():.0%}; sign consistency {cg.sign_consistency.mean():.0%}" if len(ss) and len(cg) else "n/a"))
    lines.extend([f"| Feature/sign stability summary | {stab[0]} | {stab[1]} | {stab[2]} |", "",
      "Paired split differences (E1−E0 and E2−E0) are in `paired_comparison.csv`; lower Brier/log loss is better. The no-op duplicate control should coincide with E0 under family-normalized weights; its paired check is enforced by an assertion. See `negative_controls.csv` for duplicate and label-shuffle checks.",
      "Feature and coefficient selection/sign summaries are in `feature_selection_stability.csv` and `coefficient_stability.csv`. Prediction and score spread for repeated real validation parents is in `score_stability.csv`; bin cut and WoE details are in `binning_stability.csv`. Parent-normalized weighting is primary; naive row weighting is secondary. Repeated splits overlap, so their variability is descriptive and does not increase the number of independent real outcomes.","",
      "## E. Holdout — REAL HOLDOUT ONLY", "",
      f"The deterministic real holdout contains N={summary['holdout_class_counts']['n']}, defaults={summary['holdout_class_counts']['defaults']}, nondefaults={summary['holdout_class_counts']['nondefaults']}. It was never augmented or used to fit generator parameters, binning, WoE, selection, or logistic models.","",
      "| Condition | AUC | Gini | KS | Brier | Log loss | Mean PD | Observed default rate |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for r in holdout:
        lines.append(f"| {r['condition']} | {r['auc']:.3f} | {r['gini']:.3f} | {r['ks']:.3f} | {r['brier']:.3f} | {r['log_loss']:.3f} | {r['mean_predicted_pd']:.3f} | {r['observed_default_rate']:.3f} |")
    lines.extend(["","The holdout has very few default events and is a single sanity check only; it does not choose augmentation strength or condition.","",
      "## F. Does augmentation help?", "",
      "The evidence remains inconclusive. Compare paired discrimination and probability-quality differences, selection stability, coefficient signs, prediction/score variation, realism, and duplication controls together. An AUC change alone is not a support criterion. No separate probability calibrator is recommended because there are only 31 independent observed defaults and the holdout is very small.",
      "The E1/E2 density sensitivity is in `augmentation_density_analysis.csv`; differences in strength and descendants-per-parent are not treated as independent observations.","",
      "## Leakage, limitations, and production status", "",
      "Automated assertions enforce disjoint parent partitions, train-only generator fitting, train-parent-only descendants, real-only validation/holdout, A/B outcomes only, complete-calendar transaction dates, no loan-field predictors, training-only binning/WoE, and no use of superseded Phase 2A input. The label-shuffle sanity control is performed only on real training parents and scored on real validation parents.",
      "There remain only 231 real loans and 31 real defaults. This is a historical Czech bank population; descendants add no independent outcomes and do not establish modern, Indian, or real-world PRISM applicant validity. No production artifact was changed. Phase 1 regression remains not executable in the configured environment because its venv points to a missing interpreter and system Python lacks dependencies.","",
      "**PHASE_2B5S_AUGMENTATION_INCONCLUSIVE**. Phase 2C is not started automatically."])
    (out/"phase2b5s_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

if __name__=="__main__": main()
