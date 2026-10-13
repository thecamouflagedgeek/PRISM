import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phase2.windowing import complete_calendar_window
from phase2.phase2b import sha256, stratified_indices
from phase2.semisynthetic.data import AUDIT, real_3m_parents
from phase2.semisynthetic.feature_extraction import FEATURES, extract_behavioral_features
from phase2.semisynthetic.generator import (
    fit_generator, training_feature_geometry, make_descendant, make_duplicate,
    _history_signature, _ledger_rebuild,
)
from phase2.semisynthetic.modeling import family_weights, fit_woe, transform, scorecard_fit, evaluate

BACKEND = Path(__file__).resolve().parents[2]


def fake_parent(pid=10, target=0):
    start=pd.Timestamp("1993-01-01"); end=pd.Timestamp("1993-04-01"); loan=pd.Timestamp("1993-04-17")
    tx=pd.DataFrame({
        "trans_id":[pid*10+i for i in range(4)],"account_id":[pid]*4,
        "source_order":range(4),"date":pd.to_datetime(["1993-01-04","1993-01-20","1993-02-10","1993-03-15"]),
        "amount":[100.,200.,30.,120.],"type":["PRIJEM","PRIJEM","VYDAJ","PRIJEM"],
        "k_symbol":["","","SIPO",""],"balance":[600.,800.,770.,890.],
    })
    return {"parent_loan_id":pid,"parent_account_id":pid,"status":"A" if target==0 else "B","target":target,"label_source":"OBSERVED_BERKA","is_synthetic":False,"loan_date":loan,"window_start":start,"window_end_exclusive":end,"transactions":tx,"features":extract_behavioral_features(tx,loan,start,end,3)}


@pytest.fixture(scope="module")
def real_parents():
    return real_3m_parents()


def test_corrected_3m_real_cohort_independently_verified(real_parents):
    parents,summary=real_parents
    assert (len(parents),summary["real_parent_defaults"],summary["real_parent_nondefaults"])==(231,31,200)
    assert summary["raw_membership_matches_corrected_phase2a"]
    assert summary["feature_extractor_parity_all_features"]


def test_real_training_history_can_produce_a_reconciled_local_descendant(real_parents):
    parents,_=real_parents
    training=parents[:180]
    params=fit_generator(training,313)
    geometry=training_feature_geometry(training)
    failures=[]
    for parent in training[:30]:
        try:
            child=make_descendant(parent,params,geometry,"E1",.5,901+parent["parent_loan_id"],"real_smoke",params["q90_abs_log_residual"],None)
            assert child["ledger_error"]<=1e-6
            return
        except ValueError as exc:
            failures.append(str(exc))
    pytest.fail(f"No local real-parent descendant passed ledger/plausibility checks: {failures[:4]}")


def test_raw_cohort_excludes_c_and_d(real_parents):
    parents,_=real_parents
    assert all(p["status"] in {"A","B"} and p["target"] in {0,1} for p in parents)


def test_complete_calendar_window_boundaries():
    w=complete_calendar_window(pd.Timestamp("1993-04-17").date(),3,account_open_date=pd.Timestamp("1993-01-01").date(),source_coverage_start=pd.Timestamp("1992-01-01").date(),source_coverage_end_exclusive=pd.Timestamp("1994-01-01").date())
    assert str(w.window_start)=="1993-01-01" and str(w.window_end_exclusive)=="1993-04-01" and w.eligible


def test_first_origination_month_and_loan_date_txn_are_rejected():
    p=fake_parent(); bad=p["transactions"].copy(); bad.loc[0,"date"]=pd.Timestamp("1993-04-01")
    with pytest.raises(ValueError,match="outside complete pre-origination"):
        extract_behavioral_features(bad,p["loan_date"],p["window_start"],p["window_end_exclusive"],3)
    bad=p["transactions"].copy(); bad.loc[0,"date"]=p["loan_date"]
    with pytest.raises(ValueError,match="outside complete pre-origination"):
        extract_behavioral_features(bad,p["loan_date"],p["window_start"],p["window_end_exclusive"],3)


def test_split_before_augmentation_and_parent_partition_is_disjoint():
    y=np.array([0]*40+[1]*8); train,val=stratified_indices(y,.25,91)
    assert not set(train)&set(val) and set(train)|set(val)==set(range(len(y)))


