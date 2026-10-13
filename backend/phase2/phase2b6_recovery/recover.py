"""Instrument the original Phase 2B.6 final-fit functions once; no methodology copy."""
from __future__ import annotations
import csv,hashlib,importlib.metadata,json,math,platform,sys
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
from scipy.special import expit

PHASE2=Path(__file__).resolve().parents[1]
REPO=PHASE2.parents[1]
OUT=PHASE2/"outputs"/"phase2b6_recovery"
TOLERANCE=OUT/"reproduction_tolerances.json"
RUN_MARKER=OUT/"recovery_execution.json"

def _sha_bytes(data): return hashlib.sha256(data).hexdigest().upper()
def _sha_file(path): return _sha_bytes(Path(path).read_bytes())
def _json(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
def _finite(v):
    v=float(v)
    return v if math.isfinite(v) else ("-Infinity" if v<0 else "Infinity")
def _index_hash(values): return _sha_bytes(",".join(map(str,values)).encode())
def _version(name):
    try: return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError: return None

def _index_of_original_bin(value,edges):
    # Independent plain boundary assignment for pd.cut(right=True, include_lowest=True).
    if pd.isna(value): return -1
    i=int(np.searchsorted(np.asarray(edges[1:],dtype=float),float(value),side="left"))
    if i<0 or i>=len(edges)-1: raise ValueError("UNMAPPABLE_FROZEN_BIN")
    return i

def _manual_one(raw_features,artifact):
    woe={}; bins={}
    for feature in artifact["feature_order"]:
        value=raw_features[feature]; spec=artifact["features"][feature]
        idx=_index_of_original_bin(value,spec["edges"])
        mapping={int(k):float(v) for k,v in spec["woe_mapping"].items()}
        if idx not in mapping: raise ValueError(f"UNMAPPABLE_FROZEN_BIN:{feature}:{idx}")
        bins[feature]=idx; woe[feature]=mapping[idx]
    logit=float(artifact["logistic_regression"]["intercept"]+sum(artifact["logistic_regression"]["coefficients"][f]*woe[f] for f in artifact["feature_order"]))
    return {"bins":bins,"woe":woe,"logit":logit,"pd":float(expit(logit))}

def recover():
    OUT.mkdir(parents=True,exist_ok=True)
    if RUN_MARKER.exists(): raise RuntimeError("Recovery runner is one-shot and has already executed; refusing another fit")
    if not TOLERANCE.is_file(): raise RuntimeError("Predeclared reproduction_tolerances.json is required before fitting")
    tolerances=json.loads(TOLERANCE.read_text(encoding="utf-8"))
    # Import the exact Phase 2B.5-R/2B.6 implementation, not a rewritten algorithm.
    evidence_dir=PHASE2/"real_evidence"
    sys.path.insert(0,str(evidence_dir))
    import run_phase2b5r as base
    import run_phase2b6 as original
    source=Path(base.INPUT); historical=json.loads((PHASE2/"outputs"/"phase2b6"/"phase2b6_summary.json").read_text(encoding="utf-8"))
    historical_metrics=json.loads((PHASE2/"outputs"/"phase2b6"/"test_metrics.json").read_text(encoding="utf-8"))
    data_hash=_sha_file(source)
    if data_hash!=str(historical["input_sha256"]).upper(): raise RuntimeError("PHASE_2B6R_BLOCKED_DATASET_IDENTITY: source SHA does not match original audit")
    df=pd.read_csv(source); target=base.TARGET; y=df[target].astype(int); X=base.derive(df)
    identity={"source_file":str(source.resolve()),"sha256":data_hash,"row_count":int(len(df)),"column_count":int(len(df.columns)),"borrower_id_column":"ID","unique_borrowers":int(df.ID.nunique()),"target_column":target,"defaults":int(y.sum()),"nondefaults":int((y==0).sum()),"row_exclusions":0,"resulting_borrower_count":int(len(df)),"original_audit_sha256":historical["input_sha256"],"matches_original_audit":True}
    if len(df)!=30000 or len(df.columns)!=25 or df.ID.nunique()!=len(df) or int(y.sum())!=6636 or int((y==0).sum())!=23364:
        raise RuntimeError("PHASE_2B6R_BLOCKED_DATASET_IDENTITY: expected dataset counts/columns differ")
    dev,test=base.stratified_split(y,.20,base.SEED)
    split={"algorithm":"run_phase2b5r.stratified_split; NumPy default_rng; classes traversed in (0,1); test n=round(class_count*0.20); final train/test positions sorted","seed":int(base.SEED),"test_fraction":0.2,"development_n":int(len(dev)),"test_n":int(len(test)),"development_defaults":int(y.iloc[dev].sum()),"test_defaults":int(y.iloc[test].sum()),"development_indices_sha256":_index_hash(dev),"test_indices_sha256":_index_hash(test),"development_borrower_ids_sha256":_index_hash(df.ID.iloc[dev]),"test_borrower_ids_sha256":_index_hash(df.ID.iloc[test]),"test_borrower_ids_in_prediction_order":df.ID.iloc[test].astype(int).tolist()}
    if len(test)!=6000 or int(y.iloc[test].sum())!=1327 or split["test_n"]!=historical_metrics["n_test"] or split["test_defaults"]!=historical_metrics["defaults_test"]:
        raise RuntimeError("PHASE_2B6R_BLOCKED_SPLIT_IDENTITY: deterministic split does not reproduce original test counts")
    env={"python":platform.python_version(),"python_implementation":platform.python_implementation(),"numpy":np.__version__,"pandas":pd.__version__,"scipy":scipy.__version__,"scikit_learn":_version("scikit-learn"),"relevant_dependencies":{"NumPy":"runtime","pandas":"runtime","SciPy":"optimizer and sigmoid"},"phase2b6_specific_environment_manifest_found":False,"related_repo_lock":{"path":"backend/requirements-backend-py312.lock.txt","numpy":"2.5.1","pandas":"3.0.5","scipy":"1.18.0","note":"lock is for a Python 3.12 backend environment; Python 3.12 unavailable here, so it was not installed or substituted"}}
    _json("dataset_identity.json",identity); _json("split_identity.json",split); _json("environment_manifest.json",env)
    # Ensure exact original methods/config before the only final scorecard fit.
    expected_features=historical_metrics["model_features"]
    method={"source_runner":"backend/phase2/real_evidence/run_phase2b6.py","base_feature_runner":"backend/phase2/real_evidence/run_phase2b5r.py","final_fit_call":"fit_spec(X.iloc[dev], y.iloc[dev], X.iloc[test], FEATURES, PRIMARY)","source_feature_pool":base.FEATURES,"historical_final_feature_order":expected_features,"primary_config":original.PRIMARY,"final_fit_count":1,"cross_validation_fits_run":0,"sensitivity_fits_run":0,"test_used_for_fit_or_selection":False,"score_scaling_in_original_phase2b6":"not present; original runner reports raw LR probabilities only","score_calibration":"not applied; calibration intercept/slope is a test diagnostic only"}
    if base.FEATURES!=["worst_delinquency_level","months_with_delinquency","recent_delinquency_level","mean_statement_balance","payment_to_statement_ratio"]:
        raise RuntimeError("Frozen source feature pool changed")
    # One transparent passthrough wrapper captures the exact optimizer result while retaining the original call.
    original_minimize=base.minimize; optimizer_results=[]
    def capture_minimize(*args,**kwargs):
        result=original_minimize(*args,**kwargs)
        optimizer_results.append({"success":bool(result.success),"status":int(result.status),"message":str(result.message),"iterations":int(getattr(result,"nit",-1)),"function_evaluations":int(getattr(result,"nfev",-1)),"gradient_norm":float(np.linalg.norm(result.jac)) if getattr(result,"jac",None) is not None else None})
        return result
    base.minimize=capture_minimize
    final=original.fit_spec(X.iloc[dev],y.iloc[dev],X.iloc[test],base.FEATURES,original.PRIMARY)
    method["final_fit_count"]=1
    method["final_selected_feature_order"]=list(final["features"])
    if list(final["features"])!=expected_features:
        _json("recovery_mismatch.json",{"status":"PHASE_2B6R_REPRODUCTION_MISMATCH","reason":"recovered selected feature order differs from frozen historical test metrics","recovered":final["features"],"historical":expected_features,"environment":env})
        raise RuntimeError("PHASE_2B6R_REPRODUCTION_MISMATCH: final feature order differs; no alternative fit attempted")
    # Historical test metrics are evaluated only after the frozen development model is fit.
    test_prediction=original.predict(final,final["apply_woe"])
    recovered_metrics=base.metrics(y.iloc[test],test_prediction)
    # Reproduce original calibration diagnostics only; this fit never transforms predictions or the scorecard.
    diag=base.calibration(y.iloc[test],test_prediction)
    recovered_metrics.update(diag); recovered_metrics.update({"n_test":int(len(test)),"defaults_test":int(y.iloc[test].sum()),"model_features":list(final["features"])})
    compared={k:{"historical":float(historical_metrics[k]),"recovered":float(recovered_metrics[k]),"absolute_difference":abs(float(historical_metrics[k])-float(recovered_metrics[k])),"within_tolerance":abs(float(historical_metrics[k])-float(recovered_metrics[k]))<=float(tolerances["historical_metrics_absolute_tolerance"])} for k in ("auc","gini","ks","brier","log_loss","observed_default_rate","mean_predicted_pd","calibration_intercept","calibration_slope")}
    counts_exact=int(recovered_metrics["n_test"])==int(historical_metrics["n_test"]) and int(recovered_metrics["defaults_test"])==int(historical_metrics["defaults_test"])
    metrics_match=counts_exact and all(v["within_tolerance"] for v in compared.values())
    train_y=y.iloc[dev].to_numpy(int); train_good=int((train_y==0).sum()); train_bad=int((train_y==1).sum())
    bins={}; provenance={}
    for f in final["features"]:
        b=final["binners"][f]; edges=[_finite(x) for x in b["edges"]]; rows=[]
        for row in b["rows"]:
            idx=int(row["bin_index"]); mapping=float(b["mapping"][idx])
            rows.append({"bin_id":idx,"lower_bound":_finite(row["lower"]) if row["lower"] is not None else None,"upper_bound":_finite(row["upper"]) if row["upper"] is not None else None,"missing_bin":bool(row["missing_bin"]),"interval_closure":"missing-category" if idx==-1 else ("[-inf, upper]" if idx==0 else "(lower, upper]"),"training_count":int(row["population"]),"training_nondefault_count":int(row["good"]),"training_default_count":int(row["bad"]),"observed_training_default_rate":float(row["event_rate"]),"woe":mapping,"iv_contribution":float(row["iv_component"])})
        bins[f]={"edges":edges,"right_closed":True,"include_lowest":True,"duplicates":"drop","binning_direction":b["direction"],"woe_convention":"ln(P(bin|nondefault)/P(bin|default))","jeffreys_smoothing":0.5,"good_total":train_good,"bad_total":train_bad,"woe_mapping":{str(int(k)):float(v) for k,v in b["mapping"].items()},"bins":rows,"missing_semantics":"separate learned bin id -1 when present and support-qualified; otherwise missing input is unmappable and fails closed","out_of_range_semantics":"outer edges are -Infinity/+Infinity; numeric values below/above observed fit range map to first/last learned interval; no clipping"}
        provenance[f]={"binning_origin":"original final development-set fit via run_phase2b6.learn_binner","source":"backend/phase2/real_evidence/run_phase2b6.py","source_sha256":_sha_file(PHASE2/"real_evidence"/"run_phase2b6.py"),"woe_origin":"original final development-set tabulation and Jeffreys-smoothed map","training_rows":len(dev)}
    beta=np.asarray(final["beta"],float)
    lr={"intercept":float(beta[0]),"coefficients":{f:float(beta[i+1]) for i,f in enumerate(final["features"])},"feature_order":list(final["features"]),"solver":"scipy.optimize.minimize(method='BFGS')","objective":"sum(logaddexp(0, X beta) - y*(X beta)) + 0.5*l2*sum(non-intercept coefficients^2)","regularization":{"l2":float(original.PRIMARY["l2"]),"intercept_penalized":False},"class_weight":None,"initial_parameters":"all zeros","random_state":None,"convergence":{"fit_lr_returned_optimizer_result":False,"diagnostic_result_captured_by_passthrough":optimizer_results[0] if optimizer_results else None,"optimizer_call_count_including_historical_test_calibration_diagnostic":len(optimizer_results),"scorecard_final_fit_calls":1}}
    artifact={"artifact_type":"EXPERIMENTAL_RECOVERED_PHASE_2B6_SCORECARD","recovery_status":"DETERMINISTIC_REPRODUCTION_PENDING_METRIC_CHECK","source_phase":"Phase 2B.6 final development-set fit","source_status":"PHASE_2B6_INCONCLUSIVE","original_artifact_was_persisted":False,"dataset_sha256":data_hash,"outer_split_seed":int(base.SEED),"feature_order":list(final["features"]),"source_feature_derivation":"run_phase2b5r.derive; no edits","primary_config":original.PRIMARY,"features":bins,"logistic_regression":lr,"score_scaling":{"used_in_original_phase2b6":False,"base_score":None,"pdo":None,"base_odds":None,"factor":None,"offset":None,"convention":None,"reason":"The Phase 2B.6 executable contains no PDO/score-scaling function and reports raw LR probabilities; no scaling is fabricated."},"calibration":{"applied_to_pd":False,"test_diagnostic_only":True,"calibrator_artifact":None},"provenance":{"runner":"backend/phase2/real_evidence/run_phase2b6.py","runner_sha256":_sha_file(PHASE2/"real_evidence"/"run_phase2b6.py"),"base_runner":"backend/phase2/real_evidence/run_phase2b5r.py","base_runner_sha256":_sha_file(PHASE2/"real_evidence"/"run_phase2b5r.py"),"per_feature_bins":provenance,"coefficients_origin":"single original-procedure final fit on development rows only","intercept_origin":"single original-procedure final fit on development rows only","training_good_count":train_good,"training_default_count":train_bad}}
    _json("recovery_method.json",method)
    artifact_path=OUT/"recovered_final_scorecard.json"; artifact_path.write_text(json.dumps(artifact,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    artifact_hash=_sha_file(artifact_path); (OUT/"recovered_final_scorecard.sha256").write_text(artifact_hash+"  recovered_final_scorecard.json\n",encoding="ascii")
    pred_path=OUT/"recovered_test_predictions.csv"
    with pred_path.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["ID","target","predicted_pd"])
        for identifier,target_value,pd_value in zip(df.ID.iloc[test],y.iloc[test],test_prediction): w.writerow([int(identifier),int(target_value),format(float(pd_value),".17g")])
    (OUT/"recovered_test_predictions.sha256").write_text(_sha_file(pred_path)+"  recovered_test_predictions.csv\n",encoding="ascii")
    _json("historical_metric_comparison.json",{"status":"PASS" if metrics_match else "MISMATCH","predeclared_absolute_tolerance":tolerances["historical_metrics_absolute_tolerance"],"counts_exact":counts_exact,"metrics":compared,"historical_artifact":historical_metrics,"recovered_metrics":recovered_metrics,"no_test_informed_changes":True})
    manual=[]
    test_features=X.iloc[test]
    for pos in range(min(10,len(test))):
        row=test_features.iloc[pos]; raw={f:float(row[f]) for f in final["features"]}
        scored_woe={f:float(final["apply_woe"].iloc[pos][f]) for f in final["features"]}
        exact_woe=_manual_one(raw,artifact)
        manual_logit=float(lr["intercept"]+sum(lr["coefficients"][f]*scored_woe[f] for f in final["features"]))
        manual_pd=float(expit(manual_logit)); fitted=float(test_prediction[pos])
        manual.append({"ID":int(df.ID.iloc[test[pos]]),"raw_features":raw,"woe_from_original_encoded_frame":scored_woe,"woe_from_independent_boundary_assignment":exact_woe["woe"],"manual_logit":manual_logit,"manual_pd":manual_pd,"fitted_pd":fitted,"absolute_prediction_error":abs(manual_pd-fitted)})
    maxerr=max(r["absolute_prediction_error"] for r in manual)
    _json("manual_reconstruction_results.json",{"rows_checked":len(manual),"maximum_absolute_prediction_error":maxerr,"tolerance":tolerances["manual_prediction_absolute_tolerance"],"all_within_tolerance":maxerr<=tolerances["manual_prediction_absolute_tolerance"],"rows":manual})
    _json("recovery_execution.json",{"scorecard_final_fit_count":1,"fit_spec_calls":1,"cross_validation_fits":0,"sensitivity_fits":0,"final_lr_optimizer_result":optimizer_results[0] if optimizer_results else None,"historical_calibration_diagnostic_runs":1,"fit_completed":True})
    return {"metrics_match":metrics_match,"features":final["features"],"artifact_sha256":artifact_hash,"max_manual_error":maxerr}

if __name__=="__main__": print(json.dumps(recover(),indent=2))
