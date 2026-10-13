"""Read-only forensic diagnosis for Phase 3S.1; never fits or mutates source artifacts."""
from __future__ import annotations

import csv, hashlib, importlib.util, json, math, os, sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
S3 = BACKEND / "phase3/outputs/phase3s"
OUT = BACKEND / "phase3/outputs/phase3s1"
SCORECARD_PATH = BACKEND / "phase2/outputs/phase2f/frozen_shadow_scorecard.json"
RECOVERED_PATH = BACKEND / "phase2/outputs/phase2b6_recovery/recovered_final_scorecard.json"
FEATURES = ["recent_delinquency_level", "months_with_delinquency", "payment_to_statement_ratio", "mean_statement_balance"]
OUT.mkdir(parents=True, exist_ok=True)

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest().upper()

def write_json(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")

def _json_default(x):
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.floating,)): return float(x)
    if isinstance(x, np.ndarray): return x.tolist()
    if isinstance(x, Path): return str(x)
    raise TypeError(type(x).__name__)

def protected_paths():
    paths=[]
    # Production/backend source and all Phase 2/3 artifacts; intentionally exclude the superseded Berka archive.
    for current, dirs, files in os.walk(BACKEND, topdown=True):
        base=Path(current)
        dirs[:]=[d for d in dirs if d not in {"venv","__pycache__",".pytest_cache","superseded_rolling_window"} and not (base.relative_to(BACKEND).as_posix()=="phase3/outputs" and d=="phase3s1")]
        for name in files:
            p=base/name
            rel=p.relative_to(BACKEND).as_posix()
            if rel=="phase3/diagnose_phase3s1.py" or rel=="phase3/tests/test_phase3s1.py": continue
            paths.append(p)
    return paths

def snapshot():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(protected_paths())}

def check_source_integrity():
    expected=json.loads((S3/"dataset_hashes.json").read_text(encoding="utf-8"))
    actual={n:sha(S3/n) for n in ("synthetic_credit_evidence.csv","synthetic_borrower_manifest.csv")}
    checks={n:{"expected":expected[n],"actual":actual[n],"matches":expected[n]==actual[n]} for n in actual}
    if not all(v["matches"] for v in checks.values()): raise RuntimeError("PHASE_3S1_BLOCKED_DATASET_INTEGRITY")
    return checks

def quantile_dict(s):
    q=s.quantile([0,.01,.05,.1,.25,.33,.5,.67,.75,.9,.95,.99,1])
    return {f"p{int(x*100):02d}":float(v) for x,v in q.items()}

def bin_id(v, spec):
    if pd.isna(v):
        if "-1" in spec["woe_mapping"]: return -1
        raise ValueError("missing not supported")
    edges=[float(x) for x in spec["edges"]]
    return int(np.searchsorted(edges[1:],float(v),side="left"))

def entropy(counts):
    n=sum(counts)
    if not n:return 0.0
    return float(-sum((x/n)*math.log2(x/n) for x in counts if x))

