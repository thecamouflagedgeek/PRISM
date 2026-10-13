"""Package actual synthetic evidence requests and Phase 2G API responses for the demo."""
from __future__ import annotations
import json, os, sys
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/"backend"
OUT=BACKEND/"phase4/outputs"
S3=BACKEND/"phase3/outputs/phase3s"
sys.path.insert(0,str(BACKEND))
os.environ["ENABLE_EXPERIMENTAL_SHADOW_SCORING"]="true"
from phase2.shadow_api.routes import ShadowAssessmentRequest,_build_response

def json_default(value):
    if is_dataclass(value): return asdict(value)
    if isinstance(value,Enum): return value.value
    if isinstance(value,Decimal): return str(value)
    if hasattr(value,"model_dump"): return value.model_dump(mode="json")
    if hasattr(value,"__dict__"): return value.__dict__
    raise TypeError(type(value).__name__)

def main():
    evidence=pd.read_csv(S3/"synthetic_credit_evidence.csv")
    results=pd.read_csv(S3/"synthetic_shadow_results.csv")
    data=pd.read_csv(BACKEND/"phase3/outputs/phase3s2/synthetic_shadow_results.csv")
    scenarios=[]; used=set()
    def add(sid,label,borrower,group,kind="SCOREABLE",alter=None):
        if borrower in used:return
        used.add(borrower)
        rows=evidence[evidence.synthetic_borrower_id.eq(borrower)].sort_values("statement_month")
        statements=[];repayments=[]
        for r in rows.to_dict(orient="records"):
            month=r["statement_month"];sev=int(r["repayment_severity"]);status="DELINQUENT" if sev>0 else "CURRENT"
            if alter and alter["month"]==month: status,sev=alter["statement_status"],alter["statement_severity"]
            src=r["synthetic_source_id"]
            meta={"source_document_id":src,"extraction_method":"phase3s-synthetic-structured-evidence","extraction_confidence":1.0,"account_link_confidence":1.0,"authenticated":True}
            statements.append({"account_reference":r["synthetic_account_id"],"product_type":"CREDIT_CARD","provider":r["provider"],
              "masked_account_number":r["masked_account_number"],"currency":r["currency"],"statement_month":month,
              "statement_balance":str(r["statement_balance"]),"payment_amount":str(r["payment_amount"]),
              "repayment_status":{"status":status,"delinquency_severity":sev,"source_code":f"synthetic:{sev}"},"source_metadata":meta})
            repay_meta={**meta,"source_document_id":f"BUREAU_{src}"}
            repayments.append({"account_reference":r["synthetic_account_id"],"product_type":"CREDIT_CARD","provider":r["provider"],
              "month":month,"repayment_status":"DELINQUENT" if int(r["repayment_severity"])>0 else "CURRENT",
              "delinquency_severity":int(r["repayment_severity"]),"source_code":f"synthetic:{int(r['repayment_severity'])}","source_metadata":repay_meta})
        req={"borrower_reference":borrower,"prediction_cutoff_month":"2026-10","statements":statements,
             "repayment_history":repayments,"consent":{"state":"GRANTED","scopes":["CREDIT_CARD_STATEMENTS","BUREAU_REPAYMENT_HISTORY"],"granted_at":"2026-01-01T00:00:00Z"},"borrower_account_count":1}
        upload={"evidence_type":"CREDIT_ACCOUNT_REPAYMENT","borrower_reference":borrower,"prediction_cutoff_month":"2026-10",
                "statements":statements,"repayment_history":repayments,"borrower_account_count":1}
        response=_build_response(ShadowAssessmentRequest.model_validate(req),debug=True)
        scenarios.append({"id":sid,"label":label,"scenario_family":group,"expected_behavior":kind,"synthetic":True,
                          "source_borrower_id":borrower,"evidence_upload":upload,"request":req,"actual_api_output":response})
    # Choose actual frozen score outputs, not hand-assigned scores or PDs.
    lo=data.loc[data.raw_pd.idxmin()]; mid=data.loc[(data.raw_pd-data.raw_pd.median()).abs().idxmin()]; hi=data.loc[data.raw_pd.idxmax()]
    phase32=pd.read_csv(BACKEND/"phase3/outputs/phase3s2/synthetic_credit_evidence.csv")
    def add_s2(sid,label,row):
        bid=row.synthetic_borrower_id; rec=phase32[phase32.synthetic_borrower_id.eq(bid)].sort_values("statement_month")
        # Convert the Phase 3S.2 history via the same source mapping and then call the actual experimental API logic.
        statements=[];repayments=[]
        for r in rec.to_dict(orient="records"):
            sev=int(r["repayment_severity"]);src=r["synthetic_source_id"];meta={"source_document_id":src,"extraction_method":"phase3s2-synthetic-structured-evidence","extraction_confidence":1.0,"account_link_confidence":1.0,"authenticated":True}
            statements.append({"account_reference":r["synthetic_account_id"],"product_type":"CREDIT_CARD","provider":r["provider"],"masked_account_number":r["masked_account_number"],"currency":r["currency"],"statement_month":r["statement_month"],"statement_balance":str(r["statement_balance"]),"payment_amount":str(r["payment_amount"]),"repayment_status":{"status":"DELINQUENT" if sev else "CURRENT","delinquency_severity":sev,"source_code":f"synthetic:{sev}"},"source_metadata":meta})
            repay_meta={**meta,"source_document_id":f"BUREAU_{src}"}
            repayments.append({"account_reference":r["synthetic_account_id"],"product_type":"CREDIT_CARD","provider":r["provider"],"month":r["statement_month"],"repayment_status":"DELINQUENT" if sev else "CURRENT","delinquency_severity":sev,"source_code":f"synthetic:{sev}","source_metadata":repay_meta})
        req={"borrower_reference":bid,"prediction_cutoff_month":"2026-10","statements":statements,"repayment_history":repayments,"consent":{"state":"GRANTED","scopes":["CREDIT_CARD_STATEMENTS","BUREAU_REPAYMENT_HISTORY"],"granted_at":"2026-01-01T00:00:00Z"},"borrower_account_count":1}
        response=_build_response(ShadowAssessmentRequest.model_validate(req),debug=True)
        scenarios.append({"id":sid,"label":label,"scenario_family":"phase3s2_coverage_extreme","expected_behavior":"SCOREABLE","synthetic":True,"source_borrower_id":bid,"evidence_upload":{"evidence_type":"CREDIT_ACCOUNT_REPAYMENT","borrower_reference":bid,"prediction_cutoff_month":"2026-10","statements":statements,"repayment_history":repayments,"borrower_account_count":1},"request":req,"actual_api_output":response})
    add_s2("lowest_model_pd","Lowest model PD in the coverage pack",lo)
    add_s2("middle_model_pd","Median-nearest model PD in the coverage pack",mid)
    add_s2("highest_model_pd","Highest model PD in the coverage pack",hi)
    named=[("healthy_repayment","Healthy full-payer history","stable_full_payer"),("recent_severe","Recent severe delinquency","recent_shock"),
      ("persistent_delinquency","Persistent delinquency","persistent_delinquency"),("improving","Improving repayment","improving_borrower"),
      ("recovering","Recovering repayment","recovered_borrower"),("high_balance_good_payment","High balance with strong payment","high_balance_good_repayment"),
      ("low_balance_poor_payment","Low balance with poor payment","low_balance_poor_repayment"),
      ("conflicting_high_ratio","High payment ratio with delinquency conflict","high_ratio_delinquency_conflict"),
      ("conflicting_low_ratio","Low payment ratio with current status","low_ratio_current_conflict")]
    for sid,label,arch in named:
        group=results[results.archetype.eq(arch)].sort_values("synthetic_borrower_id")
        add(sid,label,group.iloc[0].synthetic_borrower_id,arch)
    # Consent, bank-only and evidence-conflict negative calls are recorded from the real API function.
    good=scenarios[next(i for i,x in enumerate(scenarios) if x["id"]=="healthy_repayment")]["request"]
    for sid,label,mutator in [
      ("invalid_consent","Invalid consent blocks scoring",lambda x:x.update(consent={"state":"NOT_GRANTED","scopes":[],"granted_at":None})),
      ("insufficient_evidence","Bank statement only blocks credit scoring",lambda x:(x.update(statements=[],repayment_history=[]))),
      ("evidence_conflict","Conflicting account repayment evidence blocks scoring",lambda x:(x["statements"][0]["repayment_status"].update(status="CURRENT",delinquency_severity=0),x["repayment_history"][0].update(repayment_status="DELINQUENT",delinquency_severity=1)))]:
        req=json.loads(json.dumps(good));req["borrower_reference"]="SYN_NEG_"+sid;mutator(req)
        response=_build_response(ShadowAssessmentRequest.model_validate(req),debug=True)
        scenarios.append({"id":sid,"label":label,"scenario_family":"negative_evidence","expected_behavior":"BLOCKED_NO_SCORE","synthetic":True,"source_borrower_id":req["borrower_reference"],"request":req,"actual_api_output":response})
    OUT.mkdir(parents=True,exist_ok=True)
    result={"source":"Phase 3S and Phase 3S.2 synthetic evidence, scored by the Phase 2G experimental API response builder","frozen_model_sha256":json.loads((S3/"generator_manifest.json").read_text())["phase2f_frozen_spec_sha256"],"scenarios":scenarios}
    (OUT/"demo_scenarios.json").write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False,default=json_default)+"\n",encoding="utf-8")
    print(json.dumps({"scenario_count":len(scenarios),"scoreable":sum(x["actual_api_output"].get("eligibility",{}).get("eligible",False) for x in scenarios),"blocked":sum(not x["actual_api_output"].get("eligibility",{}).get("eligible",False) for x in scenarios)},indent=2))
if __name__=="__main__":main()
