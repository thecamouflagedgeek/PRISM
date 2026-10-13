"""Synthetic contract-validation fixtures; never used for model fitting."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from .models import *
from .consent import SCOPE_CARD_STATEMENTS

AT=datetime(2026,1,1,tzinfo=timezone.utc)
def p(field,value,src="card-doc",record_id=None):
    return Provenance(src,SourceType.CREDIT_CARD_STATEMENT,field,"synthetic_fixture",1.0,"identity",value,value,page_or_record_id=record_id or field)
def ev(field,value,month):
    return EvidenceValue(ValueState.PRESENT,Decimal(str(value)),"USD",(p(field,value,record_id=month),))
def status(month, level=0):
    kind=RepaymentStatusKind.DELINQUENT if level>0 else RepaymentStatusKind.CURRENT
    return RepaymentStatus(ValueState.PRESENT,kind,level,source_code=f"fixture:{level}",provenance=(p("repayment_status",level,record_id=month),))
def base_account():
    months=[f"2025-{m:02}" for m in range(4,10)]
    records=tuple(CreditMonthlyRecord(m,ev("statement_balance",100+i,m),ev("payment_amount",50,m),status(m),"acct-A",("card-doc",)) for i,m in enumerate(months))
    source=EvidenceSource("card-doc",SourceType.CREDIT_CARD_STATEMENT,SourceRole.PRIMARY_ACCOUNT_SOURCE,"acct-A",1.0,True,tuple(months))
    consent=Consent(ConsentState.GRANTED,frozenset({SCOPE_CARD_STATEMENTS}),AT.replace(year=2025),version="fixture-v1")
    return CreditAccountEvidence("borrower-X","acct-A",ProductType.CREDIT_CARD,"Example Bank","****-****-****-1234","USD","ACTIVE","2025-10",records,(source,),consent,"2025-04","2025-10")

def controlled_scenarios():
    """Return the requested 18 synthetic negative/positive scenarios."""
    a=base_account(); rs=a.monthly_records
    def record(i, **kw): return replace(rs[i],**kw)
    def account(records=rs, **kw): return replace(a,monthly_records=tuple(records),**kw)
    zero_bal=tuple(replace(r,statement_balance=ev("statement_balance",0,r.statement_month)) for r in rs)
    missingpay=tuple(record(i,payment_amount=EvidenceValue(ValueState.MISSING)) if i==0 else r for i,r in enumerate(rs))
    missingstatus=tuple(record(i,repayment_status=RepaymentStatus(ValueState.MISSING)) if i==0 else r for i,r in enumerate(rs))
    conflict=account(conflicts=("unresolved competing balance evidence",))
    no_consent=account(consent=Consent(ConsentState.NOT_GRANTED))
    withdrawn=account(consent=replace(a.consent,withdrawn_at=AT))
    mismatch=account(records=(record(0,account_reference="acct-B"),)+rs[1:])
    not_applicable=CreditFacilityApplicabilityEvidence("borrower-X",FacilityApplicability.NOT_APPLICABLE,AT,(p("facility_search_result","no_applicable_credit_facility",record_id="verified-registry-response"),))
    loan=account(product_type=ProductType.PERSONAL_LOAN)
    no_prov=account(records=(record(0,statement_balance=EvidenceValue(ValueState.PRESENT,Decimal("100"),"USD")),)+rs[1:])
    duplicate=account(records=rs[:-1]+(record(5,statement_month=rs[4].statement_month),))
    missing_month=account(records=rs[:2]+rs[3:])
    future=account(records=rs[:-1]+(record(5,statement_month="2025-10"),))
    partial=tuple(record(i,payment_amount=ev("payment_amount",25,r.statement_month)) if i==0 else r for i,r in enumerate(rs))
    zero_payment=tuple(record(i,payment_amount=ev("payment_amount",0,r.statement_month)) if i==0 else r for i,r in enumerate(rs))
    recent=tuple(record(i,repayment_status=status(r.statement_month,2)) if i==5 else r for i,r in enumerate(rs))
    multi=tuple(record(i,repayment_status=status(r.statement_month,1)) if i in (1,4) else r for i,r in enumerate(rs))
    return {
      "six_complete_all_current":(a,"COMPUTABLE"),
      "recent_delinquency":(account(records=recent),"COMPUTABLE"),
      "multiple_delinquent_months":(account(records=multi),"COMPUTABLE"),
      "partial_payments":(account(records=partial),"COMPUTABLE"),
      "zero_statement_balance":(account(records=zero_bal),"ZERO_DENOMINATOR"),
      "observed_zero_payment":(account(records=zero_payment),"COMPUTABLE"),
      "missing_payment":(account(records=missingpay),"MISSING_PAYMENT_AMOUNT"),
      "missing_repayment_status":(account(records=missingstatus),"MISSING_REPAYMENT_STATUS"),
      "missing_middle_month":(missing_month,"INSUFFICIENT_HISTORY"),
      "duplicate_month":(duplicate,"DUPLICATE_MONTH"),
      "future_month":(future,"FUTURE_OR_PARTIAL_MONTH"),
      "conflicting_evidence":(conflict,"CONFLICTING_EVIDENCE"),
      "insufficient_consent":(no_consent,"CONSENT_REQUIRED"),
      "withdrawn_consent":(withdrawn,"CONSENT_REQUIRED"),
      "mixed_accounts":(mismatch,"ACCOUNT_LINK_UNCERTAIN"),
      "verified_no_applicable_credit_facility":(not_applicable,"NOT_APPLICABLE"),
      "unsupported_loan_product":(loan,"UNSUPPORTED_PRODUCT"),
      "incomplete_provenance":(no_prov,"PROVENANCE_INCOMPLETE"),
    }

def fixture_catalog():
    return [
      {"id":1,"name":"six complete months all current","expected":"COMPUTABLE"},
      {"id":2,"name":"recent delinquency","expected":"COMPUTABLE"},
      {"id":3,"name":"multiple delinquent months","expected":"COMPUTABLE"},
      {"id":4,"name":"partial payments","expected":"COMPUTABLE"},
      {"id":5,"name":"zero statement balance","expected":"ZERO_DENOMINATOR"},
      {"id":6,"name":"observed zero payment","expected":"COMPUTABLE"},
      {"id":7,"name":"missing payment","expected":"MISSING_PAYMENT_AMOUNT"},
      {"id":8,"name":"missing repayment status","expected":"MISSING_REPAYMENT_STATUS"},
      {"id":9,"name":"missing middle month","expected":"INSUFFICIENT_HISTORY"},
      {"id":10,"name":"duplicate month","expected":"DUPLICATE_MONTH"},
      {"id":11,"name":"future month","expected":"FUTURE_OR_PARTIAL_MONTH"},
      {"id":12,"name":"conflicting evidence","expected":"CONFLICTING_EVIDENCE"},
      {"id":13,"name":"insufficient consent","expected":"CONSENT_REQUIRED"},
      {"id":14,"name":"withdrawn consent","expected":"CONSENT_REQUIRED"},
      {"id":15,"name":"two mixed account ids","expected":"ACCOUNT_LINK_UNCERTAIN"},
      {"id":16,"name":"verified no applicable facility","expected":"NOT_APPLICABLE"},
      {"id":17,"name":"unsupported loan product","expected":"UNSUPPORTED_PRODUCT"},
      {"id":18,"name":"incomplete provenance","expected":"PROVENANCE_INCOMPLETE"},
    ]
