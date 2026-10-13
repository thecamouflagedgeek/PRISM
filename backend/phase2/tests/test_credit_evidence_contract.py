from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
import hashlib
from pathlib import Path
import pytest
from phase2.credit_evidence.models import *
from phase2.credit_evidence.fixtures import base_account, AT, p, ev, status, fixture_catalog, controlled_scenarios
from phase2.credit_evidence.feature_adapter import compute_features
from phase2.credit_evidence.validation import validate_account, expected_months
from phase2.credit_evidence.eligibility import assess_eligibility
from phase2.credit_evidence.consent import SCOPE_CARD_STATEMENTS

def test_schema_validates_and_is_typed(): assert isinstance(base_account(),CreditAccountEvidence)
def test_identity_requires_masked_identifier():
    with pytest.raises(ValueError): replace(base_account(),masked_account_number="1234567890123456")
def test_product_enum_is_explicit(): assert {p.value for p in ProductType}=={"CREDIT_CARD","PERSONAL_LOAN","HOME_LOAN","AUTO_LOAN","OTHER_CREDIT"}
def test_expected_month_window(): assert expected_months("2025-10")==("2025-04","2025-05","2025-06","2025-07","2025-08","2025-09")
def test_exact_six_required(): assert "EXACTLY_SIX_MONTHS_REQUIRED" in validate_account(replace(base_account(),monthly_records=base_account().monthly_records[:5]),at=AT).blockers
def test_six_month_continuity_valid(): assert validate_account(base_account(),at=AT).valid
def test_duplicate_month_rejected():
    a=base_account(); rs=a.monthly_records; assert "DUPLICATE_MONTH" in validate_account(replace(a,monthly_records=rs[:-1]+(replace(rs[-1],statement_month=rs[-2].statement_month),)),at=AT).blockers
def test_missing_middle_month_rejected():
    a=base_account(); rs=a.monthly_records; assert "MONTH_WINDOW_OR_CONTINUITY_INVALID" in validate_account(replace(a,monthly_records=rs[:2]+rs[3:]),at=AT).blockers
def test_future_period_rejected():
    a=base_account(); rs=a.monthly_records; assert "FUTURE_OR_PARTIAL_MONTH" in validate_account(replace(a,monthly_records=rs[:-1]+(replace(rs[-1],statement_month="2025-10"),)),at=AT).blockers
def test_zero_balance_is_valid_observed_zero(): assert ev("balance",0,"2025-04").value==Decimal(0)
def test_missing_balance_is_not_zero(): assert EvidenceValue(ValueState.MISSING).value is None
def test_zero_payment_is_valid(): assert ev("payment",0,"2025-04").state is ValueState.PRESENT
def test_missing_payment_blocks():
    a=base_account(); rs=a.monthly_records; r=replace(rs[0],payment_amount=EvidenceValue(ValueState.MISSING)); assert "MISSING_PAYMENT_AMOUNT" in validate_account(replace(a,monthly_records=(r,)+rs[1:]),at=AT).blockers
def test_missing_repayment_status_blocks():
    a=base_account(); rs=a.monthly_records; r=replace(rs[0],repayment_status=RepaymentStatus(ValueState.MISSING)); assert "MISSING_REPAYMENT_STATUS" in validate_account(replace(a,monthly_records=(r,)+rs[1:]),at=AT).blockers
def test_not_applicable_repayment_status_does_not_become_current():
    a=base_account(); rs=a.monthly_records; r=replace(rs[0],repayment_status=RepaymentStatus(ValueState.NOT_APPLICABLE)); assert "NOT_APPLICABLE_REPAYMENT_STATUS" in validate_account(replace(a,monthly_records=(r,)+rs[1:]),at=AT).blockers
def test_delinquency_severity_preserved(): assert status("2025-09",7).delinquency_level==7
def test_severity_upper_bound():
    with pytest.raises(ValueError): RepaymentStatus(ValueState.PRESENT,RepaymentStatusKind.DELINQUENT,10)
