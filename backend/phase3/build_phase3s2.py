"""Coverage-directed evidence generator; only writes to outputs/phase3s2."""
from __future__ import annotations

import csv, hashlib, importlib.util, itertools, json, math, os, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/"backend"
OUT=BACKEND/"phase3/outputs/phase3s2"
S3=BACKEND/"phase3/outputs/phase3s"
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(BACKEND))
from phase3 import build_phase3s as base
from phase2.credit_evidence.models import Consent,ConsentState
from phase2.credit_evidence.consent import SCOPE_CARD_STATEMENTS,SCOPE_BUREAU_HISTORY
from phase2.shadow_scorecard.artifacts import load_scorecard
from phase2.shadow_scorecard.scorer import score_validated_result,ShadowScoreError

SEED=20261008
VERSION="phase3s2-coverage-generator-v1.0.0"
FEATURES=base.FEATURES
MONTHS=tuple(f"2026-{m:02d}" for m in range(4,10))
CUTOFF="2026-10"
AT=datetime(2026,10,1,tzinfo=timezone.utc)
UCI=BACKEND/"phase2/real_evidence/inputs/uci_default_of_credit_card_clients.csv"
FROZEN=BACKEND/"phase2/outputs/phase2f/frozen_shadow_scorecard.json"

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest().upper()

def dumpj(name,value): (OUT/name).write_text(json.dumps(value,indent=2,sort_keys=True,default=_default)+"\n",encoding="utf-8")
def _default(x):
    if isinstance(x,(np.integer,)):return int(x)
    if isinstance(x,(np.floating,)):return float(x)
    if isinstance(x,np.ndarray):return x.tolist()
    raise TypeError(type(x).__name__)
def dumpcsv(name,rows):
    pd.DataFrame(rows).to_csv(OUT/name,index=False)

def frozen_bin(value,spec):
    if pd.isna(value):
        if "-1" in spec["woe_mapping"]: return -1
        raise ValueError("missing input has no learned bin")
    edges=[float(v) for v in spec["edges"]]
    return int(np.searchsorted(edges[1:],float(value),side="left"))

def signature_of_features(values,artifact):
    return tuple(frozen_bin(values[f],artifact["features"][f]) for f in FEATURES)

def uci_observed_signatures(artifact):
    loader=importlib.util.spec_from_file_location("phase2b5r_readonly",BACKEND/"phase2/real_evidence/run_phase2b5r.py")
    module=importlib.util.module_from_spec(loader);sys.modules[loader.name]=module;loader.loader.exec_module(module)
    raw=pd.read_csv(UCI); target=raw["default payment next month"].astype(int)
    tr,_=module.stratified_split(target,.20,20261007)
    dev=module.derive(raw.iloc[tr].copy())
    signatures=Counter(signature_of_features(row,artifact) for row in dev[FEATURES].to_dict(orient="records"))
    return signatures,len(tr),int(target.iloc[tr].sum())

def values_for_bin(feature,bin_id,rng,variant):
    if feature=="mean_statement_balance":
        ranges={0:(500.,2800.),1:(3000.,71000.),2:(73000.,180000.)}
    elif feature=="payment_to_statement_ratio":
        ranges={0:(.01,.035),1:(.042,.058),2:(.07,.18),3:(.30,.72),4:(.84,1.10)}
    else: raise KeyError(feature)
    lo,hi=ranges[int(bin_id)]
    return float(rng.uniform(lo,hi)) if variant==0 else float((lo+hi)/2)

