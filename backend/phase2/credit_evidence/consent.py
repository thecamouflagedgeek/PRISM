"""Consent scope checks for experimental evidence consumption."""
from .models import Consent

SCOPE_CARD_STATEMENTS = "CREDIT_CARD_STATEMENTS"
SCOPE_LOAN_HISTORY = "LOAN_ACCOUNT_HISTORY"
SCOPE_BUREAU_HISTORY = "BUREAU_REPAYMENT_HISTORY"
SCOPE_BANK_CROSS_CHECK = "BANK_TRANSACTION_CROSS_CHECK"

def consent_permits(consent: Consent, required_scope: str, at):
    return consent.permits(required_scope, at)