def test_account_mismatch_blocks():
    a=base_account(); rs=a.monthly_records; assert "ACCOUNT_MISMATCH" in validate_account(replace(a,monthly_records=(replace(rs[0],account_reference="acct-B"),)+rs[1:]),at=AT).blockers
def test_multiple_account_objects_remain_separate(): assert base_account().account_reference!="acct-B"
def test_multiple_account_aggregation_unresolved(): assert "MULTI_ACCOUNT_AGGREGATION_UNRESOLVED" in assess_eligibility(base_account(),borrower_account_count=2,at=AT).blocking_reasons
def test_unsupported_product_blocks(): assert "UNSUPPORTED_PRODUCT" in validate_account(replace(base_account(),product_type=ProductType.PERSONAL_LOAN),at=AT).blockers
def test_missing_distinct_from_zero(): assert (EvidenceValue(ValueState.MISSING).state,ev("x",0,"2025-04").state)==(ValueState.MISSING,ValueState.PRESENT)
def test_not_applicable_distinct_from_missing(): assert ValueState.NOT_APPLICABLE is not ValueState.MISSING
def test_conflict_blocks(): assert "CONFLICTING_EVIDENCE" in validate_account(replace(base_account(),conflicts=("balance mismatch",)),at=AT).blockers
def test_field_provenance_required():
    a=base_account(); rs=a.monthly_records; r=replace(rs[0],statement_balance=EvidenceValue(ValueState.PRESENT,Decimal(1),"USD")); assert "PROVENANCE_INCOMPLETE" in validate_account(replace(a,monthly_records=(r,)+rs[1:]),at=AT).blockers
def test_derived_provenance_traces_inputs():
    result=compute_features(base_account(),at=AT); assert set(result.provenance["payment_to_statement_ratio"]["input_fields"])=={"payment_amount","statement_balance"}
def test_derived_recent_feature_traces_only_recent_source_record():
    result=compute_features(base_account(),at=AT); assert result.provenance["recent_delinquency_level"]["source_record_ids"]==["2025-09"]
def test_consent_granted_allows(): assert validate_account(base_account(),at=AT).valid
def test_consent_absent_blocks(): assert "CONSENT_REQUIRED" in validate_account(replace(base_account(),consent=Consent(ConsentState.UNKNOWN)),at=AT).blockers
def test_consent_withdrawn_blocks():
    a=base_account(); c=replace(a.consent,withdrawn_at=AT); assert "CONSENT_REQUIRED" in validate_account(replace(a,consent=c),at=AT).blockers
def test_consent_wrong_scope_blocks():
    a=base_account(); c=replace(a.consent,scopes=frozenset({"BANK_TRANSACTION_CROSS_CHECK"})); assert "CONSENT_REQUIRED" in validate_account(replace(a,consent=c),at=AT).blockers
def test_payment_statement_month_alignment():
    a=base_account(); result=compute_features(a,at=AT); assert result.values["payment_to_statement_ratio"]==sum(r.payment_amount.value for r in a.monthly_records)/sum(max(r.statement_balance.value,0) for r in a.monthly_records)
def test_feature_recent_is_latest_month():
    a=base_account(); rs=a.monthly_records; rs=rs[:-1]+(replace(rs[-1],repayment_status=status("2025-09",3)),); assert compute_features(replace(a,monthly_records=rs),at=AT).values["recent_delinquency_level"]==3
def test_feature_months_with_delinquency():
    a=base_account(); rs=list(a.monthly_records); rs[1]=replace(rs[1],repayment_status=status("2025-05",2)); rs[4]=replace(rs[4],repayment_status=status("2025-08",1)); assert compute_features(replace(a,monthly_records=tuple(rs)),at=AT).values["months_with_delinquency"]==2
