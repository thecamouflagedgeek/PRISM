"""Account join and six-month assembly bridge into the frozen Phase 2D contract."""
from dataclasses import replace
from datetime import datetime
from .models import AssemblyResult, ParseState
from ..credit_evidence.models import (CreditMonthlyRecord,CreditAccountEvidence,ValueState,
    RepaymentStatus,RepaymentStatusKind,ProductType,SourceType,SourceRole)
from ..credit_evidence.validation import validate_account
from ..credit_evidence.eligibility import assess_eligibility
from ..credit_evidence.feature_adapter import compute_features
from ..credit_evidence.provenance import derived_provenance
from ..credit_evidence.consent import SCOPE_CARD_STATEMENTS,SCOPE_BUREAU_HISTORY

def assemble_credit_account(statements, repayment_records=(), *, consent, prediction_cutoff_month, borrower_reference=None, at=None):
    """Join normalized monthly statement + explicit repayment rows; never merge accounts."""
    statements=tuple(statements); repayment_records=tuple(repayment_records); at=at or datetime.now().astimezone()
    issues=[]
    if not statements: return AssemblyResult("MISSING_REQUIRED_EVIDENCE",None,None,None,None,("NO_STATEMENT_RECORDS",))
    if not borrower_reference: return AssemblyResult("MISSING_REQUIRED_EVIDENCE",None,None,None,None,("PSEUDONYMOUS_BORROWER_REFERENCE_REQUIRED",))
    if any(s.state is ParseState.UNSUPPORTED for s in statements) or any(r.state is ParseState.UNSUPPORTED for r in repayment_records):
        return AssemblyResult("UNSUPPORTED",None,None,None,None,("UNSUPPORTED_SOURCE_FORMAT",))
    anchor=statements[0]
    if not anchor.account_reference or not anchor.provider_key or anchor.product_type is None:
        return AssemblyResult("ACCOUNT_LINK_UNCERTAIN",None,None,None,None,("ANCHOR_IDENTITY_UNRESOLVED",))
    if any(s.currency is None for s in statements):
        return AssemblyResult("INVALID_EVIDENCE",None,None,None,None,("INVALID_CURRENCY",))
    for s in statements:
        if s.account_reference!=anchor.account_reference or s.provider_key!=anchor.provider_key or s.product_type is not anchor.product_type or s.masked_account_number!=anchor.masked_account_number:
            return AssemblyResult("ACCOUNT_LINK_UNCERTAIN",None,None,None,None,("STATEMENT_ACCOUNT_IDENTITY_MISMATCH",))
    for r in repayment_records:
        if r.account_reference!=anchor.account_reference or r.provider_key!=anchor.provider_key or r.product_type is not anchor.product_type:
            return AssemblyResult("ACCOUNT_LINK_UNCERTAIN",None,None,None,None,("REPAYMENT_ACCOUNT_IDENTITY_MISMATCH",))
    if repayment_records and not any(s.statement_month==r.month for s in statements for r in repayment_records):
        issues.append("REPAYMENT_MONTH_MISMATCH")
    by_month={}
    for r in repayment_records: by_month.setdefault(r.month,[]).append(r)
    months=[s.statement_month for s in statements]
    all_sources=tuple(s.source for s in statements if s.source is not None)+tuple(r.source for r in repayment_records if r.source is not None)
    source_byid={s.source_document_id:s for s in all_sources}
    monthly=[]
    for stmt in statements:
        linked=by_month.get(stmt.statement_month,[])
        if len(linked)>1: issues.append(f"DUPLICATE_REPAYMENT_MONTH:{stmt.statement_month}")
        bureau=linked[0] if linked else None
        statement_status=stmt.repayment_status
        conflict=False
        if bureau is not None and statement_status.state is ValueState.PRESENT and bureau.repayment_status.state is ValueState.PRESENT:
            a=(statement_status.status,statement_status.delinquency_level); b=(bureau.repayment_status.status,bureau.repayment_status.delinquency_level)
            if a!=b:
                conflict=True; repayment=RepaymentStatus(ValueState.CONFLICTING)
            else: repayment=statement_status
        elif statement_status.state is ValueState.PRESENT: repayment=statement_status
        elif bureau is not None: repayment=bureau.repayment_status
        else: repayment=RepaymentStatus(ValueState.MISSING)
        ids=tuple(x for x in (stmt.source.source_document_id if stmt.source else None,bureau.source.source_document_id if bureau and bureau.source else None) if x)
        monthly.append(CreditMonthlyRecord(stmt.statement_month,stmt.statement_balance,stmt.payment_amount,repayment,
            stmt.account_reference or anchor.account_reference,ids,unresolved_conflict=conflict))
    # Keep only one source per document id, preserving all distinct statement/history source records.
    sources=tuple(source_byid.values())
    evidence=CreditAccountEvidence(
        borrower_reference=str(borrower_reference),
        account_reference=anchor.account_reference,product_type=anchor.product_type,provider_name=anchor.provider_name or "UNKNOWN",
        masked_account_number=anchor.masked_account_number or "TOKEN-UNRESOLVED",currency=anchor.currency or "USD",
        account_state="UNKNOWN",prediction_cutoff_month=prediction_cutoff_month,monthly_records=tuple(monthly),evidence_sources=sources,
        consent=consent,coverage_start_month=min(months) if months else None,coverage_end_month_exclusive=prediction_cutoff_month,
        conflicts=("STATEMENT_REPAYMENT_CONFLICT",) if any(r.unresolved_conflict for r in monthly) else ())
    validation=validate_account(evidence,at=at)
    eligibility=assess_eligibility(evidence,borrower_account_count=1,at=at)
    features=compute_features(evidence,at=at)
    if features.state!="COMPUTABLE" and eligibility.eligible_for_phase2b6_scorecard:
        eligibility=replace(eligibility,eligible_for_phase2b6_scorecard=False,blocking_reasons=tuple(dict.fromkeys(eligibility.blocking_reasons+features.blockers)))
    state="ACCOUNT_LINK_UNCERTAIN" if issues and any("MISMATCH" in i for i in issues) else features.state if validation.valid and features.state!="COMPUTABLE" else validation.state
    return AssemblyResult(state,evidence,validation,eligibility,features,tuple(issues))

def run_equivalence_path(statement_payloads, repayment_payloads=(), *, consent, prediction_cutoff_month, borrower_reference=None, at=None, text=False):
    """Real parser→normalizer→Phase 2D validator→eligibility→feature adapter path."""
    from .parser import parse_structured_statement, parse_controlled_text_statement, parse_repayment_history
    parse_statement=parse_controlled_text_statement if text else parse_structured_statement
    statements=tuple(parse_statement(p["text"],source_metadata=p["source_metadata"]) if text else parse_statement(p) for p in statement_payloads)
    repayment=tuple(parse_repayment_history(p) for p in repayment_payloads)
    return assemble_credit_account(statements,repayment,consent=consent,prediction_cutoff_month=prediction_cutoff_month,borrower_reference=borrower_reference,at=at)
