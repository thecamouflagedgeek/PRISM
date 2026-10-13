"""Experimental parser-independent credit evidence contract for Phase 2D.

This package is deliberately isolated from production scoring and document parsing.
"""
from .models import (Consent, CreditAccountEvidence, CreditMonthlyRecord, EvidenceSource,
                     EvidenceValue, Provenance, RepaymentStatus, RepaymentStatusKind)
from .validation import validate_account, ValidationResult
from .feature_adapter import compute_features, FeatureResult
from .eligibility import assess_eligibility

__all__ = ["Consent", "CreditAccountEvidence", "CreditMonthlyRecord", "EvidenceSource",
           "EvidenceValue", "Provenance", "RepaymentStatus", "RepaymentStatusKind",
           "validate_account", "ValidationResult", "compute_features", "FeatureResult",
           "assess_eligibility"]
