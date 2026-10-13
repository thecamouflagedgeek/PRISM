"""Experimental parser result types; intentionally separate from scorecard features."""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

class ParseState(str,Enum): PARSED="PARSED"; PARTIALLY_PARSED="PARTIALLY_PARSED"; UNSUPPORTED="UNSUPPORTED"; INVALID="INVALID"
@dataclass(frozen=True)
class FieldIssue:
    field: str
    code: str
    message: str
@dataclass(frozen=True)
class ParsedStatement:
    state: ParseState
    account_reference: str | None
    product_type: object | None
    provider_name: str | None
    provider_key: str | None
    masked_account_number: str | None
    currency: str | None
    statement_month: str | None
    statement_balance: object
    payment_amount: object
    repayment_status: object
    source: object | None
    issues: tuple[FieldIssue,...]=()
@dataclass(frozen=True)
class ParsedRepaymentRecord:
    state: ParseState
    account_reference: str | None
    product_type: object | None
    provider_name: str | None
    provider_key: str | None
    month: str | None
    repayment_status: object
    source: object | None
    issues: tuple[FieldIssue,...]=()
@dataclass(frozen=True)
class AssemblyResult:
    state: str
    account: object | None
    validation: object | None
    eligibility: object | None
    features: object | None
    issues: tuple[str,...]=()
