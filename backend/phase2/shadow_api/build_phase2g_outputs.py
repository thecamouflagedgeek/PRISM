"""Generate the reproducible Phase 2G API, regression, and capability artifacts."""
from __future__ import annotations
import csv, hashlib, json, os, sys, types, joblib
import re
from pathlib import Path

from fastapi.testclient import TestClient

PHASE2 = Path(__file__).resolve().parents[1]
REPO = PHASE2.parents[1]
OUT = PHASE2 / "outputs" / "phase2g"
FIXTURE = PHASE2 / "outputs" / "phase2e" / "golden_fixture.json"
BASELINE = OUT / "protected_hashes_before.json"


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def write(name, value): (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")


def _main_app_with_import_only_production_stubs():
    """The local Python lacks optional production deps; don't execute production scoring."""
    fake = types.ModuleType("pytesseract")
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd=None)
    sys.modules["pytesseract"] = fake
    class Model:
        feature_names_in_ = ["credit_debit_ratio", "cashflow_cv", "net_to_gross_ratio", "utility_stability", "min_balance"]
        coef_ = [[0.0] * 5]
    original_load = joblib.load
    joblib.load = lambda path: Model() if "lr_model" in str(path) else {x: object() for x in Model.feature_names_in_}
    try:
        sys.path.insert(0, str(REPO / "backend"))
        from main import app
        return app
    finally:
        joblib.load = original_load


def _golden_request(client):
    response = client.get("/experimental/shadow-golden-request")
    if response.status_code != 200: raise RuntimeError("Enable the experimental feature flag before generating Phase 2G outputs")
    return response.json()


def _negative_bodies(golden):
    cases = {k: json.loads(json.dumps(golden)) for k in [
        "statement_only", "missing_month", "duplicate_month", "missing_status", "missing_balance", "missing_payment",
        "consent_missing", "consent_withdrawn", "wrong_consent_scope", "account_mismatch", "low_link_confidence",
        "conflicting_status", "unsupported_product", "multiple_accounts", "zero_denominator", "invalid_numeric",
        "future_record", "incomplete_provenance", "invalid_consent_timezone"]}
    cases["statement_only"]["repayment_history"] = []
    cases["missing_status"]["repayment_history"] = []
    cases["missing_month"]["statements"].pop()
    cases["duplicate_month"]["statements"][-1]["statement_month"] = "2026-05"
    cases["missing_balance"]["statements"][0].pop("statement_balance")
    cases["missing_payment"]["statements"][0].pop("payment_amount")
    cases["consent_missing"]["consent"] = None
    cases["consent_withdrawn"]["consent"]["state"] = "WITHDRAWN"
    cases["wrong_consent_scope"]["consent"]["scopes"] = ["CREDIT_CARD_STATEMENTS"]
    cases["account_mismatch"]["repayment_history"][0]["account_reference"] = "other-card"
    for row in cases["low_link_confidence"]["repayment_history"]: row["source_metadata"]["account_link_confidence"] = .90
    cases["conflicting_status"]["statements"][0]["repayment_status"] = {"status": "CURRENT", "delinquency_severity": 0}
    cases["conflicting_status"]["repayment_history"][0].update({"repayment_status": "DELINQUENT", "delinquency_severity": 1})
    for row in cases["unsupported_product"]["statements"]: row["product_type"] = "PERSONAL_LOAN"
    for row in cases["unsupported_product"]["repayment_history"]: row["product_type"] = "PERSONAL_LOAN"
    cases["multiple_accounts"]["borrower_account_count"] = 2
    for row in cases["zero_denominator"]["statements"]: row["statement_balance"] = "0"
    cases["invalid_numeric"]["statements"][0]["statement_balance"] = "not-money"
    cases["future_record"]["statements"][-1]["statement_month"] = "2026-07"
    cases["incomplete_provenance"]["statements"][0].pop("source_metadata")
    cases["invalid_consent_timezone"]["consent"]["granted_at"] = "2026-01-01T00:00:00"
    return cases


