"""Canonical normalized evidence types. No OCR/parser-specific values are accepted."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
import re
from typing import Any

class ProductType(str, Enum):
    CREDIT_CARD="CREDIT_CARD"; PERSONAL_LOAN="PERSONAL_LOAN"; HOME_LOAN="HOME_LOAN"; AUTO_LOAN="AUTO_LOAN"; OTHER_CREDIT="OTHER_CREDIT"
class ValueState(str, Enum):
    PRESENT="PRESENT"; MISSING="MISSING"; NOT_APPLICABLE="NOT_APPLICABLE"; INVALID="INVALID"; CONFLICTING="CONFLICTING"
class SourceType(str, Enum):
    CREDIT_CARD_STATEMENT="CREDIT_CARD_STATEMENT"; LOAN_STATEMENT="LOAN_STATEMENT"; BUREAU_HISTORY="BUREAU_HISTORY"; LENDER_HISTORY="LENDER_HISTORY"; STRUCTURED_ACCOUNT_HISTORY="STRUCTURED_ACCOUNT_HISTORY"; BANK_CROSS_CHECK="BANK_CROSS_CHECK"
class SourceRole(str, Enum):
    PRIMARY_ACCOUNT_SOURCE="PRIMARY_ACCOUNT_SOURCE"; SUPPORTING_SOURCE="SUPPORTING_SOURCE"; CROSS_CHECK_SOURCE="CROSS_CHECK_SOURCE"
class RepaymentStatusKind(str, Enum):
    CURRENT="CURRENT"; DELINQUENT="DELINQUENT"; NO_PAYMENT_DUE="NO_PAYMENT_DUE"; UNKNOWN="UNKNOWN"; NOT_APPLICABLE="NOT_APPLICABLE"
class ConsentState(str, Enum):
    GRANTED="GRANTED"; NOT_GRANTED="NOT_GRANTED"; WITHDRAWN="WITHDRAWN"; UNKNOWN="UNKNOWN"
class FacilityApplicability(str, Enum):
    APPLICABLE="APPLICABLE"; NOT_APPLICABLE="NOT_APPLICABLE"; UNKNOWN="UNKNOWN"

@dataclass(frozen=True)
class Provenance:
    source_document_id: str
    source_type: SourceType
    source_field: str
    extraction_method: str
    extraction_confidence: float
    normalization_transform: str
    original_value: Any
    normalized_value: Any
    page_or_record_id: str | None = None
    derivation_method: str | None = None
    input_fields: tuple[str, ...] = ()
    source_record_ids: tuple[str, ...] = ()
    def complete(self) -> bool:
        return bool(self.source_document_id and self.source_type and self.page_or_record_id and self.source_field and self.extraction_method and self.normalization_transform and 0 <= self.extraction_confidence <= 1)

@dataclass(frozen=True)
class EvidenceValue:
    state: ValueState
    value: Decimal | None = None
    currency: str | None = None
    provenance: tuple[Provenance, ...] = ()
    reason: str | None = None
    def __post_init__(self):
        if self.state is ValueState.PRESENT and self.value is None: raise ValueError("PRESENT requires a value; zero is valid")
        if self.state is not ValueState.PRESENT and self.value is not None: raise ValueError("non-PRESENT values cannot carry numeric values")
        if self.value is not None and not self.value.is_finite(): raise ValueError("numeric evidence must be finite")

@dataclass(frozen=True)
class RepaymentStatus:
    state: ValueState
    status: RepaymentStatusKind | None = None
    delinquency_level: int | None = None  # UCI semantics: 0 current, 1..9 (9 means 9+ months); -1/-2 both normalized to 0 only when explicitly observed.
    days_past_due: int | None = None
    source_code: str | None = None
    provenance: tuple[Provenance, ...] = ()
    def __post_init__(self):
        if self.state is ValueState.PRESENT and self.status is None: raise ValueError("PRESENT repayment status requires explicit status")
        if self.delinquency_level is not None and not 0 <= self.delinquency_level <= 9: raise ValueError("delinquency level must be 0..9")
        if self.status is RepaymentStatusKind.DELINQUENT and (self.delinquency_level is None or self.delinquency_level == 0): raise ValueError("DELINQUENT requires severity 1..9")

@dataclass(frozen=True)
class Consent:
    state: ConsentState
    scopes: frozenset[str] = frozenset()
    granted_at: datetime | None = None
    expires_at: datetime | None = None
    withdrawn_at: datetime | None = None
    version: str = ""
    def permits(self, required: str, at: datetime) -> bool:
        return (self.state is ConsentState.GRANTED and required in self.scopes and self.granted_at is not None and self.granted_at <= at and (self.expires_at is None or at < self.expires_at) and (self.withdrawn_at is None or at < self.withdrawn_at))

@dataclass(frozen=True)
class EvidenceSource:
    source_document_id: str
    source_type: SourceType
    role: SourceRole
    account_reference: str
    account_link_confidence: float
    authenticated: bool
    record_ids: tuple[str, ...] = ()
    def __post_init__(self):
        if not 0 <= self.account_link_confidence <= 1: raise ValueError("account link confidence must be 0..1")

@dataclass(frozen=True)
class CreditFacilityApplicabilityEvidence:
    borrower_reference: str
    state: FacilityApplicability
    verified_at: datetime
    provenance: tuple[Provenance, ...]
    def __post_init__(self):
        if not self.borrower_reference or not self.provenance or not all(p.complete() for p in self.provenance): raise ValueError("facility applicability requires borrower identity and verified provenance")

@dataclass(frozen=True)
class CreditMonthlyRecord:
    statement_month: str  # YYYY-MM, account-local statement month
    statement_balance: EvidenceValue
    payment_amount: EvidenceValue
    repayment_status: RepaymentStatus
    account_reference: str
    source_document_ids: tuple[str, ...] = ()
    minimum_amount_due: EvidenceValue | None = None
    total_amount_due: EvidenceValue | None = None
    due_date: str | None = None
    payment_date: str | None = None
    unresolved_conflict: bool = False
    def __post_init__(self):
        if len(self.statement_month)!=7 or self.statement_month[4]!='-' or not self.statement_month[:4].isdigit() or not 1<=int(self.statement_month[5:])<=12: raise ValueError("statement_month must be YYYY-MM")

@dataclass(frozen=True)
class CreditAccountEvidence:
    borrower_reference: str
    account_reference: str
    product_type: ProductType
    provider_name: str
    masked_account_number: str
    currency: str
    account_state: str
    prediction_cutoff_month: str  # first day of this month is exclusive cutoff
    monthly_records: tuple[CreditMonthlyRecord, ...]
    evidence_sources: tuple[EvidenceSource, ...]
    consent: Consent
    coverage_start_month: str | None = None
    coverage_end_month_exclusive: str | None = None
    validation_state: str = "UNVALIDATED"
    conflicts: tuple[str, ...] = ()
    def __post_init__(self):
        if not self.borrower_reference or not self.account_reference or not self.provider_name: raise ValueError("borrower, account, and provider references are required")
        if not self.masked_account_number or re.fullmatch(r"\d{12,19}", self.masked_account_number): raise ValueError("store only a masked/tokenized account identifier")
        if len(self.currency) != 3 or not self.currency.isalpha(): raise ValueError("currency must be an ISO 4217 code")
        for month in (self.prediction_cutoff_month, self.coverage_start_month, self.coverage_end_month_exclusive):
            if month is not None and (len(month)!=7 or month[4]!='-' or not month[:4].isdigit() or not 1<=int(month[5:])<=12): raise ValueError(f"invalid YYYY-MM month: {month}")
