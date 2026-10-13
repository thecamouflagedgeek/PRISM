from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import hashlib, json
import pytest
from phase2.credit_parser.fixtures import (statement_payloads,repayment_payloads,consent,AT,CUTOFF,MONTHS,BALANCES,PAYMENTS,LEVELS,text_statement_payloads,BORROWER)
from phase2.credit_parser.parser import (parse_structured_statement,parse_controlled_text_statement,parse_repayment_history,normalize_month,normalize_provider,normalize_amount)
from phase2.credit_parser.normalizer import run_equivalence_path,assemble_credit_account
from phase2.credit_parser.models import ParseState
from phase2.credit_evidence.models import *
from phase2.credit_evidence.validation import validate_account
from phase2.credit_evidence.eligibility import assess_eligibility
from phase2.credit_evidence.feature_adapter import compute_features
from phase2.credit_evidence.consent import SCOPE_CARD_STATEMENTS

EXPECTED={"recent_delinquency_level":3,"months_with_delinquency":3,"payment_to_statement_ratio":Decimal("0.5"),"mean_statement_balance":Decimal("350")}

def run(stmts=None,history=None,cons=None):
    return run_equivalence_path(statement_payloads() if stmts is None else stmts,
        repayment_payloads() if history is None else history,consent=cons or consent(),prediction_cutoff_month=CUTOFF,borrower_reference=BORROWER,at=AT)

def test_structured_statement_parsing(): assert parse_structured_statement(statement_payloads()[0]).state is ParseState.PARTIALLY_PARSED
def test_parser_reports_explicit_complete_statement(): assert parse_structured_statement(statement_payloads(status_in_statements=True)[0]).state is ParseState.PARSED
def test_numeric_normalization_comma_and_decimal(): assert normalize_amount("15,000.25")==Decimal("15000.25")
def test_numeric_parentheses_preserve_sign(): assert normalize_amount("(125.50)")==Decimal("-125.50")
def test_invalid_numeric_rejected():
    with pytest.raises(ValueError): normalize_amount("not-money")
def test_month_normalization_year_month(): assert normalize_month("2026-06")=="2026-06"
def test_month_normalization_iso_date(): assert normalize_month("2026-06-30")=="2026-06"
def test_invalid_currency_rejected():
    p=statement_payloads()[0]; p["currency"]="ZZZ"; assert parse_structured_statement(p).state is ParseState.INVALID
def test_masked_account_preserved(): assert parse_structured_statement(statement_payloads()[0]).masked_account_number=="****1234"
def test_full_card_number_rejected():
    p=statement_payloads()[0]; p["masked_account_number"]="4111111111111111"; assert parse_structured_statement(p).state is ParseState.INVALID
def test_provider_normalization(): assert normalize_provider("  Example-Bank, Ltd. ")[1]=="examplebankltd"
def test_statement_balance_extraction_decimal(): assert parse_structured_statement(statement_payloads()[0]).statement_balance.value==Decimal("100")
def test_payment_extraction_decimal(): assert parse_structured_statement(statement_payloads()[0]).payment_amount.value==Decimal("50")
def test_repayment_status_extraction_only_when_explicit(): assert parse_structured_statement(statement_payloads()[0]).repayment_status.state is ValueState.MISSING
def test_severity_preservation_from_statement():
    p=statement_payloads(status_in_statements=True)[3]; assert parse_structured_statement(p).repayment_status.delinquency_level==2
def test_provenance_created_from_document_metadata(): assert parse_structured_statement(statement_payloads()[0]).statement_balance.provenance[0].source_document_id=="stmt-2026-01"
def test_missing_source_link_metadata_does_not_default_trusted():
    p=statement_payloads()[0]; p["source_metadata"].pop("account_link_confidence"); assert parse_structured_statement(p).state is ParseState.INVALID
def test_missing_authentication_metadata_does_not_default_true():
    p=statement_payloads()[0]; p["source_metadata"].pop("authenticated"); assert parse_structured_statement(p).state is ParseState.INVALID
def test_six_month_assembly(): assert len(run().account.monthly_records)==6
def test_account_linkage_on_stable_reference(): assert run().account.account_reference=="fixture-card-001"
def test_supplementary_repayment_linkage():
    out=run(); assert out.account.monthly_records[0].repayment_status.status is RepaymentStatusKind.CURRENT
def test_statement_only_is_partial_and_ineligible():
    out=run(history=[]); assert out.features.values is None and "MISSING_REPAYMENT_STATUS" in out.validation.blockers
def test_statement_plus_history_is_eligible(): assert run().eligibility.eligible_for_phase2b6_scorecard
def test_exact_recent_delinquency_equivalence(): assert run().features.values["recent_delinquency_level"]==3
def test_exact_delinquent_month_count_equivalence(): assert run().features.values["months_with_delinquency"]==3
def test_exact_payment_ratio_equivalence_independent():
    assert sum(PAYMENTS)/sum(max(x,0) for x in BALANCES)==0.5
    assert run().features.values["payment_to_statement_ratio"]==Decimal("0.5")