def test_generator_fit_uses_only_passed_training_parents():
    p=fake_parent(10); q=fake_parent(11,1); held=fake_parent(12,1)
    a=fit_generator([p,q],3); b=fit_generator([p,q],3)
    assert set(a["fit_parent_ids"])=={10,11}
    assert a["fit_parent_ids_sha256"]==b["fit_parent_ids_sha256"]
    assert a["q95_abs_log_residual"]==b["q95_abs_log_residual"]
    assert held["parent_loan_id"] not in a["fit_parent_ids"]


def test_deterministic_local_generation_and_lineage():
    p=fake_parent(); params=fit_generator([p],4); geometry=training_feature_geometry([p])
    a=make_descendant(p,params,geometry,"E1",.5,123,"a",100,None)
    b=make_descendant(p,params,geometry,"E1",.5,123,"a",100,None)
    assert a["synthetic_signature"]==b["synthetic_signature"]
    assert a["parent_loan_id"]==p["parent_loan_id"] and a["label_source"]=="PARENT_INHERITED"
    assert a["target"]==p["target"] and a["is_synthetic"]


def test_transaction_direction_and_category_are_preserved():
    p=fake_parent(); d=make_descendant(p,fit_generator([p],1),training_feature_geometry([p]),"E1",.5,55,"syn",100,None)
    assert d["transactions"].type.tolist()==p["transactions"].type.tolist()
    assert d["transactions"].k_symbol.fillna("").tolist()==p["transactions"].k_symbol.fillna("").tolist()


def test_transaction_dates_remain_within_window_and_preloan():
    p=fake_parent(); d=make_descendant(p,fit_generator([p],1),training_feature_geometry([p]),"E2",1,66,"syn",100,None)
    t=d["transactions"].date
    assert (t>=p["window_start"]).all() and (t<p["window_end_exclusive"]).all() and (t<p["loan_date"]).all()


def test_category_and_status_leakage_fields_are_not_predictors():
    assert not set(FEATURES)&{"loan_amount","duration","payments","target","status","loan_id","parent_loan_id","documented_loan_payment_total"}


def test_transaction_amounts_nonnegative_and_finite():
    p=fake_parent(); d=make_descendant(p,fit_generator([p],1),training_feature_geometry([p]),"E1",.5,77,"syn",100,None)
    assert np.isfinite(d["transactions"].amount).all() and (d["transactions"].amount>=0).all()


def test_ledger_rebuild_reconciles_after_amount_perturbation():
    p=fake_parent(); d=make_descendant(p,fit_generator([p],1),training_feature_geometry([p]),"E2",1,78,"syn",100,None)
    _,error=_ledger_rebuild(d["transactions"])
    assert error<=1e-6 and d["ledger_error"]<=1e-6


def test_feature_extractor_accepts_descendants_and_has_frozen_schema():
    p=fake_parent(); d=make_descendant(p,fit_generator([p],1),training_feature_geometry([p]),"E1",.5,79,"syn",100,None)
    assert set(d["features"])==set(FEATURES) and all(np.isfinite(v) or pd.isna(v) for v in d["features"].values())


def test_valid_zero_and_zero_denominator_semantics():
    p=fake_parent(); tx=p["transactions"].copy(); tx.loc[tx.type=="VYDAJ","amount"]=0.; tx.loc[tx.type=="VYDAJ","balance"]=800.
    f=extract_behavioral_features(tx,p["loan_date"],p["window_start"],p["window_end_exclusive"],3)
    assert pd.isna(f["credit_debit_ratio"])
    assert f["avg_monthly_debit"]==0


def test_exact_duplicate_control_is_explicitly_identified():
    p=fake_parent(); d=make_duplicate(p,"E_DUPLICATE_CONTROL",1,"dup")
    assert _history_signature(d["transactions"])==_history_signature(p["transactions"])
    assert d["feature_distance"]==0 and d["augmentation_condition"]=="E_DUPLICATE_CONTROL"


def test_parent_aware_family_weights_sum_to_one():
    rows=[{"parent_loan_id":1},{"parent_loan_id":1},{"parent_loan_id":1},{"parent_loan_id":2}]
    w=family_weights(rows)
    assert sum(w[:3])==pytest.approx(1) and w[3]==pytest.approx(1)
    assert np.all(family_weights(rows,naive=True)==1)


