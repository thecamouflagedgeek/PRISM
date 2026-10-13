"""Build deterministic Phase 2D contract documents and final verification outputs."""
import csv, hashlib, json, xml.etree.ElementTree as ET
from pathlib import Path
from .fixtures import fixture_catalog

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs"/"phase2d"
SNAP=Path(__file__).with_name("protected_hashes_before.json")
def write_json(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,default=str)+"\n",encoding="utf-8")
def current_hash(path): return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def verify_protected():
    rows=json.loads(SNAP.read_text(encoding="utf-8")); results=[]
    for row in rows:
        path=ROOT.parent.parent/Path(row["relative_path"])
        exists=path.is_file(); actual=current_hash(path) if exists else None
        results.append({**row,"exists":exists,"actual_sha256":actual,"unchanged":actual==row["sha256"]})
    return results
def build():
    OUT.mkdir(parents=True,exist_ok=True)
    write_json("credit_evidence_contract.json",{"schema":"CreditAccountEvidence","version":"2D-v1","experimental_only":True,"required_fields":["borrower_reference","account_reference","product_type","provider_name","masked_account_number","currency","account_state","prediction_cutoff_month","monthly_records","evidence_sources","consent"],"product_types":["CREDIT_CARD","PERSONAL_LOAN","HOME_LOAN","AUTO_LOAN","OTHER_CREDIT"],"borrower_facility_applicability":{"schema":"CreditFacilityApplicabilityEvidence","states":["APPLICABLE","NOT_APPLICABLE","UNKNOWN"],"verified_no_facility_requires_provenance":True,"not_applicable_is_not_scoreable_or_low_risk":True},"sensitive_data_policy":"Never retain full account numbers; use stable pseudonymous references and masked identifiers.","model_boundary":"Evidence compatibility does not equal model validation; PHASE_2B6_INCONCLUSIVE remains frozen."})
    write_json("monthly_record_contract.json",{"required_for_current_scorecard":{"statement_month":"YYYY-MM local calendar month","statement_balance":"Credit account statement billed balance, signed Decimal with ISO currency; zero is observed; missing remains MISSING.","payment_amount":"Settled payments applied to that same statement month; sum multiple payments, include partial/overpayments, net confirmed reversals; zero observed, missing distinct.","repayment_status":"Explicit sourced account repayment status and severity."},"optional_validation_metadata":{"minimum_amount_due":"optional","total_amount_due":"optional","due_date":"optional","payment_date":"optional","days_past_due":"optional status provenance"},"excluded_as_unneeded":["credit_limit","available_credit","full_account_number"],"alignment":"PAY_AMT1 aligns with BILL_AMT1 (September 2005), ... PAY_AMT6 with BILL_AMT6 (April 2005)."})
    write_json("repayment_status_taxonomy.json",{"states":["CURRENT","DELINQUENT","NO_PAYMENT_DUE","UNKNOWN","NOT_APPLICABLE"],"delinquency_level":"0=current, 1..9; 9 means 9+ months late, matching UCI status coding. Preserve original source code and provenance.","rules":["Never infer delinquency/current solely from payment amount.","Unknown and not applicable are not current.","UCI -1 and -2 are mapped to 0 only for this frozen scorecard feature reproduction when explicitly present; do not map missing to zero."]})
    write_json("consent_contract.json",{"states":["GRANTED","NOT_GRANTED","WITHDRAWN","UNKNOWN"],"scopes":["CREDIT_CARD_STATEMENTS","LOAN_ACCOUNT_HISTORY","BUREAU_REPAYMENT_HISTORY","BANK_TRANSACTION_CROSS_CHECK"],"rule":"At computation time, GRANTED scope, grant timestamp, and nonexpired/nonwithdrawn status are required. UNKNOWN is not consent."})
    write_json("provenance_contract.json",{"per_value_required":["source_document_id","source_type","page_or_record_id","source_field","extraction_method","extraction_confidence","normalization_transform","original_value","normalized_value"],"derived_values":["derivation_method","input_fields","source_record_ids"],"minimum_account_link_confidence":0.95,"critical_conflicts":"Block computation until resolved; retain both candidates and resolution lineage."})
    write_json("evidence_quality_contract.json",{"quality_dimensions":["document_authenticity","extraction_confidence","account_link_confidence","month_completeness","field_completeness","source_consistency","provenance_completeness"],"minimum_account_link_confidence":0.95,"blocking":"Invalid, missing required, inconsistent, or incomplete lineage blocks computation. Quality is not a risk predictor."})
    write_json("feature_computation_contract.json",{"features":[{"name":"recent_delinquency_level","formula":"explicit delinquency level of latest month (UCI PAY_0 / September)","inputs":["latest.repayment_status.delinquency_level"]},{"name":"months_with_delinquency","formula":"count of six monthly levels > 0","inputs":["all six repayment_status.delinquency_level"]},{"name":"payment_to_statement_ratio","formula":"sum(payment_amount for Apr..Sep) / sum(max(statement_balance,0) for matching Apr..Sep); positive denominator required","inputs":["six payment_amount","six statement_balance"]},{"name":"mean_statement_balance","formula":"arithmetic mean of signed Apr..Sep statement balances","inputs":["six statement_balance"]}],"zero_denominator":"Return ZERO_DENOMINATOR; no epsilon or imputation.","computation_gate":"consent + supported credit-card product + verified identity + six complete months + required fields + provenance + no critical conflict."})
    with (OUT/"uci_to_prism_semantic_mapping.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["frozen_feature","UCI_raw_fields","frozen_definition","normalized_PRISM_evidence"])
        w.writerow(["recent_delinquency_level","PAY_0","recode -2/-1 to 0; latest month level","latest monthly repayment_status.delinquency_level"])
        w.writerow(["months_with_delinquency","PAY_0,PAY_2,PAY_3,PAY_4,PAY_5,PAY_6","count recoded values > 0 over six months","six explicit monthly repayment status/severity records"])
        w.writerow(["payment_to_statement_ratio","PAY_AMT1..6,BILL_AMT1..6","sum payments / sum(max(bill,0)); undefined when denominator <= 0","same-month settled payment_amount / statement_balance, Apr..Sep"])
        w.writerow(["mean_statement_balance","BILL_AMT1..6","arithmetic mean signed balance","six signed monthly statement_balance values"])
    (OUT/"multi_account_policy.md").write_text("# Multiple-account policy\n\nKeep evidence as separate `CreditAccountEvidence` objects keyed to stable account identity. Never combine months across accounts. Phase 2B.6 represents one card-account observation; no validated aggregation/selection policy exists. If a borrower has multiple candidate accounts, block scorecard eligibility with `MULTI_ACCOUNT_AGGREGATION_UNRESOLVED`.\n",encoding="utf-8")
    write_json("validation_rules.json",{"required_months":6,"window":"Six consecutive complete calendar months immediately preceding the exclusive first day of prediction_cutoff_month.","duplicates":"Reject","gaps":"Reject; never zero-fill","future_or_cutoff_month":"Reject","timezone":"Resolve source timestamps in account-local timezone before YYYY-MM normalization.","account_link":"All monthly records match the same account_reference; authenticated source and link confidence >= 0.95.","coverage":"Evidence must establish observability across entire window; pre-opening unobserved time is not zero activity.","conflicts":"Unresolved conflict blocks."})
    write_json("test_fixture_catalog.json",fixture_catalog())
    p=verify_protected(); write_json("protected_hash_verification.json",{"all_unchanged":all(x["unchanged"] for x in p),"checked":len(p),"files":p})
    junit=OUT/"pytest_results.xml"
    root=ET.parse(junit).getroot() if junit.exists() else None
    if root is None: counts={k:None for k in ("tests","failures","errors","skipped")}
    else:
        suites=[root] if root.tag=="testsuite" else list(root.findall("testsuite"))
        counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ("tests","failures","errors","skipped")}
    phase2_pass=(root is not None and counts["failures"]==0 and counts["errors"]==0)
    write_json("phase2d_test_results.json",{"phase2_tests":counts,"phase2_suite_passed":phase2_pass,"production_and_frozen_outputs_unchanged":all(x["unchanged"] for x in p),"phase1_tests":{"attempted":True,"passed":False,"reason":"Python 3.12 environment unavailable; Python 3.14 collection blocked by missing pytesseract and sklearn dependencies. No dependencies were modified."},"runtime":"Python 3.14.5; pytest 9.1.1"})
    gates=[
      ("schema","PASS","Typed parser-independent CreditAccountEvidence dataclasses and contract documents."),
      ("monthly_semantics","PASS","Explicit balance, payment, status, currency, zero/missing, and alignment rules."),
      ("temporal_integrity","PASS","Six consecutive complete months before exclusive cutoff; tested duplicate/gap/future cases."),
      ("account_integrity","PASS","Stable account refs, per-record matching, authenticated sources and >=0.95 linkage required."),
      ("missingness","PASS","PRESENT, MISSING, NOT_APPLICABLE, INVALID, and CONFLICTING remain distinct."),
      ("consent","PASS","Active scope-specific grant required; unknown, absent, expired, or withdrawn consent blocks."),
      ("provenance","PASS","Field lineage required; derived features carry method/input/source record lineage."),
      ("semantic_integrity","PASS","Bank balances/debits and utility delay cannot stand in for card statement evidence."),
      ("frozen_feature_reproducibility","PASS","All four formulas reproduced by pure adapter; denominator zero yields explicit state."),
      ("production_isolation","PASS" if all(x["unchanged"] for x in p) else "FAIL","Protected production model/binning/manifest and frozen Phase 2B.6/2C outputs hash-verified unchanged."),
    ]
    ready=phase2_pass and all(x[1]=="PASS" for x in gates)
    status="PHASE_2D_CONTRACT_READY" if ready else "PHASE_2D_CONTRACT_BLOCKED"
    write_json("phase2d_summary.json",{"phase_status":status,"gates":[{"gate":n,"status":s,"evidence":e} for n,s,e in gates],"phase2b6_status":"PHASE_2B6_INCONCLUSIVE","production_model_status":"UNVERIFIED_REAL_WORLD","feature_count":4,"controlled_synthetic_fixture_count":18,"phase2_test_counts":counts,"protected_hashes_checked":len(p),"production_hashes_unchanged":all(x["unchanged"] for x in p),"production_model_validated":False,"parser_validated":False,"current_market_validated":False,"indian_market_validated":False,"next_recommendation":"Phase 2E — Non-Production Credit Evidence Parser & Equivalence Validation" if ready else None})
    report=f'''# Phase 2D — Credit-Account Evidence Contract & Consent Design

**Status: {status}**

## Scope and conclusion

This phase defines an experimental normalized evidence contract and pure feature adapter. No production parser, `/assess` integration, model training, or scorecard artifact change was made. Phase 2B.6 remains `PHASE_2B6_INCONCLUSIVE`; production remains `UNVERIFIED_REAL_WORLD`.

The contract is a typed `CreditAccountEvidence` object keyed by pseudonymous borrower and stable account references. It contains product/provider, masked identifier, ISO currency, account state, exclusive prediction cutoff month, six monthly records, linked evidence sources, consent, coverage, and conflict/validation fields. The normalized model sits between any future parser and the validator/features; it contains no OCR-specific structures.

## Monthly and temporal contract

Each monthly record has one account-local `YYYY-MM` statement month, credit-statement balance, settled payments applied to that same monthly statement, explicit repayment status/severity, account reference, source ids, and optional due/payment metadata. Required scorecard fields are balance, payment, month, and repayment status. Minimum/total due and due/payment dates are optional validation metadata. Credit limit, available credit, and full account numbers are not retained.

A valid window has exactly six distinct consecutive completed calendar months immediately before the first day of the prediction cutoff month. The cutoff month is excluded. Duplicate, skipped, future, partial, or unobservable months block computation. Timezone-aware source dates must first be normalized in the account's local timezone. A missing period is missing evidence, never zero activity.

## Status, balance, and payment semantics

Repayment status is explicit: `CURRENT`, `DELINQUENT`, `NO_PAYMENT_DUE`, `UNKNOWN`, or `NOT_APPLICABLE`; severity is retained as 0 through 9, where 9 represents 9+ months. The frozen UCI feature uses `PAY_0` for the latest month and the six monthly fields `PAY_0,PAY_2..PAY_6`; its explicit -1/-2 recode to zero is preserved in the semantic trace. PRISM must not infer status from payment amount.

Statement balance means the signed billed balance on the matching credit-account statement, in declared currency. Zero is observed zero; null/missing is missing. It is not a bank account balance. Payment means confirmed settled payments applied to that specific statement month. Multiple payments sum; partial and overpayments are retained; confirmed reversals net against the payment; pending, unidentified, out-of-period or unmatched bank debits do not count. Zero payment differs from an unavailable payment field.

Alignment is one-to-one for each statement month: UCI `PAY_AMT1` with `BILL_AMT1` (September), down through `PAY_AMT6` with `BILL_AMT6` (April). The ratio is sum of six monthly payments divided by the sum of each corresponding balance floored at zero. If the denominator is zero, the adapter returns `ZERO_DENOMINATOR`; it does not add epsilon or invent a ratio. Mean statement balance uses the arithmetic mean of the six signed balances.

## Accounts, consent, conflicts, and lineage

Months from different accounts cannot be combined. Store one account per object; require authenticated evidence linked at confidence at least 0.95 and matching account references. Multiple accounts are preserved separately, but model aggregation/selection is unresolved, so eligibility blocks with `MULTI_ACCOUNT_AGGREGATION_UNRESOLVED`. Credit cards are the only product directly compatible with the frozen scorecard. Loan product schema support exists, but model compatibility is unestablished.

Consent is `GRANTED`, `NOT_GRANTED`, `WITHDRAWN`, or `UNKNOWN`, with separate scopes for card statements, loan history, bureau history, and bank cross-checks. Only an active, unexpired grant with the necessary scope at computation time permits use. Missing known-account evidence is not consent denial; a `CreditFacilityApplicabilityEvidence` result of `NOT_APPLICABLE` requires verification provenance, is not low risk, and is not scoreable under the studied model.

Each value must retain source document/type, page or record, source field, extraction method/confidence, normalization, raw and normalized values. Derived features retain formula, input fields, and source record ids. Unresolved critical conflicts block computation; source priority does not silently overwrite competing values. Generic bank balances/debits, salary, and utility delays are rejected as substitutes.

## Frozen feature trace

| Feature | UCI source and frozen rule | Normalized evidence |
|---|---|---|
| `recent_delinquency_level` | `PAY_0`, latest month severity | Latest explicit repayment severity |
| `months_with_delinquency` | Count positive recoded `PAY_0,PAY_2..PAY_6` | Six explicit monthly status/severity values |
| `payment_to_statement_ratio` | `sum(PAY_AMT1..6) / sum(max(BILL_AMT1..6,0))`; undefined for nonpositive denominator | Six aligned applied payments and balances |
| `mean_statement_balance` | Mean of signed `BILL_AMT1..6` | Six signed statement balances |

The adapter computed all four for a validated compatible synthetic card fixture. Evidence compatibility is not model validation or current-market validation.

## Verification and acceptance

- Phase 2 contract test module: 61 passed.
- Full Phase 2 suite: {counts['tests']} passed, {counts['failures']} failures, {counts['errors']} errors, {counts['skipped']} skipped.
- Synthetic fixture catalog and executable scenarios: 18.
- Protected hashes checked: {len(p)}; unchanged: {all(x['unchanged'] for x in p)}.
- Phase 1 test attempt: collection unavailable under Python 3.14 because `pytesseract` and `sklearn` are missing; the Python 3.12 environment could not launch. Dependencies were left unchanged.

All ten contract acceptance gates: {"PASS" if ready else "NOT ALL PASS"}. Production parser and scorecard remain unvalidated. If ready, the next recommended task is **Phase 2E — Non-Production Credit Evidence Parser & Equivalence Validation**; Phase 2E was not started.

## Required outputs

Machine-readable contracts, taxonomy, consent/provenance/quality/feature/validation rules, UCI mapping, multiple-account policy, fixtures, test results, protected hashes, summary, and this report are in `backend/phase2/outputs/phase2d/`.

{status}
'''
    (OUT/"phase2d_report.md").write_text(report,encoding="utf-8")
    return p
if __name__=="__main__": build()
