"""Thin explicit bridge to authoritative Phase 2D validation and feature computation."""
from ..credit_evidence.validation import validate_account
from ..credit_evidence.eligibility import assess_eligibility
from ..credit_evidence.feature_adapter import compute_features

def validate_and_compute(account, *, borrower_account_count=1, at=None):
    validation=validate_account(account,at=at)
    eligibility=assess_eligibility(account,borrower_account_count=borrower_account_count,at=at)
    features=compute_features(account,at=at)
    return validation,eligibility,features