def test_exact_mean_balance_equivalence_independent():
    assert sum(BALANCES)/6==350
    assert run().features.values["mean_statement_balance"]==Decimal("350")
def test_feature_provenance_traces_latest_status(): assert run().features.provenance["recent_delinquency_level"]["source_record_ids"]==["2026-06"]
def test_feature_provenance_traces_all_six_statuses(): assert set(run().features.provenance["months_with_delinquency"]["source_record_ids"])==set(MONTHS)
def test_feature_provenance_traces_balance_and_payment_months(): assert set(run().features.provenance["payment_to_statement_ratio"]["source_record_ids"])==set(MONTHS)
def test_feature_provenance_traces_all_balances(): assert set(run().features.provenance["mean_statement_balance"]["source_record_ids"])==set(MONTHS)
def test_zero_denominator():
    ps=statement_payloads()
    for p in ps: p["statement_balance"]="0"
    assert run(ps).features.state=="ZERO_DENOMINATOR"
def test_observed_zero_payment_remains_present():
    ps=statement_payloads(); ps[0]["payment_amount"]="0"; assert parse_structured_statement(ps[0]).payment_amount.state is ValueState.PRESENT
def test_missing_payment_remains_missing():
    ps=statement_payloads(); ps[0].pop("payment_amount"); assert run(ps).validation.state=="MISSING_PAYMENT_AMOUNT"
def test_missing_balance_remains_missing():
    ps=statement_payloads(); ps[0].pop("statement_balance"); assert run(ps).validation.state=="MISSING_STATEMENT_BALANCE"
def test_missing_status_fails_closed(): assert run(history=[]).validation.state=="MISSING_REPAYMENT_STATUS"
def test_missing_month_fails_closed(): assert run(statement_payloads()[:-1]).validation.state=="INSUFFICIENT_HISTORY"
def test_duplicate_month_fails_closed():
    ps=statement_payloads(); ps[-1]["statement_month"]="2026-05"; assert run(ps).validation.state=="DUPLICATE_MONTH"
def test_future_month_fails_closed():
    ps=statement_payloads(); ps[-1]["statement_month"]="2026-07"; assert run(ps).validation.state=="FUTURE_OR_PARTIAL_MONTH"
def test_statement_account_mismatch_fails_closed():
    ps=statement_payloads(); ps[-1]["account_reference"]="other-card"; assert run(ps).state=="ACCOUNT_LINK_UNCERTAIN"
def test_month_mismatch_fails_closed():
    hs=repayment_payloads(months=("2025-12",)*6); assert run(history=hs).state=="ACCOUNT_LINK_UNCERTAIN"
def test_conflicting_repayment_evidence_fails_closed():
    ps=statement_payloads(status_in_statements=True); hs=repayment_payloads(levels=(0,0,0,0,0,0)); assert run(ps,hs).validation.state=="CONFLICTING_EVIDENCE"
def test_low_account_link_confidence_fails_closed(): assert run(history=repayment_payloads(confidence=.90)).validation.state=="ACCOUNT_LINK_UNCERTAIN"
def test_missing_provenance_fails_closed():
    out=run(); a=out.account; r=a.monthly_records[0]; bad=replace(r,statement_balance=replace(r.statement_balance,provenance=())); account=replace(a,monthly_records=(bad,)+a.monthly_records[1:]); assert validate_account(account,at=AT).state=="PROVENANCE_INCOMPLETE"
def test_insufficient_consent_fails_closed(): assert run(cons=consent(scopes={SCOPE_CARD_STATEMENTS})).validation.state=="CONSENT_REQUIRED"
def test_withdrawn_consent_fails_closed(): assert run(cons=consent(withdrawn_at=AT)).validation.state=="CONSENT_REQUIRED"
def test_unsupported_product_fails_closed():
    ps=statement_payloads(); hs=repayment_payloads()
    for p in ps: p["product_type"]="PERSONAL_LOAN"
    for h in hs: h["product_type"]="PERSONAL_LOAN"
    assert run(ps,hs).validation.state=="UNSUPPORTED_PRODUCT"
def test_multiple_accounts_parsed_separately_not_aggregated():
    first=run(); ps=statement_payloads(); hs=repayment_payloads()
    for p in ps: p["account_reference"]="fixture-card-002"
    for h in hs: h["account_reference"]="fixture-card-002"
    second=run(ps,hs); assert first.account.account_reference!=second.account.account_reference