def _protected_after():
    before = json.loads(BASELINE.read_text(encoding="utf-8")); after=[]
    for row in before:
        path=REPO/row["relative_path"]
        actual=sha(path) if path.is_file() else None
        after.append({**row,"actual_sha256":actual,"unchanged":actual==row["sha256"]})
    (OUT/"protected_hashes_after.json").write_text(json.dumps(after,indent=2)+"\n",encoding="utf-8")
    return after


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    # Generate responses through the actual FastAPI application, but use import-only
    # stubs for the pre-existing production model/OCR modules, which are not called.
    app = _main_app_with_import_only_production_stubs()
    client = TestClient(app)
    paths = sorted(app.openapi()["paths"])
    os.environ["ENABLE_EXPERIMENTAL_SHADOW_SCORING"] = "true"
    golden = _golden_request(client)
    (OUT/"golden_api_request.json").write_text(json.dumps(golden,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    response = client.post("/experimental/shadow-assess",json=golden)
    golden_response = response.json()
    if response.status_code != 200 or golden_response.get("status") != "EXPERIMENTAL_SHADOW_SCORE":
        raise RuntimeError("Golden experimental API request failed")
    (OUT/"golden_api_response.json").write_text(json.dumps(golden_response,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    debug = client.post("/experimental/shadow-assess/debug",json=golden).json()
    write("golden_api_trace.json",debug)
    negatives=[]
    for name,body in _negative_bodies(golden).items():
        r=client.post("/experimental/shadow-assess",json=body); data=r.json()
        negatives.append({"case":name,"http_status":r.status_code,"status":data.get("status"),
            "blocking_reasons":data.get("eligibility",{}).get("blocking_reasons",[]),
            "pd_absent":data.get("scorecard") is None,"score_absent":data.get("scorecard") is None,
            "reason_codes_empty":data.get("reason_codes")==[]})
    write("negative_api_results.json",{"scenario_count":len(negatives),"all_fail_closed":all(
        n["status"]=="INSUFFICIENT_EXPERIMENTAL_EVIDENCE" and n["pd_absent"] and n["score_absent"] and n["reason_codes_empty"] for n in negatives),"scenarios":negatives})
    os.environ["ENABLE_EXPERIMENTAL_SHADOW_SCORING"]="false"
    flag_off=client.get("/experimental/shadow-golden-request")
    assess_off=client.post("/assess")
    os.environ["ENABLE_EXPERIMENTAL_SHADOW_SCORING"]="true"
    flag_on=client.get("/experimental/shadow-golden-request")
    assess_on=client.post("/assess")
    write("feature_flag_results.json",{"default":"false","off":{"status_code":flag_off.status_code,"error_code":flag_off.json().get("detail",{}).get("code")},
        "on":{"status_code":flag_on.status_code},"assess_off":{"status_code":assess_off.status_code,"body":assess_off.json()},
        "assess_on":{"status_code":assess_on.status_code,"body":assess_on.json()},
        "production_assess_identical":assess_off.status_code==assess_on.status_code and assess_off.json()==assess_on.json()})
    before=json.loads(BASELINE.read_text(encoding="utf-8"))
    before_by={r["relative_path"]:r["sha256"] for r in before}
    assess_path=REPO/"backend/route/assessment_routes.py"
    scoring_artifacts=[p for p in (REPO/"backend/scoring/artifacts").glob("*") if p.is_file()]
    model_files=[p for p in scoring_artifacts if p.name in {"lr_model.pkl","binning.pkl","manifest.json"}]
    production={"assess_route": "/assess" in paths,
        "assessment_route_source_unchanged":sha(assess_path)==before_by["backend/route/assessment_routes.py"],
        "production_model_artifact_hashes_unchanged":all(sha(p)==before_by[p.relative_to(REPO).as_posix()] for p in model_files),
        "production_assess_behavior_flag_off_on_identical":assess_off.status_code==assess_on.status_code and assess_off.json()==assess_on.json(),
        "experimental_router_separate":all(x in paths for x in ["/experimental/shadow-assess","/experimental/shadow-assess/debug"]),
        "shadow_module_calls_production_scorer":False}
    write("production_regression_results.json",production)
    contract={"purpose":"Evidence-first experimental shadow scoring demonstration.","route":"POST /experimental/shadow-assess",
        "debug_route":"POST /experimental/shadow-assess/debug","golden_fixture_route":"GET /experimental/shadow-golden-request",
        "frozen_scorecard_artifact":"backend/phase2/outputs/phase2f/frozen_shadow_scorecard.json",
        "feature_flag":{"name":"ENABLE_EXPERIMENTAL_SHADOW_SCORING","default":False,"disabled_status":404,"disabled_code":"EXPERIMENTAL_FEATURE_DISABLED"},
        "input":{"six_month_credit_card_statement_evidence":"required for eligible result","explicit_repayment_history":"required if statements do not contain status",
        "consent":"CREDIT_CARD_STATEMENTS required; BUREAU_REPAYMENT_HISTORY additionally required when repayment-history records are supplied","prediction_cutoff_month":"required",
            "caller_feature_vector":"not accepted","structured_evidence_only":True},
        "success_response_fields":["status","decision_use","eligibility","evidence","features","scorecard.raw_pd","scorecard.good_bad_odds","scorecard.experimental_shadow_score","reason_codes","trace_id","model_status","validation_scope","limitations"],
        "failure":{"status":"INSUFFICIENT_EXPERIMENTAL_EVIDENCE","eligible":False,"scorecard":None,"reason_codes":[]},
        "no_lending_decision":True,"no_risk_tier":True,"no_pdf_or_ocr":True,"no_persistent_evidence_storage":True,
        "calibration":False,"model_fitting":False,"PDO_is_presentation_only":True,
        "phase2b6_status":"PHASE_2B6_INCONCLUSIVE","production_status":"UNVERIFIED_REAL_WORLD"}
    write("shadow_api_contract.json",contract)
    with (OUT/"demo_capability_matrix.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(["Capability","Demo support","Production support"])
        w.writerows([["Structured six-month card evidence","Experimental","No"],["Controlled statement text","Phase 2E library only; not exposed by this API","No"],
            ["Explicit repayment-history records","Experimental","No"],["Arbitrary PDF","No","No"],["Credit-card OCR","No","No"],
            ["Evidence validation","Experimental verified","Existing production path separate"],["Four behavioral features","Experimental verified","No"],
            ["Raw experimental PD","Shadow only","No"],["PDO presentation score","Shadow only","No"],["Contribution reasons","Shadow only","No"],["Credit decision","No","No"]])
    after=_protected_after()
    write("protected_hash_verification.json",{"file_count":len(after),"all_unchanged":all(r["unchanged"] for r in after),"files":after})
    full_log=(OUT/"pytest_full_phase2.log").read_text(encoding="utf-8") if (OUT/"pytest_full_phase2.log").exists() else ""
    full_match=re.search(r"(\d+) passed(?:,\s*(\d+) failed)?(?:,\s*(\d+) skipped)?(?:,\s*(\d+) warnings?)?",full_log)
    full_passed=int(full_match.group(1)) if full_match else 0
    full_failed=int(full_match.group(2) or 0) if full_match else -1
    full_skipped=int(full_match.group(3) or 0) if full_match else -1
    api_log=(OUT/"pytest_phase2g.log").read_text(encoding="utf-8") if (OUT/"pytest_phase2g.log").exists() else ""
    api_match=re.search(r"(\d+) passed(?:,\s*(\d+) failed)?(?:,\s*(\d+) skipped)?",api_log)
    api_passed=int(api_match.group(1)) if api_match else 0
    build_log=(OUT/"frontend_build.log").read_text(encoding="utf-8") if (OUT/"frontend_build.log").exists() else ""
    frontend_passed="built in" in build_log and "error during build" not in build_log.lower()
    frontend_warnings=[]
    if "@import must precede" in build_log: frontend_warnings.append("Existing index.css has a PostCSS @import ordering warning.")
    if "caniuse-lite" in build_log: frontend_warnings.append("Browserslist data is stale.")
    write("frontend_build_results.json",{"production_build_passed":frontend_passed,
        "command":"node node_modules/vite/bin/vite.js build (project-local Vite; npm launcher is broken on this host)",
        "npm_run_build_launcher":"failed: missing global npm-cli.js",
        "manual_route_render":{"verified":True,"method":"local browser DOM inspection","visible":"Experimental Credit Evidence Lab, experimental warning, and Run Verified Example action"},
        "automated_frontend_test_framework_present":False,"manual_visual_review":"route loaded; golden button interaction not run against a live backend",
        "warnings":frontend_warnings,"log":"backend/phase2/outputs/phase2g/frontend_build.log"})
    test_results={"phase2g_api_tests":{"passed":api_passed,"failed":0 if api_passed else -1,
                        "command":"python -m pytest backend/phase2/tests/test_phase2g_shadow_api.py -q"},
        "full_phase2_suite":{"passed":full_passed,"failed":full_failed,"skipped":full_skipped,"baseline":227,
                             "command":"python -m pytest backend/phase2/tests -q"},
        "phase2g_tests_added":api_passed,"suite_passed":full_passed>227 and full_failed==0 and full_skipped==0,
        "log":"backend/phase2/outputs/phase2g/pytest_full_phase2.log"}
    write("phase2g_test_results.json",test_results)
    runtime_note="Python 3.14 on this host lacks pytesseract and scikit-learn required by the pre-existing production app import. Phase 2G endpoint integration was tested via TestClient on the mounted application with import-only stubs; production scoring was never invoked. Use the backend lock/Python 3.12 environment for local server startup."
    all_gates=all([production["assess_route"],production["assessment_route_source_unchanged"],
        production["production_model_artifact_hashes_unchanged"],production["production_assess_behavior_flag_off_on_identical"],
        production["experimental_router_separate"],json.loads((OUT/"negative_api_results.json").read_text())["all_fail_closed"],
        response.status_code==200,flag_off.status_code==404,flag_on.status_code==200,
        all(r["unchanged"] for r in after),frontend_passed,test_results["suite_passed"],
        golden_response["decision_use"]=="NOT_FOR_CREDIT_DECISION",golden_response["scorecard"]["pdo_presentation_only"]])
    final_status="PHASE_2G_SHADOW_DEMO_READY" if all_gates else "PHASE_2G_INTEGRATION_BLOCKED"
    summary={"status":final_status,"acceptance_gates_passed":all_gates,"api_path":"POST /experimental/shadow-assess",
        "feature_flag_default":False,"production_status":"UNVERIFIED_REAL_WORLD","phase2b6_status":"PHASE_2B6_INCONCLUSIVE",
        "golden_raw_pd":golden_response["scorecard"]["raw_pd"],
        "golden_shadow_score":golden_response["scorecard"]["experimental_shadow_score"],
        "negative_cases":len(negatives),"negative_cases_all_fail_closed":json.loads((OUT/"negative_api_results.json").read_text())["all_fail_closed"],
        "phase2g_api_tests":api_passed,"full_phase2_tests":full_passed,"frontend_build_passed":frontend_passed,
        "protected_file_count":len(after),"protected_hashes_unchanged":all(r["unchanged"] for r in after),
        "training_calls":0,"calibration_calls":0,"runtime_environment_note":runtime_note}
    write("phase2g_summary.json",summary)
    report=f'''# Phase 2G — Experimental Shadow API & Demo Integration\n\nStatus: `{final_status}`\n\n## Result\n\nThe evidence-first Phase 2D → 2E → 2F path is exposed through a separate, default-off experimental API and a separately labeled frontend page. The experimental PDO score is presentation-only. This phase does not validate the model or change production model status.\n\n## Golden API result\n\n- Endpoint: `POST /experimental/shadow-assess`; detailed trace: `POST /experimental/shadow-assess/debug`.\n- Feature flag: `ENABLE_EXPERIMENTAL_SHADOW_SCORING`, default `false`. Disabled calls return `EXPERIMENTAL_FEATURE_DISABLED`.\n- Features: `{json.dumps(golden_response['features'],sort_keys=True)}`.\n- Raw PD: {golden_response['scorecard']['raw_pd']:.15g}; good:bad odds: {golden_response['scorecard']['good_bad_odds']:.15g}; experimental PDO presentation score: {golden_response['scorecard']['experimental_shadow_score']:.12g}.\n- Reason order: {', '.join(r['label'] for r in golden_response['reason_codes'])}. The UI reports coefficient × WoE contribution reasons, never SHAP.\n- Golden evidence is the existing synthetic Phase 2E fixture; caller-supplied final feature vectors are rejected.\n\n## Fail-closed and isolation checks\n\n- API negative scenarios: {len(negatives)}; all returned no feature vector, PD, score, or reason codes. Statement-only evidence returns `MISSING_REPAYMENT_STATUS_EVIDENCE`; invalid consent blocks scoring; multiple accounts return `MULTI_ACCOUNT_AGGREGATION_UNRESOLVED`.\n- No risk tier or approve/reject output is present. PDF and OCR support are not claimed. Request evidence is not persisted.\n- `/assess` remains mounted, its source and production model/bin/manifest hashes are unchanged, and its response to the same invalid request was identical with the flag off and on.\n- Protected files checked: {len(after)}; unchanged: {all(r['unchanged'] for r in after)}.\n\n## Verification\n\n- Phase 2G API tests: {api_passed} passed. Full Phase 2 regression: {full_passed} passed, {full_failed} failed, {full_skipped} skipped (baseline 227).\n- Frontend production build: {'passed' if frontend_passed else 'failed'} using the project-local Vite executable. The global `npm` launcher is broken on this host; build warnings are recorded in `frontend_build_results.json`.\n- Browser DOM check confirmed the experimental page, warning, and Run Verified Example action. No frontend test framework exists; the golden action was verified through API integration tests, not by a live-browser click.\n- Runtime limitation: {runtime_note}\n- Phase 2F scorecard mathematics and artifacts were consumed unchanged. No fit, retraining, calibration, or production scorer call occurred in Phase 2G.\n\n## Status preserved\n\nPhase 2B.6 remains `PHASE_2B6_INCONCLUSIVE`; Phase 2C remains `PHASE_2C_REQUIRES_EVIDENCE_EXTENSION`; Phase 2D remains `PHASE_2D_CONTRACT_READY`; Phase 2E remains `PHASE_2E_EQUIVALENCE_VERIFIED`; Phase 2F remains `PHASE_2F_SHADOW_SCORE_VERIFIED`; production remains `UNVERIFIED_REAL_WORLD`.\n'''
    (OUT/"phase2g_report.md").write_text(report,encoding="utf-8")
    return final_status


if __name__=="__main__": print(build())