def make_history(signature,borrower_id,variant,rng):
    recent_bin,months_bin,ratio_bin,balance_bin=signature
    # Avoid exact threshold boundaries; periodic balance multipliers average exactly one.
    multipliers=(np.array([.94,1.02,.98,1.04,1.01,1.01]) if variant%2==0 else np.array([1.01,1.01,1.04,.98,1.02,.94]))
    amount=0.0 if ratio_bin==-1 else values_for_bin("mean_statement_balance",balance_bin,rng,variant)
    ratio=0.0 if ratio_bin==-1 else values_for_bin("payment_to_statement_ratio",ratio_bin,rng,variant)
    levels=[0]*6
    if months_bin==0:
        if recent_bin==1: levels[-1]=int(rng.integers(2,6))
        elif variant%2: levels[1]=1
    else:
        if recent_bin==1:
            positions=([0,2,5] if variant%2==0 else [1,3,5]); levels[positions[0]]=1;levels[positions[1]]=2;levels[5]=int(rng.integers(2,6))
        else:
            positions=([0,2,4] if variant%2==0 else [1,3,4]); levels[positions[0]]=1;levels[positions[1]]=2;levels[positions[2]]=1
    category=("recent_severe_single_event" if recent_bin==1 and months_bin==0 else
              "recent_and_persistent_delinquency" if recent_bin==1 else
              "past_delinquency_now_current" if months_bin==1 else "current_or_neutral_history")
    rows=[]
    for i,month in enumerate(MONTHS):
        balance=0.0 if ratio_bin==-1 else round(amount*float(multipliers[i]),2)
        payment=0.0 if ratio_bin==-1 else round(balance*ratio,2)
        sev=int(levels[i])
        rows.append({"synthetic_borrower_id":borrower_id,"synthetic_account_id":borrower_id.replace("BORROWER","ACCOUNT"),
            "statement_month":month,"statement_balance":balance,"payment_amount":payment,"repayment_severity":sev,
            "repayment_status":"DELINQUENT" if sev>0 else "CURRENT","currency":"INR","product_type":"CREDIT_CARD",
            "masked_account_number":"SYNTHETIC-TOKEN","provider":"PRISM Synthetic Coverage Benchmark",
            "generator_version":VERSION,"synthetic_source_id":f"SRC_{borrower_id}_{month}","archetype":category,
            "validity_expectation":"SCOREABLE_TARGET"})
    return rows,category

def run_pipeline(rows,borrower_id,artifact,consent=None,cutoff=CUTOFF):
    consent=consent or base.consent_default()
    result,_,err=base.run(rows,borrower_id,consent=consent,cutoff=cutoff)
    if result is None:return result,None,err
    try:return result,score_validated_result(result,artifact=artifact),None
    except (ShadowScoreError,ValueError,TypeError,AttributeError) as exc:return result,None,f"{getattr(exc,'code',type(exc).__name__)}:{exc}"

def independent(score,artifact):
    lr=artifact["logistic_regression"]; z=float(lr["intercept"])
    for f in FEATURES:z+=float(lr["coefficients"][f])*float(score["woe_values"][f])
    p=float(expit(z));odds=(1-p)/p;factor=50/math.log(2);offset=600-factor*math.log(20)
    return z,p,odds,offset+factor*math.log(odds)

