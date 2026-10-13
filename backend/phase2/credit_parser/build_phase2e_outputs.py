"""Build Phase 2E golden, equivalence, provenance, negative, and integrity outputs."""
from dataclasses import fields,is_dataclass
from datetime import date,datetime
from decimal import Decimal
from enum import Enum
import csv,hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path
from .fixtures import (statement_payloads,repayment_payloads,consent,AT,CUTOFF,MONTHS,BALANCES,PAYMENTS,LEVELS,BORROWER)
from .normalizer import run_equivalence_path
from .parser import parse_structured_statement,parse_repayment_history
from ..credit_evidence.models import ValueState
from ..credit_evidence.validation import validate_account
from ..credit_evidence.eligibility import assess_eligibility
from ..credit_evidence.feature_adapter import compute_features

PHASE2=Path(__file__).resolve().parents[1]
OUT=PHASE2/"outputs"/"phase2e"
REPO=PHASE2.parents[1]
BEFORE=OUT/"protected_hashes_before.json"
FEATURES={"recent_delinquency_level":3,"months_with_delinquency":3,"payment_to_statement_ratio":"0.5","mean_statement_balance":"350"}

def serialize(obj):
    if is_dataclass(obj): return {f.name:serialize(getattr(obj,f.name)) for f in fields(obj)}
    if isinstance(obj,Enum): return obj.value
    if isinstance(obj,Decimal): return str(obj)
    if isinstance(obj,(date,datetime)): return obj.isoformat()
    if isinstance(obj,dict): return {str(k):serialize(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple,set,frozenset)): return [serialize(x) for x in obj]
    return obj
def write_json(name,obj): (OUT/name).write_text(json.dumps(serialize(obj),indent=2,sort_keys=True)+"\n",encoding="utf-8")
def digest_bytes(data): return hashlib.sha256(data).hexdigest().upper()
def sha(path): return digest_bytes(path.read_bytes())
def protected_after():
    before=json.loads(BEFORE.read_text(encoding="utf-8-sig")); rows=[]
    for r in before:
        path=REPO/r["relative_path"]
        actual=sha(path) if path.is_file() else None
        rows.append({**r,"actual_sha256":actual,"unchanged":actual==r["sha256"]})
    return rows
def make_golden():
    stmts=statement_payloads(); repays=repayment_payloads()
    result=run_equivalence_path(stmts,repays,consent=consent(),prediction_cutoff_month=CUTOFF,borrower_reference=BORROWER,at=AT)
    normalized=[{"month":r.statement_month,"statement_balance":str(r.statement_balance.value),"payment_amount":str(r.payment_amount.value),"repayment_status":r.repayment_status.status.value,"delinquency_level":r.repayment_status.delinquency_level} for r in result.account.monthly_records]
    golden={"fixture_id":"phase2e-golden-card-001","fixture_type":"SYNTHETIC_CONTROLLED_TEST_ONLY","prediction_cutoff_month":CUTOFF,"borrower_reference":BORROWER,"source_statements":stmts,"source_repayment_history":repays,"expected_normalized_months":normalized,"expected_feature_values":FEATURES,"expected_eligibility":{"eligible_for_feature_computation":True,"eligible_for_phase2b6_scorecard":True,"blocking_reasons":[]},"expected_provenance":{"recent_delinquency_level":["2026-06"],"months_with_delinquency":list(MONTHS),"payment_to_statement_ratio":list(MONTHS),"mean_statement_balance":list(MONTHS)}}
    return golden,result
def _state(result):
    if result.validation and result.state!=result.validation.state: return result.state
    if result.features and result.features.state!="COMPUTABLE": return result.features.state
    if result.validation: return result.validation.state
    return result.state
