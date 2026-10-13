"""Synthetic source fixtures for deterministic parser/equivalence tests only."""
from datetime import datetime,timezone
from ..credit_evidence.models import Consent,ConsentState
from ..credit_evidence.consent import SCOPE_CARD_STATEMENTS,SCOPE_BUREAU_HISTORY

CUTOFF="2026-07"
AT=datetime(2026,7,1,tzinfo=timezone.utc)
ACCOUNT="fixture-card-001"
BORROWER="synthetic-borrower-001"
PROVIDER="Example Bank"
MASKED="****1234"
MONTHS=("2026-01","2026-02","2026-03","2026-04","2026-05","2026-06")
BALANCES=(100,200,300,400,500,600)
PAYMENTS=(50,100,150,200,250,300)
LEVELS=(0,1,0,2,0,3)

def consent(*,withdrawn_at=None,scopes=None):
    return Consent(ConsentState.GRANTED,frozenset(scopes or {SCOPE_CARD_STATEMENTS,SCOPE_BUREAU_HISTORY}),datetime(2026,1,1,tzinfo=timezone.utc),withdrawn_at=withdrawn_at,version="synthetic-phase2e-v1")

def source_metadata(docid, *, confidence=1.0, link=1.0, authenticated=True):
    return {"source_document_id":docid,"extraction_method":"controlled_fixture_fields","extraction_confidence":confidence,"account_link_confidence":link,"authenticated":authenticated}

def statement_payloads(*,status_in_statements=False):
    rows=[]
    for i,month in enumerate(MONTHS):
        row={"account_reference":ACCOUNT,"product_type":"CREDIT_CARD","provider":PROVIDER,"masked_account_number":MASKED,"currency":"USD","statement_month":month,"statement_balance":str(BALANCES[i]),"payment_amount":str(PAYMENTS[i]),"source_metadata":source_metadata(f"stmt-{month}")}
        if status_in_statements:
            s=LEVELS[i]; row["repayment_status"]={"status":"DELINQUENT" if s else "CURRENT","delinquency_severity":s,"source_code":f"fixture:{s}"}
        rows.append(row)
    return rows

def repayment_payloads(*,account=ACCOUNT,provider=PROVIDER,months=MONTHS,levels=LEVELS,confidence=1.0):
    rows=[]
    for i,month in enumerate(months):
        level=levels[i] if i<len(levels) else 0
        rows.append({"account_reference":account,"product_type":"CREDIT_CARD","provider":provider,"month":month,"repayment_status":"DELINQUENT" if level else "CURRENT","delinquency_severity":level,"source_code":f"bureau-fixture:{level}","source_metadata":source_metadata(f"repay-{month}",confidence=confidence,link=confidence)})
    return rows

def text_statement_payloads():
    out=[]
    for i,month in enumerate(MONTHS):
        text=(f"STATEMENT MONTH: {month}\nACCOUNT REFERENCE: {ACCOUNT}\nPROVIDER: {PROVIDER}\nACCOUNT: {MASKED}\nCURRENCY: USD\nSTATEMENT BALANCE: {BALANCES[i]:,}.00\nPAYMENT RECEIVED: {PAYMENTS[i]:,}.00\n")
        out.append({"text":text,"source_metadata":source_metadata(f"text-stmt-{month}")})
    return out