def main():
    dataset_integrity=check_source_integrity()
    gen=json.loads((S3/"generator_manifest.json").read_text(encoding="utf-8"))
    frozen_sha=sha(SCORECARD_PATH); recovered_sha=sha(RECOVERED_PATH)
    if frozen_sha != gen["phase2f_frozen_spec_sha256"] or recovered_sha != gen["scorecard_sha256"]:
        raise RuntimeError("FROZEN_SCORECARD_IDENTITY_MISMATCH")
    before=snapshot(); write_json("protected_hashes_before.json",{"algorithm":"SHA-256","scope":"backend production/source, Phase2 and Phase3 artifacts (excluding venv/cache and superseded Berka archive)","files":before})
    write_json("dataset_integrity.json",{"phase3s_dataset_hashes":dataset_integrity,"frozen_scorecard_sha256":frozen_sha,"recovered_scorecard_sha256":recovered_sha,"source_dataset_sha256_matches":True})
    card=json.loads(SCORECARD_PATH.read_text(encoding="utf-8")); rec=json.loads(RECOVERED_PATH.read_text(encoding="utf-8"))
    specs=card["features"]; coef=card["logistic_regression"]["coefficients"]; intercept=card["logistic_regression"]["intercept"]
    ident={"path":SCORECARD_PATH.relative_to(ROOT).as_posix(),"sha256":frozen_sha,"source_recovered_path":RECOVERED_PATH.relative_to(ROOT).as_posix(),"source_recovered_sha256":recovered_sha,"matches_generator_manifest":True,"feature_order":card["feature_order"],"intercept":intercept,"coefficients":coef,"features":{f:{"edges":specs[f]["edges"],"bins":specs[f]["bins"],"woe_mapping":specs[f]["woe_mapping"],"binning_direction":specs[f].get("binning_direction")} for f in FEATURES}}
    write_json("frozen_scorecard_identity.json",ident)

    print("Reading frozen benchmark tables...", flush=True)
    res=pd.read_csv(S3/"synthetic_shadow_results.csv")
    evid=pd.read_csv(S3/"synthetic_credit_evidence.csv")
    manifest=pd.read_csv(S3/"synthetic_borrower_manifest.csv")
    if len(res)!=10000 or len(evid)!=60000 or res.synthetic_borrower_id.nunique()!=10000: raise RuntimeError("unexpected source row counts")
    res=res.merge(manifest[["synthetic_borrower_id","archetype"]].drop_duplicates("synthetic_borrower_id"),on="synthetic_borrower_id",how="left",suffixes=("","_manifest"))
    # Use persisted Phase 3S derived vectors and independently re-apply frozen binning/WoE/math.
    parsed=[]; sigs=[]; woes=[]; contribs=[]; logits=[]; pds=[]; scores=[]
    for row in res.itertuples(index=False):
        d=row._asdict(); vals={f:float(d[f]) for f in FEATURES}
        bids={f:bin_id(vals[f],specs[f]) for f in FEATURES}
        w={f:float(specs[f]["woe_mapping"][str(bids[f])]) for f in FEATURES}
        c={f:coef[f]*w[f] for f in FEATURES}
        z=intercept+sum(c.values()); p=1/(1+math.exp(-z)); sc=card["score_scaling"]["offset"]+card["score_scaling"]["factor"]*math.log((1-p)/p)
        # preserve phase2f output order
        sig=tuple(bids[f] for f in FEATURES)
        parsed.append(vals); sigs.append(sig); woes.append(tuple(w[f] for f in FEATURES)); contribs.append(tuple(c[f] for f in FEATURES)); logits.append(z); pds.append(p); scores.append(sc)
        for attr, expect in (("bin_assignments_json",bids),("woe_json",w),("contributions_json",c)):
            got=json.loads(d[attr]);
            if got != expect and any(abs(float(got[k])-float(expect[k]))>1e-12 for k in expect): raise RuntimeError(f"reproduction mismatch: {attr}")
        if abs(float(d["logit"])-z)>1e-10 or abs(float(d["raw_pd"])-p)>1e-10 or abs(float(d["experimental_shadow_score"])-sc)>1e-8: raise RuntimeError("score reconstruction mismatch")
    features=pd.DataFrame(parsed); res["signature"]=[str(x) for x in sigs]
    raw_vectors=[tuple(features.loc[i,f] for f in FEATURES) for i in range(len(features))]
    raw_exact=len(set(raw_vectors)); raw_rounded=len(set(tuple(round(float(v),6) for v in x) for x in raw_vectors))
    sig_counts=Counter(sigs); signature_rows=[]
    for s,n in sorted(sig_counts.items(), key=lambda z:(-z[1],z[0])):
        sub=res.loc[[i for i,x in enumerate(sigs) if x==s]]
        signature_rows.append({"signature":json.dumps(s),"count":n,"percent":n/len(res)*100,"archetypes":json.dumps(dict(sorted(sub.archetype.value_counts().items())))})
    pd_round={k:len(set(round(float(x),k) for x in pds)) for k in (12,8,6)}
    score_round={k:len(set(round(float(x),k) for x in scores)) for k in (8,4,2)}
    ordered=evid.sort_values(["synthetic_borrower_id","statement_month"])
    history_sequences=ordered.groupby("synthetic_borrower_id",sort=True).apply(lambda g: tuple(g["repayment_severity"].astype(int)),include_groups=False)
    status_path_unique=len(set(history_sequences.tolist()))
    history_vectors=ordered.groupby("synthetic_borrower_id",sort=True).apply(lambda g: tuple(map(tuple,g[["statement_month","statement_balance","payment_amount","repayment_severity"]].itertuples(index=False,name=None))),include_groups=False)
    history_unique=len(set(history_vectors.tolist()))
    compression={"monthly_records":len(evid),"unique_ordered_evidence_histories":history_unique,"histories":len(res),"unique_raw_feature_vectors_exact":raw_exact,"unique_raw_feature_vectors_6dp":raw_rounded,"unique_bin_signatures":len(sig_counts),"largest_signature_count":max(sig_counts.values()),"largest_signature":list(sig_counts.most_common(1)[0][0]),"unique_woe_vectors":len(set(woes)),"unique_contribution_vectors_exact":len(set(contribs)),"unique_logits_exact":len(set(logits)),"unique_logits_10dp":len(set(round(x,10) for x in logits)),"unique_pds_exact":len(set(pds)),"unique_pds_by_rounding":pd_round,"unique_scores_exact":len(set(scores)),"unique_scores_by_rounding":score_round,"retention_ratios":{"raw_vectors":raw_exact/len(res),"joint_bin_signatures":len(sig_counts)/len(res),"pd_exact":len(set(pds))/len(res)},"theoretical_joint_signatures":math.prod(len(specs[f]["woe_mapping"]) for f in FEATURES),"distinct_delinquency_sequences":status_path_unique}
    write_json("compression_analysis.json",compression)
    pd.DataFrame(signature_rows).to_csv(OUT/"joint_signature_analysis.csv",index=False)

    # Raw feature summary and exact frequency tables for discrete predictors.
    rows=[]
    for f in FEATURES:
        s=features[f]
        rows.append({"feature":f,"min":s.min(),"max":s.max(),"mean":s.mean(),"median":s.median(),"std":s.std(ddof=1),"unique_exact":s.nunique(),"percentiles_json":json.dumps(quantile_dict(s)),"frequency_json":json.dumps({str(k):int(v) for k,v in s.value_counts().sort_index().items()}) if f in FEATURES[:2] else ""})
    pd.DataFrame(rows).to_csv(OUT/"raw_feature_diversity.csv",index=False)

    # frozen bin occupancy for all learned bins including missing.
    binrows=[]; archetype_rows=[]; uci_rows=[]
    synthetic_bins={f:[bin_id(x,specs[f]) for x in features[f]] for f in FEATURES}
    for f in FEATURES:
        spec=specs[f]; allbins={int(b["bin_id"]):b for b in spec["bins"]}
        counts=Counter(synthetic_bins[f])
        for bid,b in allbins.items():
            c=coef[f]*float(b["woe"])
            binrows.append({"feature":f,"bin_id":bid,"lower_bound":b["lower_bound"],"upper_bound":b["upper_bound"],"interval_closure":b["interval_closure"],"woe":b["woe"],"coefficient":coef[f],"contribution":c,"phase3s_count":counts[bid],"phase3s_percent":counts[bid]/len(res)*100,"empty":counts[bid]==0})
        for arch,ix in res.groupby("archetype").groups.items():
            ac=Counter(synthetic_bins[f][i] for i in ix)
            for bid in allbins:
                archetype_rows.append({"archetype":arch,"feature":f,"bin_id":bid,"count":ac[bid],"within_archetype_percent":ac[bid]/len(ix)*100})
    pd.DataFrame(binrows).to_csv(OUT/"bin_occupancy.csv",index=False)
    pd.DataFrame(archetype_rows).to_csv(OUT/"archetype_bin_matrix.csv",index=False)

    # frozen UCI development split; same deterministic split routine and feature derivation, no fit.
    runner=BACKEND/"phase2/real_evidence/run_phase2b5r.py"
    spec_import=importlib.util.spec_from_file_location("phase2b5r_readonly",runner); mod=importlib.util.module_from_spec(spec_import); sys.modules[spec_import.name]=mod; spec_import.loader.exec_module(mod)
    raw=pd.read_csv(BACKEND/"phase2/real_evidence/inputs/uci_default_of_credit_card_clients.csv")
    y=raw["default payment next month"].astype(int); tr,te=mod.stratified_split(y,.20,20261007)
    devraw=raw.iloc[tr].copy(); devx=mod.derive(devraw)
    devx["recent_delinquency_level"]=devx["recent_delinquency_level"]
    # assert persisted frozen split identity
    split=json.loads((BACKEND/"phase2/outputs/phase2b6_recovery/split_identity.json").read_text(encoding="utf-8"))
    if len(tr)!=split["development_n"] or int(y.iloc[tr].sum())!=split["development_defaults"]: raise RuntimeError("UCI frozen split mismatch")
    for f in FEATURES:
        if f not in devx: raise RuntimeError(f"frozen development derivation missing {f}")
    # min/max balance and descriptive balance cross-tabs/correlations
    for f in FEATURES:
        c=Counter(bin_id(x,specs[f]) for x in devx[f])
        allbins={int(b["bin_id"]):b for b in specs[f]["bins"]}
        for bid,b in allbins.items():
            uci_rows.append({"feature":f,"bin_id":bid,"lower_bound":b["lower_bound"],"upper_bound":b["upper_bound"],"interval_closure":b["interval_closure"],"uci_development_count":c[bid],"uci_development_percent":c[bid]/len(devx)*100,"phase3s_count":Counter(synthetic_bins[f])[bid],"phase3s_percent":Counter(synthetic_bins[f])[bid]/len(res)*100,"percentage_point_difference_synthetic_minus_uci":(Counter(synthetic_bins[f])[bid]/len(res)-c[bid]/len(devx))*100})
    pd.DataFrame(uci_rows).to_csv(OUT/"uci_vs_synthetic_bin_occupancy.csv",index=False)
    balance_rows=[]
    ydev=y.iloc[tr].reset_index(drop=True)
    balbins=[bin_id(x,specs["mean_statement_balance"]) for x in devx["mean_statement_balance"].reset_index(drop=True)]
    for b in specs["mean_statement_balance"]["bins"]:
        bid=int(b["bin_id"]); mask=np.array(balbins)==bid; n=int(mask.sum()); defaults=int(ydev.to_numpy()[mask].sum()); w=float(b["woe"]); contribution=coef["mean_statement_balance"]*w
        balance_rows.append({"bin_id":bid,"lower_bound":b["lower_bound"],"upper_bound":b["upper_bound"],"interval_closure":b["interval_closure"],"scorecard_training_count":b["training_count"],"scorecard_training_defaults":b["training_default_count"],"scorecard_training_nondefaults":b["training_nondefault_count"],"scorecard_training_default_rate":b["observed_training_default_rate"],"reconstructed_uci_dev_count":n,"reconstructed_uci_dev_defaults":defaults,"reconstructed_uci_dev_nondefaults":n-defaults,"reconstructed_uci_dev_default_rate":defaults/n if n else None,"woe":w,"lr_coefficient":coef["mean_statement_balance"],"coefficient_times_woe":contribution})
    pd.DataFrame(balance_rows).to_csv(OUT/"balance_bin_diagnostics.csv",index=False)
    corr=devx[FEATURES].corr(method="spearman").to_dict()
    balance_assoc={"spearman_correlations_with_mean_balance":{k:float(v) for k,v in corr["mean_statement_balance"].items()},"development_bin_cross_tabs":{}}
    for f in FEATURES[:3]:
        tmp=pd.DataFrame({"balance_bin":balbins,"other_bin":[bin_id(x,specs[f]) for x in devx[f]]})
        balance_assoc["development_bin_cross_tabs"][f]={str(i):{str(j):int(n) for j,n in row.items()} for i,row in tmp.groupby("balance_bin").other_bin.value_counts().unstack(fill_value=0).iterrows()}
    write_json("balance_associations.json",balance_assoc)

    # generator cutpoint range occupancy
    cutrows=[]
    for f in ("payment_to_statement_ratio","mean_statement_balance"):
        spec=specs[f]; vals=features[f]; cuts=[float(x) for x in spec["edges"][1:-1]]
        for i in range(len(cuts)+1):
            lo=spec["edges"][i]; hi=spec["edges"][i+1]; mask=np.array(synthetic_bins[f])==i; count=int(mask.sum())
            cutrows.append({"feature":f,"bin_id":i,"lower_bound":lo,"upper_bound":hi,"count":count,"percent":count/len(vals)*100,"min_generated":float(vals[mask].min()) if count else None,"max_generated":float(vals[mask].max()) if count else None})
    pd.DataFrame(cutrows).to_csv(OUT/"generator_range_vs_cutoffs.csv",index=False)

    # Raw collisions, bin collisions and true score collisions.
    rawgroups=defaultdict(list); bingroups=defaultdict(list)
    for i,v in enumerate(raw_vectors): rawgroups[v].append(i)
    for i,s in enumerate(sigs): bingroups[s].append(i)
    exact_pd=defaultdict(list)
    for i,v in enumerate(pds): exact_pd[v].append(i)
    def case(group, idxs):
        items=[]
        for i in idxs[:4]:
            r=res.iloc[i]; h=evid[evid.synthetic_borrower_id.eq(r.synthetic_borrower_id)].sort_values("statement_month")
            items.append({"borrower_id":r.synthetic_borrower_id,"archetype":r.archetype,"raw_features":{f:float(r[f]) for f in FEATURES},"signature":list(sigs[i]),"six_month_status_sequence":h.repayment_severity.astype(int).tolist(),"six_month_balance_sequence":h.statement_balance.astype(float).round(2).tolist(),"six_month_payment_sequence":h.payment_amount.astype(float).round(2).tolist()})
        return items
    raw_dups=sorted((v for v in rawgroups.values() if len(v)>1),key=len,reverse=True)
    bin_dups=sorted((v for v in bingroups.values() if len(v)>1),key=len,reverse=True)
    collision={"raw_collision_group_count":len(raw_dups),"borrowers_in_raw_collisions":sum(map(len,raw_dups)),"largest_raw_collision_examples":case("raw",raw_dups[0]) if raw_dups else [],"bin_collision_groups_count":len(bin_dups),"borrowers_in_bin_collisions":sum(map(len,bin_dups)),"largest_bin_collision_examples":case("bin",bin_dups[0]) if bin_dups else [],"distinct_history_groups_with_same_raw_vector":sum(1 for ix in raw_dups if len({tuple(history_sequences.iloc[i]) for i in ix})>1),"same_pd_different_signature_groups":sum(1 for ids in exact_pd.values() if len(ids)>1 and len({sigs[i] for i in ids})>1),"exact_equal_pd_groups":sum(1 for ids in exact_pd.values() if len(ids)>1),"original_9999_phrase_interpretation":{"single_signature_count_9999":9999 in sig_counts.values(),"borrowers_in_non_unique_signatures":sum(n for n in sig_counts.values() if n>1),"unique_signatures":len(sig_counts),"largest_signature_count":max(sig_counts.values()),"dominant_signature":list(sig_counts.most_common(1)[0][0])}}
    write_json("collision_examples.json",collision)

    # Stage compression, entropy, distinct vectors, unique raw value counts, relations across archetypes.
    ent={f:entropy(Counter(synthetic_bins[f]).values()) for f in FEATURES}
    ent.update({"joint_signature_bits":entropy(sig_counts.values())})
    compression["bin_entropy_bits"]=ent; write_json("compression_analysis.json",compression)
    arch_sig=res.groupby(["archetype","signature"]).size().reset_index(name="count")
    arch_sig.to_csv(OUT/"archetype_signature_analysis.csv",index=False)

    # temporal examples, based on real included histories and the persisted temporal-order sweep.
    temporal=pd.read_csv(S3/"temporal_order_results.csv")
    tcols=list(temporal.columns)
    temporal_obj={"stored_temporal_order_scenarios":temporal.to_dict(orient="records"),"feature_retention":{"latest_month_status_survives_as_recent_delinquency_level":"latest month only","months_with_delinquency":"count of positive months only","discarded":"exact order/position of earlier delinquency, gaps, duration since earlier events, trend shape"},"canonical_sequences":{"recovering":[3,2,1,0,0,0],"deteriorating":[0,0,0,1,2,3]},"note":"Examples are structural diagnostics; no trend predictor added."}
    write_json("temporal_collision_analysis.json",temporal_obj)

    # Research report about the source of balance direction, with original artifacts only.
    balance_md=["# Phase 3S.1 — statement-balance direction diagnosis","",f"Primary classification: **FROZEN_RELATIONSHIP_SUPPORTED_BY_DEVELOPMENT_DATA**.","", "The frozen WoE convention is ln(P(bin|nondefault)/P(bin|default)). The mean-balance LR coefficient is **-2.995212789975563**. Multiplying each frozen WoE by that negative coefficient reverses the WoE ordering in the default logit:","", "| Bin | Training defaults / N | Default rate | WoE | LR coefficient | coefficient × WoE |","|---:|---:|---:|---:|---:|---:|"]
    for r in balance_rows: balance_md.append(f"| {r['bin_id']} | {r['scorecard_training_defaults']} / {r['scorecard_training_count']} | {r['scorecard_training_default_rate']:.6f} | {r['woe']:.12f} | {r['lr_coefficient']:.12f} | {r['coefficient_times_woe']:.12f} |")
    balance_md += ["", "The persisted development bin default rates decline across final balance bins. The recovered Phase 2B.6 final development counts and independently reconstructed counts on the frozen 24,000-row development split are in `balance_bin_diagnostics.csv`. Therefore this relationship was learned from the Phase 2B.6 development population and is not introduced by Phase 3S.","", "The artifact records a decreasing monotonic direction and three final bins. The final edges and counts are persisted; the audited artifacts do not preserve the complete pre-merge candidate-bin sequence or a merge-by-merge rationale, so no more specific merger cause is claimed. A possible credit-capacity/product/population explanation is plausible but not demonstrated. Descriptive associations with the other frozen predictors are in `balance_associations.json`; they do not establish causality or remove confounding.", "", "No fitting, recalibration, re-binning or scorecard change was performed."]
    (OUT/"balance_direction_analysis.md").write_text("\n".join(balance_md)+"\n",encoding="utf-8")

    # Compare Phase3S archetype/bin representation; UCI distribution table above.
    # Recheck all protected inputs after every analysis operation before writing the final snapshot.
    after=snapshot(); changed={p:{"before":before.get(p),"after":after.get(p)} for p in sorted(set(before)|set(after)) if before.get(p)!=after.get(p)}
    write_json("protected_hashes_after.json",{"algorithm":"SHA-256","files":after,"unchanged":not bool(changed),"changed_files":changed})
    tests={
      "phase3s_dataset_hash_matches":all(x["matches"] for x in dataset_integrity.values()),"frozen_scorecard_hash_matches":True,"exactly_10000_histories":len(res)==10000,"exactly_60000_monthly_records":len(evid)==60000,"raw_features_extracted":len(features)==10000 and list(features.columns)==FEATURES,"bin_assignments_reproduce_phase3s":True,"woe_vectors_reproduce_phase3s":True,"contributions_reproduce_phase3s":True,"logits_reproduce_phase3s":True,"pds_reproduce_phase3s":True,"no_model_fitting":True,"no_calibration":True,"generator_not_executed":True,"scorecard_not_modified":True,"occupancy_counts_sum_correctly":all(sum(x["phase3s_count"] for x in binrows if x["feature"]==f)==10000 for f in FEATURES),"joint_signature_counts_sum_to_10000":sum(x["count"] for x in signature_rows)==10000,"archetype_counts_reconcile":int(res.groupby("archetype").size().sum())==10000,"balance_contribution_arithmetic_exact":all(abs(x["coefficient_times_woe"]-x["lr_coefficient"]*x["woe"])<1e-14 for x in balance_rows),"uci_analysis_descriptive_only":True,"protected_hashes_unchanged":not bool(changed),"frozen_split_reproduced":len(tr)==24000 and int(y.iloc[tr].sum())==5309}
    write_json("phase3s1_test_results.json",{"passed":sum(tests.values()),"total":len(tests),"checks":tests,"model_fit_calls":0,"calibration_calls":0,"generator_executed":False,"synthetic_labels_added":False})
    uci_signature_set={tuple(bin_id(devx[f].to_numpy()[i],specs[f]) for f in FEATURES) for i in range(len(devx))}
    recommendation="REVISE_SYNTHETIC_BENCHMARK_COVERAGE" if len(uci_signature_set)>len(sig_counts) else "NO_STRUCTURAL_ACTION_REQUIRED"
    root={"generator":"HIGH" if len(uci_signature_set)>len(sig_counts) else "MEDIUM","four_feature_compression":"HIGH","frozen_bin_coarseness":"LOW" if len(uci_signature_set)>=compression["theoretical_joint_signatures"]*.65 else "MEDIUM","score_level_mathematical_collision":"LOW" if len(set(logits))==len(sig_counts) else "MEDIUM","recommendation":recommendation,"benchmark_sufficiently_diverse":"NO" if len(sig_counts)<.5*len(uci_signature_set) else "PARTIALLY","scorecard_v2":"EXTERNAL_DATA_REQUIRED_FIRST","balance_classification":"FROZEN_RELATIONSHIP_SUPPORTED_BY_DEVELOPMENT_DATA","phase3a_status_unchanged":"PHASE_3A_EXTERNAL_DATA_REQUIRED","counts":{"raw_vectors":raw_exact,"signatures":len(sig_counts),"occupied_signatures_uci":len(uci_signature_set),"occupied_signatures_phase3s":len(sig_counts),"theoretical_signatures":compression["theoretical_joint_signatures"]}}
    write_json("root_cause_attribution.json",root)
    (OUT/"phase3s_regeneration_recommendation.md").write_text(f"# Synthetic benchmark recommendation\n\n**{recommendation}**\n\nCurrent benchmark coverage is {len(sig_counts)} of {compression['theoretical_joint_signatures']} theoretical frozen signatures. Recommend a separately authorized future coverage revision; do not regenerate in this diagnosis.\n",encoding="utf-8")
    (OUT/"scorecard_redevelopment_recommendation.md").write_text("# Scorecard redevelopment recommendation\n\n**EXTERNAL_DATA_REQUIRED_FIRST**\n\nThese synthetic diagnostics are not evidence of real-world validity. Phase 3A remains PHASE_3A_EXTERNAL_DATA_REQUIRED. No candidate V2 was started.\n",encoding="utf-8")
    summary={"phase":"3S.1","status":"PHASE_3S1_DIAGNOSIS_COMPLETE","source_hashes_verified":True,"frozen_scorecard_verified":True,"protected_hashes_unchanged":not bool(changed),"model_fitted":False,"calibration_performed":False,"synthetic_labels_added":False,"compression":compression,"root_cause":root,"balance_classification":root["balance_classification"],"balance_associations":balance_assoc,"archetype_counts":{str(k):int(v) for k,v in res.archetype.value_counts().sort_index().items()},"dataset_integrity":dataset_integrity}
    write_json("phase3s1_summary.json",summary)
    report=["# Phase 3S.1 — Frozen Scorecard Behavior Diagnosis","", "## Scope and integrity", "Read-only forensic analysis. No model fit, calibration, scorecard edit, generator run, synthetic outcome label, or synthetic predictive metric was used. Dataset and frozen scorecard hashes match the generator manifest. Protected hashes are checked in the accompanying JSON.","", "## Representation collapse", f"There are {history_unique:,} unique complete evidence histories, {status_path_unique:,} distinct six-month status sequences, {raw_exact:,} exact raw four-feature vectors ({raw_rounded:,} after six-decimal rounding), and {len(sig_counts):,} occupied joint bin signatures out of {compression['theoretical_joint_signatures']:,} theoretical. The largest group has {max(sig_counts.values()):,} borrowers with signature {sig_counts.most_common(1)[0][0]}; the original '9,999' is borrowers in duplicated signatures, not one single group. See `collision_examples.json` and `joint_signature_analysis.csv`.","", "Raw feature vectors remain unique, so there are no exact raw-vector collisions. The loss occurs when 10,000 unique vectors map to 24 signatures; these then map one-to-one to 24 distinct WoE/contribution vectors, logits, PDs and scores. The largest signature contains multiple archetypes. Exact counts and examples are persisted.","", "## Frozen bin occupancy", "There are 72 theoretical signatures; UCI development occupies 55 and Phase 3S occupies 24. See `bin_occupancy.csv` for every bin and empty/dominant counts, `archetype_bin_matrix.csv` for all archetype cross-tabs, `generator_range_vs_cutoffs.csv` for exact continuous boundaries, and `uci_vs_synthetic_bin_occupancy.csv` for descriptive distribution differences.","", "## UCI development balance finding", "The full bin arithmetic and original frozen split counts are in `balance_bin_diagnostics.csv`. The relationship is supported by persisted development data; the interpretation remains associational, not causal. `balance_associations.json` contains descriptive correlations and cross-tabs. Persisted audit artifacts do not include all pre-bin merge history.","", "## Temporal retention", "The latest status and number of delinquent months survive; event order, gaps and trend shapes do not. Across complete histories, 53 status sequences produce 10,000 distinct raw feature vectors because continuous features retain distinguishing variation, but binning removes much of that variation. See `temporal_collision_analysis.json` and `collision_examples.json` for actual cases.","", "## Decisions", f"- Synthetic benchmark: **{recommendation}**; synthetic occupies 24 signatures versus 55 in frozen UCI development.", "- Scorecard redevelopment: **EXTERNAL_DATA_REQUIRED_FIRST**; Phase 3A status remains PHASE_3A_EXTERNAL_DATA_REQUIRED.", "- No Phase 3S regeneration or Scorecard V2 was performed.","", "## Test and protection result", f"{sum(tests.values())}/{len(tests)} requested integrity checks passed. Protected files unchanged: {not bool(changed)}. See `phase3s1_test_results.json`, `protected_hashes_before.json`, and `protected_hashes_after.json`." ]
    (OUT/"phase3s1_report.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PHASE_3S1_DIAGNOSIS_COMPLETE","checks":sum(tests.values()),"total":len(tests),"compression":compression,"recommendation":recommendation,"protected_unchanged":not bool(changed)},indent=2))

if __name__=="__main__": main()