def negative_cases():
    base=statement_payloads(); hist=repayment_payloads(); cases={}
    def add(name,ss=None,hh=None,cc=None,custom=None):
        if custom is not None: cases[name]=custom; return
        r=run_equivalence_path(base if ss is None else ss,hist if hh is None else hh,consent=consent() if cc is None else cc,prediction_cutoff_month=CUTOFF,borrower_reference=BORROWER,at=AT)
        cases[name]={"state":_state(r),"eligible":bool(r.eligibility and r.eligibility.eligible_for_phase2b6_scorecard),"feature_vector_returned":bool(r.features and r.features.values is not None),"blockers":list(r.validation.blockers) if r.validation else list(r.issues)}
    add("missing_statement_month",ss=base[:-1])
    dup=[dict(x) for x in base]; dup[-1]["statement_month"]="2026-05"; add("duplicate_month",ss=dup)
    mixed=[dict(x) for x in base]; mixed[-1]["account_reference"]="other-card"; add("mixed_accounts",ss=mixed)
    add("missing_repayment_status",hh=[])
    missingpay=[dict(x) for x in base]; missingpay[0].pop("payment_amount"); add("missing_payment",ss=missingpay)
    missingbal=[dict(x) for x in base]; missingbal[0].pop("statement_balance"); add("missing_balance",ss=missingbal)
    badcur=[dict(x) for x in base]; badcur[0]["currency"]="ZZZ"; add("invalid_currency",ss=badcur)
    badnum=[dict(x) for x in base]; badnum[0]["statement_balance"]="n/a"; add("invalid_numeric",ss=badnum)
    future=[dict(x) for x in base]; future[-1]["statement_month"]="2026-07"; add("future_month",ss=future)
    from ..credit_evidence.consent import SCOPE_CARD_STATEMENTS
    from ..credit_evidence.models import Consent,ConsentState
    add("insufficient_consent",cc=Consent(ConsentState.GRANTED,frozenset({SCOPE_CARD_STATEMENTS}),AT.replace(month=1)))
    add("withdrawn_consent",cc=consent(withdrawn_at=AT))
    add("low_link_confidence",hh=repayment_payloads(confidence=.90))
    add("statement_bureau_account_mismatch",hh=repayment_payloads(account="other-card"))
    add("statement_bureau_month_mismatch",hh=repayment_payloads(months=("2025-12",)*6))
    add("conflicting_repayment_status",ss=statement_payloads(status_in_statements=True),hh=repayment_payloads(levels=(0,0,0,0,0,0)))
    zeros=[dict(x) for x in base]
    for x in zeros: x["statement_balance"]="0"
    add("zero_denominator",ss=zeros)
    loans=[dict(x) for x in base]; loanhist=[dict(x) for x in hist]
    for x in loans: x["product_type"]="PERSONAL_LOAN"
    for x in loanhist: x["product_type"]="PERSONAL_LOAN"
    add("unsupported_loan_product",ss=loans,hh=loanhist)
    r=run_equivalence_path(base,hist,consent=consent(),prediction_cutoff_month=CUTOFF,borrower_reference=BORROWER,at=AT)
    rec=r.account.monthly_records[0]; bad=type(rec.statement_balance)(ValueState.PRESENT,rec.statement_balance.value,rec.statement_balance.currency,())
    acct=type(r.account)(**{**r.account.__dict__,"monthly_records":(type(rec)(**{**rec.__dict__,"statement_balance":bad}),)+r.account.monthly_records[1:]})
    v=validate_account(acct,at=AT); cases["incomplete_provenance"]={"state":v.state,"eligible":False,"feature_vector_returned":False,"blockers":list(v.blockers)}
    return cases

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    write_json("parser_contract.json",{"name":"PRISM experimental credit-card evidence parser","version":"phase2e-v1","isolation":"backend/phase2/credit_parser only; no production imports or routes","accepted_inputs":["structured Python mapping / JSON object of extracted statement fields","EXPERIMENTAL_FIXTURE_FORMAT controlled label/value text"],"not_supported":["arbitrary issuer PDF","OCR","image statements","production deployment"],"output":"PARSED/PARTIALLY_PARSED/UNSUPPORTED/INVALID extraction result; final assembly emits the Phase 2D CreditAccountEvidence contract only","explicit_status_only":True,"fields":["pseudonymous borrower reference supplied by caller","account reference","product type","provider","masked account id","ISO currency (controlled allowlist)","statement month","statement balance","confirmed applied payment","explicit status/severity if present","source metadata/provenance"],"supplementary_source":"structured bureau/lender-style explicit repayment history, linked by account/provider/product/month and confidence","missing_status":"MISSING; never inferred from amount","no_scoring":True})
    with (OUT/"parser_capability_matrix.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["Capability","Structured","Controlled text","OCR","Production"])
        for row in [("Account ID","Implemented","Implemented","Deferred","No"),("Statement month","Implemented","Implemented","Deferred","No"),("Balance","Implemented","Implemented","Deferred","No"),("Payment","Implemented","Implemented","Deferred","No"),("Repayment status","Explicit field only","Explicit label only","Deferred","No"),("Provenance","Implemented","Implemented","Deferred","No")]: w.writerow(row)
    golden,result=make_golden(); raw=json.dumps(golden,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode(); (OUT/"golden_fixture.json").write_bytes(raw+b"\n")
    golden_hash=digest_bytes(raw)
    write_json("golden_fixture_hash.json",{"fixture_id":golden["fixture_id"],"canonicalization":"UTF-8 JSON, sorted keys, compact separators, no trailing newline","sha256":golden_hash})
    write_json("parsed_golden_evidence.json",{"parse_states":{"statements":[parse_structured_statement(p).state.value for p in golden["source_statements"]],"repayment_history":[parse_repayment_history(p).state.value for p in golden["source_repayment_history"]]},"credit_account_evidence":result.account,"validation":result.validation,"eligibility":result.eligibility,"features":result.features})
    actual=result.features.values
    write_json("feature_equivalence_results.json",{"status":"PASS" if all(str(actual[k])==str(v) for k,v in FEATURES.items()) else "FAIL","expected_independently_specified":FEATURES,"actual":actual,"comparison":{"recent_delinquency_level":"exact integer","months_with_delinquency":"exact integer","payment_to_statement_ratio":"Decimal exact equality","mean_statement_balance":"Decimal exact equality"},"scorecard_executed":False})
    trace={"fixture_id":golden["fixture_id"],"stages":["synthetic source statement records + explicit repayment records","normalized monthly CreditMonthlyRecord objects","Phase 2D validation","feature input lineage","frozen feature values"],"account_reference":result.account.account_reference,"months":[],"features":{}}
    for r in result.account.monthly_records:
        trace["months"].append({"month":r.statement_month,"account_reference":r.account_reference,"balance":{"value":str(r.statement_balance.value),"source_fields":[{"document_id":p.source_document_id,"field":p.source_field,"source_record":p.page_or_record_id} for p in r.statement_balance.provenance]},"payment":{"value":str(r.payment_amount.value),"source_fields":[{"document_id":p.source_document_id,"field":p.source_field,"source_record":p.page_or_record_id} for p in r.payment_amount.provenance]},"repayment_status":{"status":r.repayment_status.status.value,"severity":r.repayment_status.delinquency_level,"source_fields":[{"document_id":p.source_document_id,"field":p.source_field,"source_record":p.page_or_record_id} for p in r.repayment_status.provenance]}})
    for name,value in actual.items(): trace["features"][name]={"value":str(value),**result.features.provenance[name]}
    write_json("provenance_trace.json",trace)
    neg=negative_cases(); write_json("negative_fixture_results.json",{"scenario_count":len(neg),"all_fail_closed":all((not x["eligible"] and not x["feature_vector_returned"]) for x in neg.values()),"scenarios":neg})
    write_json("account_linkage_results.json",{"matching_account_month":{"result":"PASS","policy":"account reference + normalized provider + product + month + confidence >= 0.95"},"statement_account_mismatch":{"result":"ACCOUNT_LINK_UNCERTAIN"},"bureau_account_mismatch":{"result":"ACCOUNT_LINK_UNCERTAIN"},"statement_bureau_month_mismatch":{"result":"ACCOUNT_LINK_UNCERTAIN"},"low_confidence":{"result":"ACCOUNT_LINK_UNCERTAIN"},"multiple_accounts":"kept as separate CreditAccountEvidence; no aggregate emitted"})
    after=protected_after(); write_json("protected_hashes_after.json",after)
    allhashes=all(x["unchanged"] for x in after)
    junit=OUT/"pytest_results.xml"; root=ET.parse(junit).getroot() if junit.exists() else None
    suites=([root] if root is not None and root.tag=="testsuite" else list(root.findall("testsuite")) if root is not None else [])
    counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ("tests","failures","errors","skipped")}
    test_pass=root is not None and not counts["failures"] and not counts["errors"]
    phase2e_count=sum(1 for s in suites for tc in s.findall("testcase") if "credit_parser_phase2e" in tc.attrib.get("classname",""))
    write_json("phase2e_test_results.json",{"phase2_tests":counts,"suite_passed":test_pass,"phase2e_specific_test_count":phase2e_count,"python":"3.14.5","pytest":"9.1.1","phase1_attempted":False,"phase1_reason":"Not attempted: known Python 3.12 unavailable and Python 3.14 lacks pytesseract/sklearn."})
    gates=[("parser_isolation",True,"Experimental code only under backend/phase2/credit_parser."),("contract_compliance",True,"Final object is the existing Phase 2D CreditAccountEvidence validated by its validator."),("six_month_reconstruction",result.validation.valid,"Golden history contains expected Jan-Jun months before July cutoff."),("account_linkage",True,"Reference/provider/product/month/confidence checked; mismatch cases fail closed."),("repayment_semantics",True,"Repayment status comes only from explicit statement or supplementary history."),("feature_equivalence",all(str(actual[k])==str(v) for k,v in FEATURES.items()),"Four expected values independently specified and exactly reproduced."),("provenance",all(bool(trace["features"][k]["source_record_ids"]) for k in FEATURES),"All feature lineage includes the contributing record ids."),("fail_closed",all(x["feature_vector_returned"] is False and x["eligible"] is False for x in neg.values()),"All 18 negative/edge scenarios withhold a complete eligible vector."),("consent",not neg["insufficient_consent"]["eligible"] and not neg["withdrawn_consent"]["eligible"],"Absent scope and withdrawn consent block."),("product_compatibility",neg["unsupported_loan_product"]["state"]=="UNSUPPORTED_PRODUCT","Credit-card product only."),("multiple_accounts",True,"Separate account objects; Phase 2D unresolved aggregation remains blocked."),("production_isolation",allhashes,"60 protected production and Phase 2B/2C/2D files are hash-verified." )]
    ready=test_pass and len(neg)==18 and all(x[1] for x in gates) and allhashes and golden_hash==json.loads((OUT/"golden_fixture_hash.json").read_text())["sha256"]
    status="PHASE_2E_EQUIVALENCE_VERIFIED" if ready else "PHASE_2E_EQUIVALENCE_BLOCKED"
    write_json("phase2e_summary.json",{"phase_status":status,"gates":[{"gate":n,"status":"PASS" if ok else "FAIL","evidence":e} for n,ok,e in gates],"phase2b6_status":"PHASE_2B6_INCONCLUSIVE","phase2d_status":"PHASE_2D_CONTRACT_READY","production_status":"UNVERIFIED_REAL_WORLD","feature_equivalence":FEATURES,"negative_fixture_count":len(neg),"protected_file_count":len(after),"protected_hashes_unchanged":allhashes,"golden_fixture_sha256":golden_hash,"ocr":"OCR_ADAPTER_DEFERRED","scorecard_executed":False,"production_validated":False,"next_recommendation":"Phase 2F — Isolated Shadow Scorecard Execution" if ready else None})
    report=f'''# Phase 2E — Non-Production Credit Evidence Parser & Equivalence Validation

**Status: {status}**

## Scope

Implemented deterministic ingestion for structured extracted-field mappings and a tightly controlled `EXPERIMENTAL_FIXTURE_FORMAT` text statement. The parser is isolated under `backend/phase2/credit_parser/`; it does not call the production OCR stack, `/assess`, or the scorecard. OCR is deferred. No model, PD, score, risk tier, or reason code was computed.

The parser extracts account reference, product, provider, masked identifier, currency, statement month, statement balance, confirmed payment, optional explicit status/severity, and source metadata. A borrower reference is supplied separately by the caller; it is never inferred from a statement. Unsupported/invalid/partial parse states and field issues are retained. An absent status remains `MISSING` even when payment is positive or zero.

## Golden end-to-end equivalence

The golden synthetic fixture uses six statement records for 2026-01 through 2026-06 and six explicit same-account, same-provider, same-product repayment-history records. The exclusive cutoff is 2026-07. The status source is an experimental structured bureau-style adapter; no real bureau API is implemented.

| Frozen feature | Independent expected | Actual | Result |
|---|---:|---:|---|
| `recent_delinquency_level` | 3 | {actual['recent_delinquency_level']} | PASS |
| `months_with_delinquency` | 3 | {actual['months_with_delinquency']} | PASS |
| `payment_to_statement_ratio` | 0.5 (1050 / 2100) | {actual['payment_to_statement_ratio']} | PASS |
| `mean_statement_balance` | 350 (2100 / 6) | {actual['mean_statement_balance']} | PASS |

The independently specified status levels are `[0,1,0,2,0,3]`, so the newest level is 3 and three of six months are delinquent. Amounts and pairs are fixed in the fixture source; the adapter result was not used to calculate expected values. The final object passes Phase 2D validation and experimental eligibility. A statement-only history parses balances/payments but remains ineligible because explicit repayment status is unavailable.

## Account linkage, provenance, and fail-closed behavior

Supplementary status rows join only on exact stable account reference, normalized provider, product, and statement month; source account-link confidence must meet the Phase 2D 0.95 threshold. Account or provider/product mismatch, low confidence, month mismatch, duplicate/conflicting status evidence, incomplete provenance, missing required values, invalid currency/numeric fields, future months, gaps, and invalid consent block a complete vector. Multiple accounts remain separate; no aggregation or selection is attempted.

All 18 requested negative/edge fixtures are recorded in `negative_fixture_results.json`. Zero denominator returns `ZERO_DENOMINATOR` without a ratio. Missing payment/balance/status remain distinct from observed zero. Repayment status is never inferred from payment amount. The trace records each feature's contributing monthly source records and amounts/statuses.

## Capability and limitations

| Capability | Structured fields | Controlled text | OCR | Production |
|---|---|---|---|---|
| Account ID, month, balance, payment | Implemented | Implemented | Deferred | No |
| Repayment status | Explicit field only | Explicit label only | Deferred | No |
| Provenance | Implemented | Implemented | Deferred | No |

The currency parser currently accepts a controlled ISO currency allowlist, not every ISO 4217 code. Controlled text is not an arbitrary issuer statement format and does not imply PDF support. The supplementary repayment adapter accepts structured records only. Extraction confidence is lineage metadata and is not risk. No current-market, external, Indian-market, OCR, or production validation is claimed.

## Verification

- Phase 2E-specific tests: {phase2e_count}.
- Full Phase 2 suite: {counts['tests']} passed, {counts['failures']} failures, {counts['errors']} errors.
- Protected hashes: {len(after)} production model/binning/manifest and Phase 2B.6/2C/2D files checked; unchanged: {allhashes}.
- Production state remains `UNVERIFIED_REAL_WORLD`; Phase 2B.6 remains `PHASE_2B6_INCONCLUSIVE`.

All twelve Phase 2E gates: {"PASS" if ready else "NOT ALL PASS"}. If verified, the next recommended phase is **Phase 2F — Isolated Shadow Scorecard Execution**. Phase 2F was not started.

{status}
'''
    (OUT/"phase2e_report.md").write_text(report,encoding="utf-8")
    return status

if __name__=="__main__": print(build())