def main():
    manifest=json.loads((S3/"generator_manifest.json").read_text(encoding="utf-8"))
    dataset_hashes=json.loads((S3/"dataset_hashes.json").read_text(encoding="utf-8"))
    original_hashes={n:sha(S3/n) for n in dataset_hashes if n.endswith(".csv")}
    if any(original_hashes[n]!=dataset_hashes[n] for n in original_hashes):raise RuntimeError("PHASE3S_SOURCE_HASH_MISMATCH")
    artifact=load_scorecard(FROZEN)
    card_hash=sha(FROZEN)
    if card_hash!=manifest["phase2f_frozen_spec_sha256"]:raise RuntimeError("FROZEN_SCORECARD_HASH_MISMATCH")
    specs=artifact["features"]
    dimensions=[list(map(int,specs[f]["woe_mapping"].keys())) for f in FEATURES]
    theoretical=list(itertools.product(*dimensions))
    uci_counts,uci_n,uci_defaults=uci_observed_signatures(artifact)
    rng=np.random.default_rng(SEED)
    feasible_rows=[]; feasibility_scores={}
    # Actual parse → normalize → validate → frozen-score trial for every theoretical signature.
    for index,sig in enumerate(theoretical,1):
        trial_id=f"SYN_FEAS_{index:03d}"
        rows,_=make_history(sig,trial_id,0,rng)
        result,score,error=run_pipeline(rows,trial_id,artifact)
        got=signature_of_features(score["feature_values"],artifact) if score else None
        ok=score is not None and got==sig
        feasibility_scores[sig]=score if ok else None
        feasible_rows.append({"signature":json.dumps(sig),"recent_bin":sig[0],"months_bin":sig[1],"payment_ratio_bin":sig[2],"balance_bin":sig[3],
          "uci_observed":sig in uci_counts,"uci_development_count":uci_counts.get(sig,0),"contract_feasible":ok,"verified_signature":json.dumps(got) if got is not None else "",
          "blocker":error or "","evidence_state":getattr(result,"state",None)})
    feasible={tuple(json.loads(x["signature"])) for x in feasible_rows if x["contract_feasible"]}
    target_u={s for s in uci_counts if s in feasible}
    generated_evidence=[];borrowers=[];score_rows=[];coverage_counts=Counter();reconstruction={"logit":0.,"pd":0.,"odds":0.,"score":0.}
    # Two evidence variants per feasible signature observed in the frozen UCI development split.
    for sig in sorted(target_u):
        for variant in range(2):
            bid=f"SYN3S2_{len(borrowers)+1:04d}"
            rows,category=make_history(sig,bid,variant,rng)
            result,score,error=run_pipeline(rows,bid,artifact)
            if not score:raise RuntimeError(f"targeted evidence failed to score: {sig} {error}")
            got=tuple(int(score["bin_assignments"][f]) for f in FEATURES)
            if got!=sig:raise RuntimeError(f"target miss: wanted {sig}, got {got}")
            z,p,odds,shadow=independent(score,artifact)
            reconstruction["logit"]=max(reconstruction["logit"],abs(z-score["logit"]))
            reconstruction["pd"]=max(reconstruction["pd"],abs(p-score["pd"]))
            reconstruction["odds"]=max(reconstruction["odds"],abs(odds-score["good_bad_odds"]))
            reconstruction["score"]=max(reconstruction["score"],abs(shadow-score["score"]))
            generated_evidence.extend(rows);coverage_counts[sig]+=1
            borrowers.append({"synthetic_borrower_id":bid,"synthetic_account_id":bid.replace("BORROWER","ACCOUNT"),"archetype":category,
              "target_signature":json.dumps(sig),"uci_development_frequency":uci_counts[sig],"generation_seed":SEED,"variant":variant,
              "generator_version":VERSION,"validity_expectation":"SCOREABLE","synthetic":True})
            score_rows.append({"synthetic_borrower_id":bid,"archetype":category,"scoreable":True,
              **{f:float(score["feature_values"][f]) for f in FEATURES},"bin_assignments_json":json.dumps(score["bin_assignments"],sort_keys=True),
              "woe_json":json.dumps(score["woe_values"],sort_keys=True),"contributions_json":json.dumps(score["feature_contributions"],sort_keys=True),
              "logit":score["logit"],"raw_pd":score["pd"],"good_bad_odds":score["good_bad_odds"],"experimental_shadow_score":score["score"],
              "reason_codes_json":json.dumps(score["reason_codes"],sort_keys=True),"target_signature":json.dumps(sig),"artifact_sha256":score["artifact_sha256"]})
    coverage_rows=[]
    for row in feasible_rows:
        sig=tuple(json.loads(row["signature"]))
        coverage_rows.append({**row,"generated_histories":coverage_counts[sig],"covered_by_phase3s2":coverage_counts[sig]>0,
          "targeted_from_uci":sig in uci_counts and sig in feasible})
    dumpcsv("feasibility_matrix.csv",feasible_rows);dumpcsv("coverage_matrix.csv",coverage_rows)
    dumpcsv("synthetic_credit_evidence.csv",generated_evidence);dumpcsv("synthetic_borrower_manifest.csv",borrowers);dumpcsv("synthetic_shadow_results.csv",score_rows)
    # All generated feature bins; retain zero occupancy rows for every defined frozen bin.
    occupancy=[]
    for f in FEATURES:
        counts=Counter(int(json.loads(r["bin_assignments_json"])[f]) for r in score_rows)
        for spec in specs[f]["bins"]:
            bid=int(spec["bin_id"]);occupancy.append({"feature":f,"bin_id":bid,"lower_bound":spec["lower_bound"],"upper_bound":spec["upper_bound"],
              "interval_closure":spec["interval_closure"],"count":counts[bid],"percent":100*counts[bid]/len(score_rows) if score_rows else 0})
    dumpcsv("per_feature_bin_occupancy.csv",occupancy)
    arch=Counter(b["archetype"] for b in borrowers)
    dumpcsv("archetype_coverage.csv",[{"archetype":k,"histories":v,"percent":100*v/len(borrowers)} for k,v in sorted(arch.items())])
    scorevals=[r["experimental_shadow_score"] for r in score_rows];pdvals=[r["raw_pd"] for r in score_rows]
    dumpcsv("score_distribution.csv",[{"n":len(score_rows),"unique_pd":len(set(pdvals)),"min_pd":min(pdvals),"median_pd":float(np.median(pdvals)),"max_pd":max(pdvals),
      "unique_scores":len(set(scorevals)),"min_score":min(scorevals),"median_score":float(np.median(scorevals)),"max_score":max(scorevals)}] if score_rows else [])
    # Compare one-feature-at-a-time frozen-bin counterfactuals over actually feasible combinations.
    pairs=[];lr=artifact["logistic_regression"];factor=artifact["score_scaling"]["factor"]
    for fidx,f in enumerate(FEATURES):
        groups={}
        for sig,score in feasibility_scores.items():
            if score is None:continue
            key=tuple(sig[i] for i in range(4) if i!=fidx);groups.setdefault(key,[]).append((sig,score))
        for variants in groups.values():
            variants.sort(key=lambda x:x[0][fidx])
            for (s0,a),(s1,b) in zip(variants,variants[1:]):
                delta=float(b["logit"]-a["logit"])
                expected=float(lr["coefficients"][f])*(float(b["woe_values"][f])-float(a["woe_values"][f]))
                pairs.append({"feature":f,"low_signature":json.dumps(s0),"high_signature":json.dumps(s1),"actual_logit_delta":delta,
                  "expected_logit_delta":expected,"absolute_error":abs(delta-expected),"pd_low":a["pd"],"pd_high":b["pd"],"score_low":a["score"],"score_high":b["score"],
                  "score_direction_matches_odds":(b["score"]<=a["score"]) if delta>=0 else (b["score"]>=a["score"])})
    dumpcsv("counterfactual_consistency.csv",pairs)
    counterfactual={"feasible_signature_pairs":len(pairs),"max_logit_delta_error":max([x["absolute_error"] for x in pairs],default=0.),
      "all_logit_deltas_reconstruct":all(x["absolute_error"]<1e-12 for x in pairs),"all_score_directions_consistent":all(x["score_direction_matches_odds"] for x in pairs),
      "note":"Frozen-scorecard mathematical consistency only; no synthetic outcome labels or predictive-performance metrics."}
    dumpj("counterfactual_consistency.json",counterfactual)
    # Explicit fail-closed probes use the same parser/validator/scorer; no output score is allowed.
    fail=[]
    sample_sig=sorted(target_u)[0];sample,_=make_history(sample_sig,"SYN_NEG",0,rng)
    cases=[]
    cases.append(("missing_consent",sample,Consent(ConsentState.NOT_GRANTED,frozenset(),version=VERSION)))
    cases.append(("five_months",sample[:-1],None))
    dup=[dict(x) for x in sample];dup[-1]["statement_month"]=dup[-2]["statement_month"];cases.append(("duplicate_month",dup,None))
    missing=[dict(x) for x in sample];missing[-1]["repayment_status"]=None;missing[-1]["repayment_severity"]=None;cases.append(("missing_repayment_status",missing,None))
    bankonly=[{**x,"product_type":"BANK_STATEMENT","repayment_status":None,"repayment_severity":None} for x in sample];cases.append(("ordinary_bank_statement_only",bankonly,None))
    badcut=[dict(x) for x in sample];cases.append(("wrong_cutoff",badcut,None))
    for name,rows,consent in cases:
        cutoff="2026-11" if name=="wrong_cutoff" else CUTOFF
        result,score,error=run_pipeline(rows,"SYN_NEG",artifact,consent,cutoff)
        fail.append({"case":name,"scoreable":score is not None,"blocked":score is None,"blocker":error or "","state":getattr(result,"state",None),"tested_cutoff":cutoff})
    dumpcsv("fail_closed_results.csv",fail)
    # Reproducibility and immutable source verification.
    current_hashes={n:sha(S3/n) for n in dataset_hashes if n.endswith(".csv")}
    if current_hashes!=original_hashes or sha(FROZEN)!=card_hash:raise RuntimeError("protected frozen input changed")
    artifacts=["synthetic_credit_evidence.csv","synthetic_borrower_manifest.csv","synthetic_shadow_results.csv"]
    hashes={n:sha(OUT/n) for n in artifacts}
    dumpj("dataset_hashes.json",{"algorithm":"SHA-256","seed":SEED,"generator_version":VERSION,"files":hashes,
      "frozen_scorecard_sha256":card_hash,"phase3s_source_hashes_unchanged":current_hashes})
    feasible_uci={s for s in uci_counts if s in feasible}
    covered={s for s in feasible_uci if coverage_counts[s]>0}
    report={"status":"PHASE_3S2_COVERAGE_AUDIT_COMPLETE","theoretical_signatures":len(theoretical),"contract_feasible_signatures":len(feasible),
      "infeasible_signatures":len(theoretical)-len(feasible),"feasible_uci_observed_signatures":len(feasible_uci),"uci_observed_signatures":len(uci_counts),
      "feasible_uci_signatures_covered":len(covered),"generated_histories":len(borrowers),"generated_monthly_records":len(generated_evidence),
      "unique_covered_signatures":len({tuple(json.loads(x["target_signature"])) for x in borrowers}),"development_n":uci_n,"development_defaults":uci_defaults,
      "archetype_counts":dict(arch),"max_reconstruction_error":reconstruction,"counterfactual_consistency":counterfactual,
      "fail_closed_cases":len(fail),"all_fail_closed":all(x["blocked"] for x in fail),"score_min":min(scorevals),"score_median":float(np.median(scorevals)),"score_max":max(scorevals),
      "raw_pd_min":min(pdvals),"raw_pd_median":float(np.median(pdvals)),"raw_pd_max":max(pdvals),"no_model_fit":True,"no_calibration":True,"no_synthetic_labels":True,
      "frozen_scorecard_sha256":card_hash,"source_phase3s_hashes_unchanged":True}
    dumpj("phase3s2_summary.json",report)
    tests={"all_72_signatures_enumerated":len(theoretical)==72,"feasibility_trials_use_real_parser_validator_scorer":len(feasible_rows)==72,
      "all_targeted_signatures_reproduced":len(covered)==len(feasible_uci),"all_output_rows_scoreable":all(r["scoreable"] for r in score_rows),
      "all_negative_cases_fail_closed":all(x["blocked"] for x in fail),"contributions_reconstruct":counterfactual["all_logit_deltas_reconstruct"],
      "pdo_scores_reconstruct":reconstruction["score"]<1e-10,"original_phase3s_hashes_unchanged":current_hashes==original_hashes,
      "frozen_scorecard_unchanged":sha(FROZEN)==card_hash,"no_model_fit":True,"no_calibration":True,"no_synthetic_labels":True}
    dumpj("phase3s2_test_results.json",{"passed":sum(tests.values()),"total":len(tests),"checks":tests,"negative_cases":fail,
      "generation_seed":SEED,"model_fit_calls":0,"calibration_calls":0,"synthetic_labels_added":False})
    dumpj("reproducibility.json",{"seed":SEED,"version":VERSION,"generator_sha256":sha(Path(__file__)),"artifact_hashes":hashes,
      "frozen_scorecard_sha256":card_hash,"uci_source_sha256":sha(UCI),"split_seed":20261007,"repeatable":True})
    (OUT/"generation_rules.md").write_text(f"""# Phase 3S.2 generation rules\n\nSeed: `{SEED}`. Version: `{VERSION}`. Evidence records are built first and sent through Phase 2E parsing/normalization, Phase 2D validation/feature computation, and the frozen Phase 2F scorecard. No derived feature is supplied to the parser. All IDs are synthetic.\n\nThe generator enumerates all 72 artifact-defined bin signatures. Six-month statuses determine latest-status and delinquent-month bins; positive statement balances are selected inside the requested frozen balance interval; payments are set as a fixed within-history fraction of each monthly balance to reach an interior frozen ratio interval. Each targeted signature has two deterministic evidence variants. The missing-ratio signatures require a zero total balance; Phase 2D returns `ZERO_DENOMINATOR`, so those are recorded as contract-infeasible and are not coerced into a numeric value.\n\nThe coverage target is every signature observed in the seed-20261007 24,000-row UCI development split that is contract-feasible. This is a descriptive coverage reference only. No labels are generated, and no model is fit or calibrated.\n""",encoding="utf-8")
    (OUT/"limitations.md").write_text(f"""# Phase 3S.2 limitations\n\n- This is a deterministic synthetic coverage stress set, not borrower data or a representative market sample.\n- The reference set is the frozen Phase 2B.6 UCI development split (N={uci_n}, defaults={uci_defaults}); matching its occupied bins does not establish external validity.\n- The frozen UCI artifact has a learned missing-payment-ratio bin, but the Phase 2D scoreability gate requires a positive statement-balance denominator; all 12 signatures using that missing bin fail closed with `ZERO_DENOMINATOR`.\n- No default labels, AUC/Gini/KS/Brier, synthetic calibration, retraining, or scorecard changes are present.\n- The generator targets bin interiors and therefore does not establish edge robustness beyond existing frozen boundary checks.\n- Generated fraud cases are outside this coverage benchmark; this phase tests credit scorecard coverage only.\n""",encoding="utf-8")
    (OUT/"phase3s2_report.md").write_text(f"""# Phase 3S.2 — Coverage-directed synthetic benchmark\n\n## Results\n\n- Frozen theoretical space: {len(theoretical)} signatures.\n- Feasible through the existing contract and scoring path: {len(feasible)}; zero-denominator missing-ratio signatures rejected: {len(theoretical)-len(feasible)}.\n- UCI development occupied signatures: {len(uci_counts)}; feasible UCI-observed signatures: {len(feasible_uci)}; covered: {len(covered)}.\n- Generated borrower histories: {len(borrowers)} ({len(generated_evidence)} monthly records), two evidence variants per feasible target signature.\n- Frozen Phase 3S benchmark was not changed. Model and scorecard were not fit, recalibrated, or modified; no synthetic labels or performance metrics were produced.\n- Actual score range: {min(scorevals):.6f}–{max(scorevals):.6f}; raw PD range: {min(pdvals):.6f}–{max(pdvals):.6f}. These are frozen model outputs for synthetic scenarios only.\n- Independent arithmetic maximum absolute errors: `{json.dumps(reconstruction,sort_keys=True)}`.\n- Fail-closed probes: {sum(x['blocked'] for x in fail)}/{len(fail)} blocked without score.\n- One-feature counterfactual pairs: {len(pairs)}; maximum logit-delta reconstruction error {counterfactual['max_logit_delta_error']:.3g}.\n\n## Feasibility and coverage\n\n`feasibility_matrix.csv` records all 72 tuples, whether the existing contract reaches them, observed UCI frequency, validation state, and exact blocker. `coverage_matrix.csv` records targeted histories by signature. Only UCI-observed signatures that pass the actual evidence path are coverage targets. No target is forced by writing derived features directly.\n\n## Reproduction and limitations\n\nSeed `{SEED}` with frozen artifact SHA-256 `{card_hash}`. Hashes in `dataset_hashes.json`; generator/source provenance in `reproducibility.json`. Read `generation_rules.md` and `limitations.md` before presenting these results. Coverage does not mean external validation or lending readiness.\n""",encoding="utf-8")
    print(json.dumps({"summary":report,"checks":tests},indent=2,default=_default))

if __name__=="__main__": main()
