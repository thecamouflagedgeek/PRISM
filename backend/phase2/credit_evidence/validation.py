"""Deterministic gates for six complete, account-linked, consented months."""
from dataclasses import dataclass
from datetime import datetime, timezone
from .models import (CreditAccountEvidence, ValueState, RepaymentStatusKind,
                     ProductType, SourceRole)
from .provenance import value_provenance_complete, status_provenance_complete
from .consent import SCOPE_CARD_STATEMENTS, SCOPE_LOAN_HISTORY, SCOPE_BUREAU_HISTORY

@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    state: str
    blockers: tuple[str, ...]
    months: tuple[str, ...]

def _prev(month: str, n: int=1) -> str:
    y,m=map(int,month.split('-')); z=y*12+m-1-n
    return f"{z//12:04d}-{z%12+1:02d}"

def expected_months(cutoff_month: str) -> tuple[str, ...]:
    # Six complete calendar months immediately before exclusive cutoff month.
    return tuple(_prev(cutoff_month, n) for n in range(6,0,-1))

def validate_account(account: CreditAccountEvidence, *, at: datetime | None=None) -> ValidationResult:
    at = at or datetime.now(timezone.utc)
    blockers=[]; expected=expected_months(account.prediction_cutoff_month)
    sources={s.source_document_id:s for s in account.evidence_sources}
    required_scope = SCOPE_CARD_STATEMENTS if account.product_type is ProductType.CREDIT_CARD else SCOPE_LOAN_HISTORY
    if not account.consent.permits(required_scope, at): blockers.append("CONSENT_REQUIRED")
    if account.product_type is not ProductType.CREDIT_CARD: blockers.append("UNSUPPORTED_PRODUCT")
    if not account.account_reference or not account.masked_account_number: blockers.append("ACCOUNT_IDENTITY_MISSING")
    months=tuple(r.statement_month for r in account.monthly_records)
    if len(months)!=6: blockers.append("EXACTLY_SIX_MONTHS_REQUIRED")
    if len(set(months))!=len(months): blockers.append("DUPLICATE_MONTH")
    if tuple(sorted(months)) != expected: blockers.append("MONTH_WINDOW_OR_CONTINUITY_INVALID")
    if any(m >= account.prediction_cutoff_month for m in months): blockers.append("FUTURE_OR_PARTIAL_MONTH")
    if account.coverage_start_month and account.coverage_start_month > expected[0]: blockers.append("INCOMPLETE_OBSERVABLE_COVERAGE")
    if account.coverage_end_month_exclusive and account.coverage_end_month_exclusive < account.prediction_cutoff_month: blockers.append("INCOMPLETE_OBSERVABLE_COVERAGE")
    if account.conflicts: blockers.append("CONFLICTING_EVIDENCE")
    for r in account.monthly_records:
        if r.account_reference != account.account_reference: blockers.append("ACCOUNT_MISMATCH")
        if r.unresolved_conflict: blockers.append("CONFLICTING_EVIDENCE")
        for f,v in (("statement_balance",r.statement_balance),("payment_amount",r.payment_amount)):
            if v.state is ValueState.MISSING: blockers.append(f"MISSING_{f.upper()}")
            elif v.state is ValueState.NOT_APPLICABLE: blockers.append(f"NOT_APPLICABLE_{f.upper()}")
            elif v.state is ValueState.INVALID: blockers.append("INVALID_EVIDENCE")
            elif v.state is ValueState.CONFLICTING: blockers.append("CONFLICTING_EVIDENCE")
            if v.state is ValueState.PRESENT:
                if v.currency != account.currency: blockers.append("CURRENCY_MISMATCH")
                if not value_provenance_complete(v): blockers.append("PROVENANCE_INCOMPLETE")
                allowed = {"CREDIT_CARD_STATEMENT", "LOAN_STATEMENT", "BUREAU_HISTORY", "LENDER_HISTORY", "STRUCTURED_ACCOUNT_HISTORY"}
                if any(p.source_type.name not in allowed or p.source_field.lower() in {"closing_balance","bank_balance","debit","utility_late","utility_delay"} for p in v.provenance): blockers.append("INVALID_EVIDENCE_SEMANTICS")
                for p in v.provenance:
                    src=sources.get(p.source_document_id)
                    if src is None or src.account_reference != account.account_reference or not src.authenticated or src.account_link_confidence < .95: blockers.append("ACCOUNT_LINK_UNCERTAIN")
                if v.value is not None and v.value < 0 and f=="payment_amount": blockers.append("INVALID_NEGATIVE_PAYMENT")
        s=r.repayment_status
        if s.state is ValueState.MISSING or (s.state is ValueState.PRESENT and s.status is RepaymentStatusKind.UNKNOWN): blockers.append("MISSING_REPAYMENT_STATUS")
        elif s.state is ValueState.NOT_APPLICABLE or (s.state is ValueState.PRESENT and s.status is RepaymentStatusKind.NOT_APPLICABLE): blockers.append("NOT_APPLICABLE_REPAYMENT_STATUS")
        elif s.state is ValueState.INVALID: blockers.append("INVALID_EVIDENCE")
        elif s.state is ValueState.CONFLICTING: blockers.append("CONFLICTING_EVIDENCE")
        elif not status_provenance_complete(s): blockers.append("PROVENANCE_INCOMPLETE")
        if any(p.source_field.lower() in {"utility_late","utility_delay","bank_debit","debit"} for p in s.provenance): blockers.append("INVALID_STATUS_SOURCE")
        for p in s.provenance:
            src=sources.get(p.source_document_id)
            if src is None or src.account_reference != account.account_reference or not src.authenticated or src.account_link_confidence < .95: blockers.append("ACCOUNT_LINK_UNCERTAIN")
            if p.source_type.name=="BUREAU_HISTORY" and not account.consent.permits(SCOPE_BUREAU_HISTORY,at): blockers.append("CONSENT_REQUIRED")
        if s.delinquency_level is None and s.status in (RepaymentStatusKind.CURRENT,RepaymentStatusKind.NO_PAYMENT_DUE): blockers.append("DELINQUENCY_SEVERITY_MISSING")
        if s.status is RepaymentStatusKind.DELINQUENT and s.delinquency_level is not None and s.delinquency_level <= 0: blockers.append("INVALID_DELINQUENCY_SEVERITY")
        for sid in r.source_document_ids:
            src=sources.get(sid)
            if src is None or src.account_reference != account.account_reference or src.account_link_confidence < .95 or not src.authenticated: blockers.append("ACCOUNT_LINK_UNCERTAIN")
            elif src.role not in (SourceRole.PRIMARY_ACCOUNT_SOURCE, SourceRole.SUPPORTING_SOURCE): blockers.append("NON_AUTHORITATIVE_SOURCE")
    # status must come from product-specific credit evidence, not a bank/utility proxy.
    for r in account.monthly_records:
        for p in r.repayment_status.provenance:
            if p.source_type.name in ("BANK_CROSS_CHECK",): blockers.append("INVALID_STATUS_SOURCE")
    blockers=tuple(dict.fromkeys(blockers))
    if "UNSUPPORTED_PRODUCT" in blockers: state="UNSUPPORTED_PRODUCT"
    elif "CONSENT_REQUIRED" in blockers: state="CONSENT_REQUIRED"
    elif "FUTURE_OR_PARTIAL_MONTH" in blockers: state="FUTURE_OR_PARTIAL_MONTH"
    elif "CONFLICTING_EVIDENCE" in blockers: state="CONFLICTING_EVIDENCE"
    elif "DUPLICATE_MONTH" in blockers: state="DUPLICATE_MONTH"
    elif "ACCOUNT_MISMATCH" in blockers or "ACCOUNT_LINK_UNCERTAIN" in blockers: state="ACCOUNT_LINK_UNCERTAIN"
    elif "INVALID_EVIDENCE" in blockers or "INVALID_EVIDENCE_SEMANTICS" in blockers: state="INVALID_EVIDENCE"
    elif any(x in blockers for x in ("EXACTLY_SIX_MONTHS_REQUIRED","MONTH_WINDOW_OR_CONTINUITY_INVALID","INCOMPLETE_OBSERVABLE_COVERAGE")): state="INSUFFICIENT_HISTORY"
    else: state=blockers[0] if blockers else "COMPUTABLE"
    return ValidationResult(not blockers,state,blockers,months)