def test_parent_normalized_noop_duplication_is_invariant_to_real_only_fit():
    rng=np.random.default_rng(40); train=[]
    for i in range(40):
        y=int(i%4==0)
        feats={f:float(rng.normal()+.15*y) for f in FEATURES}
        train.append({"parent_loan_id":i,"target":y,"features":feats,"is_synthetic":False})
    duplicate=train+[dict(r,is_synthetic=True) for r in train for _ in range(3)]
    m0=scorecard_fit(train,family_weights(train))
    md=scorecard_fit(duplicate,family_weights(duplicate))
    assert m0["selected"]==md["selected"]
    assert np.allclose(m0["beta"],md["beta"],atol=1e-12)


def test_training_only_binning_and_woe_ignore_validation_values():
    train=[{"parent_loan_id":i,"target":int(i>5),"features":{"min_balance":float(i)}} for i in range(10)]
    weights=np.ones(10); selected,binners,ivs,X,y=fit_woe(train,weights)
    cut=binners["min_balance"]["cut"]
    validation=[{"parent_loan_id":999,"target":1,"features":{"min_balance":1e12}}]
    assert binners["min_balance"]["cut"]==cut
    assert transform(validation,selected,binners).shape==(1,len(selected))


def test_label_source_distinguishes_observed_and_inherited():
    p=fake_parent(target=1); d=make_descendant(p,fit_generator([p],2),training_feature_geometry([p]),"E1",.5,80,"syn",100,None)
    assert p["label_source"]=="OBSERVED_BERKA" and d["label_source"]=="PARENT_INHERITED"
    assert d["target"]==p["target"]


def test_real_only_validation_holdout_and_same_split_registry_contract():
    p=fake_parent(1); q=fake_parent(2,1); h=fake_parent(3,1)
    train,val,hold={1},{2},{3}
    assert not train&val and not train&hold and not val&hold
    assert q["parent_loan_id"] not in train and h["parent_loan_id"] not in train


def test_no_superseded_rolling_window_input_is_referenced():
    source=(BACKEND/"phase2"/"semisynthetic"/"data.py").read_text(encoding="utf-8").lower()
    assert "superseded_rolling_window" not in source
    assert "complete_calendar_window" in source


def test_duplicate_control_and_e0_share_training_parents():
    p=fake_parent(); copies=[make_duplicate(p,"E_DUPLICATE_CONTROL",i,f"d{i}") for i in range(3)]
    assert {d["parent_loan_id"] for d in copies}=={p["parent_loan_id"]}


def test_no_loan_repayment_information_in_canonical_feature_set():
    assert not {"documented_loan_payment_total","loan_payment","postloan_UVER_payment_count"}.intersection(FEATURES)


def test_augmentation_fit_records_train_parent_ids_and_reproducible_seed():
    p=fake_parent(1); q=fake_parent(2,1); params=fit_generator([p,q],71)
    assert params["fit_parent_count"]==2 and params["split_seed"]==71
    assert params["group_pool_sizes"]


def test_feature_distance_and_history_distance_are_recorded():
    p=fake_parent(); d=make_descendant(p,fit_generator([p],1),training_feature_geometry([p]),"E1",.5,81,"syn",100,None)
    assert np.isfinite(d["feature_distance"]) and np.isfinite(d["history_distance"])
    assert d["max_abs_log_amount_change"]>=d["mean_abs_log_amount_change"]


def test_perturbation_distance_limit_rejects_out_of_bound_child():
    p=fake_parent(); params=fit_generator([p],1); geom=training_feature_geometry([p])
    with pytest.raises(ValueError,match="HISTORY_DISTANCE_EXCEEDED"):
        make_descendant(p,params,geom,"E2",1,82,"syn",0,None)


def test_phase2b5s_inputs_are_corrected_candidate_outputs_only():
    assert (AUDIT/"candidate_features_by_loan.csv").exists()
    assert (AUDIT/"window_reconciliation.csv").exists()
    assert not (AUDIT/"superseded_rolling_window"/"candidate_features_by_loan.csv").resolve()==(AUDIT/"candidate_features_by_loan.csv").resolve()


def test_production_artifact_hashes_and_manifest_status_unchanged():
    d=BACKEND/"scoring"/"artifacts"; m=json.loads((d/"manifest.json").read_text(encoding="utf-8"))
    assert m["model_validation_status"]=="UNVERIFIED_REAL_WORLD" and m["phase_1_runtime_status"]=="VERIFIED"
    assert sha256(d/"lr_model.pkl")==m["artifacts"]["lr_model.pkl"]
    assert sha256(d/"binning.pkl")==m["artifacts"]["binning.pkl"]
    assert sha256(d/"manifest.json")=="b7acf498dc2523cb11fffefe2b12e5ee58e55bcab54c231b39768dd671e11148"