def test_no_multi_account_aggregation(): assert "MULTI_ACCOUNT_AGGREGATION_UNRESOLVED" in assess_eligibility(run().account,borrower_account_count=2,at=AT).blocking_reasons
def test_bank_balance_not_substituted():
    ps=statement_payloads(); ps[0].pop("statement_balance"); ps[0]["bank_closing_balance"]="123"; assert run(ps).validation.state=="MISSING_STATEMENT_BALANCE"
def test_generic_bank_debit_not_substituted():
    ps=statement_payloads(); ps[0].pop("payment_amount"); ps[0]["bank_debit"]="50"; assert run(ps).validation.state=="MISSING_PAYMENT_AMOUNT"
def test_payment_does_not_infer_status():
    out=run(history=[]); assert out.account.monthly_records[-1].payment_amount.value>0 and out.account.monthly_records[-1].repayment_status.state is ValueState.MISSING
def test_zero_not_converted_to_missing(): assert parse_structured_statement({**statement_payloads()[0],"payment_amount":"0"}).payment_amount.state is ValueState.PRESENT
def test_missing_not_converted_to_zero():
    ps=statement_payloads(); ps[0].pop("payment_amount"); assert run(ps).features.values is None
def test_missing_not_converted_to_neutral(): assert run(history=[]).eligibility.eligible_for_phase2b6_scorecard is False
def test_controlled_text_parser():
    t=text_statement_payloads()[0]; parsed=parse_controlled_text_statement(t["text"],source_metadata=t["source_metadata"]); assert parsed.statement_month=="2026-01" and parsed.state is ParseState.PARTIALLY_PARSED
def test_controlled_text_six_month_end_to_end(): assert run_equivalence_path(text_statement_payloads(),repayment_payloads(),consent=consent(),prediction_cutoff_month=CUTOFF,borrower_reference=BORROWER,at=AT,text=True).features.values==EXPECTED
def test_no_borrower_identity_inferred_from_document(): assert run_equivalence_path(statement_payloads(),repayment_payloads(),consent=consent(),prediction_cutoff_month=CUTOFF,at=AT).state=="MISSING_REQUIRED_EVIDENCE"
def test_no_production_import_or_integration():
    root=Path(__file__).parents[1]/"credit_parser"; text="\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py")); assert "backend.route" not in text and "scoring.risk_scorer" not in text
def test_phase2e_works_without_production_scorer(): assert run().features.values.keys()==EXPECTED.keys()
def test_protected_baseline_has_phase2d_contract_hashes():
    rows=json.loads((Path(__file__).parents[1]/"outputs"/"phase2e"/"protected_hashes_before.json").read_text(encoding="utf-8")); assert any(r["scope"]=="phase2d_code" for r in rows) and any(r["scope"].endswith("phase2d") for r in rows)
def test_golden_fixture_integrity_hash():
    root=Path(__file__).parents[1]/"outputs"/"phase2e"; fixture=json.loads((root/"golden_fixture.json").read_text(encoding="utf-8")); canonical=json.dumps(fixture,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode(); digest=hashlib.sha256(canonical).hexdigest().upper(); saved=json.loads((root/"golden_fixture_hash.json").read_text(encoding="utf-8"))["sha256"]
    assert digest==saved=="F03B320882A39415B1A8966BD990A6C05C78172C5158E53B65EFB065FD6E58BE"
def test_protected_after_matches_before():
    root=Path(__file__).parents[1]/"outputs"/"phase2e"; before=json.loads((root/"protected_hashes_before.json").read_text(encoding="utf-8")); after=json.loads((root/"protected_hashes_after.json").read_text(encoding="utf-8")); assert len(before)==len(after) and all(x["unchanged"] and x["sha256"]==x["actual_sha256"] for x in after)
def test_production_hashes_unchanged():
    root=Path(__file__).parents[1]/"outputs"/"phase2e"; after=json.loads((root/"protected_hashes_after.json").read_text(encoding="utf-8")); assert all(x["unchanged"] for x in after if x["scope"]=="backend/scoring/artifacts")
def test_phase2b6_hashes_unchanged():
    root=Path(__file__).parents[1]/"outputs"/"phase2e"; after=json.loads((root/"protected_hashes_after.json").read_text(encoding="utf-8")); assert all(x["unchanged"] for x in after if x["scope"]=="backend/phase2/outputs/phase2b6")
def test_phase2c_hashes_unchanged():
    root=Path(__file__).parents[1]/"outputs"/"phase2e"; after=json.loads((root/"protected_hashes_after.json").read_text(encoding="utf-8")); assert all(x["unchanged"] for x in after if x["scope"]=="backend/phase2/outputs/phase2c")
def test_phase2d_hashes_unchanged():
    root=Path(__file__).parents[1]/"outputs"/"phase2e"; after=json.loads((root/"protected_hashes_after.json").read_text(encoding="utf-8")); assert all(x["unchanged"] for x in after if x["scope"] in {"backend/phase2/outputs/phase2d","phase2d_code","phase2d_tests"})