def test_zero_denominator_explicit_state():
    a=base_account(); rs=tuple(replace(r,statement_balance=ev("statement_balance",0,r.statement_month)) for r in a.monthly_records); assert compute_features(replace(a,monthly_records=rs),at=AT).state=="ZERO_DENOMINATOR"
def test_no_missing_to_zero_behavior():
    a=base_account(); rs=a.monthly_records; r=replace(rs[0],payment_amount=EvidenceValue(ValueState.MISSING)); assert compute_features(replace(a,monthly_records=(r,)+rs[1:]),at=AT).values is None
def test_no_missing_to_neutral_behavior(): assert compute_features(replace(base_account(),consent=Consent(ConsentState.UNKNOWN)),at=AT).values is None
def test_bank_balance_cannot_substitute_statement_balance():
    a=base_account(); r=a.monthly_records[0]; fake=Provenance("bank",SourceType.BANK_CROSS_CHECK,"closing_balance","parser",1,"identity",100,100); bad=replace(r,statement_balance=EvidenceValue(ValueState.PRESENT,Decimal(100),"USD",(fake,))); assert "INVALID_EVIDENCE_SEMANTICS" in validate_account(replace(a,monthly_records=(bad,)+a.monthly_records[1:]),at=AT).blockers
def test_utility_delay_cannot_substitute_credit_delinquency():
    a=base_account(); r=a.monthly_records[0]; fake=Provenance("utility",SourceType.STRUCTURED_ACCOUNT_HISTORY,"utility_late","extractor",1,"map",1,1); bad=replace(r,repayment_status=RepaymentStatus(ValueState.PRESENT,RepaymentStatusKind.DELINQUENT,1,provenance=(fake,))); assert "INVALID_STATUS_SOURCE" in validate_account(replace(a,monthly_records=(bad,)+a.monthly_records[1:]),at=AT).blockers
def test_generic_bank_debit_not_payment_source():
    a=base_account(); r=a.monthly_records[0]; fake=Provenance("bank",SourceType.BANK_CROSS_CHECK,"debit","extractor",1,"identity",10,10); bad=replace(r,payment_amount=EvidenceValue(ValueState.PRESENT,Decimal(10),"USD",(fake,))); assert "INVALID_EVIDENCE_SEMANTICS" in validate_account(replace(a,monthly_records=(bad,)+a.monthly_records[1:]),at=AT).blockers
def test_model_boundary_remains_inconclusive(): assert "PHASE_2B6_INCONCLUSIVE_EXTERNAL_VALIDATION_ABSENT" in assess_eligibility(base_account(),at=AT).warnings
def test_fixture_catalog_has_18_cases(): assert len(fixture_catalog())==18
@pytest.mark.parametrize("scenario",list(controlled_scenarios()))
def test_controlled_fixture_scenario(scenario):
    account,expected=controlled_scenarios()[scenario]
    if isinstance(account,CreditFacilityApplicabilityEvidence):
        assert account.state is FacilityApplicability.NOT_APPLICABLE
        assert expected=="NOT_APPLICABLE"
        return
    result=compute_features(account,at=AT)
    assert result.state==expected, scenario
def test_protected_hash_snapshot_exists(): assert (Path(__file__).parents[1]/"credit_evidence"/"protected_hashes_before.json").exists()
def test_production_and_phase2b6_hashes_unchanged():
    repo=Path(__file__).parents[3]; rows=json.loads((Path(__file__).parents[1]/"credit_evidence"/"protected_hashes_before.json").read_text(encoding="utf-8"))
    assert rows
    assert all((repo/Path(row["relative_path"])).is_file() and hashlib.sha256((repo/Path(row["relative_path"])).read_bytes()).hexdigest().upper()==row["sha256"] for row in rows)
def test_contract_source_has_no_production_imports():
    root=Path(__file__).parents[1]/"credit_evidence"
    assert not any("backend.scoring" in p.read_text(encoding="utf-8") for p in root.glob("*.py"))
