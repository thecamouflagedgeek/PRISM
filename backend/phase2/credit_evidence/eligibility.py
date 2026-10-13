"""Experimental separation between evidence computability and model applicability."""
from dataclasses import dataclass
from .validation import validate_account
from .models import ProductType

@dataclass(frozen=True)
class CreditEvidenceEligibility:
    eligible_for_feature_computation: bool
    eligible_for_phase2b6_scorecard: bool
    blocking_reasons: tuple[str,...]
    warnings: tuple[str,...]

def assess_eligibility(account, *, borrower_account_count: int=1, at=None):
    result=validate_account(account,at=at); blockers=list(result.blockers); warnings=[]
    if borrower_account_count>1: blockers.append("MULTI_ACCOUNT_AGGREGATION_UNRESOLVED")
    if account.product_type is not ProductType.CREDIT_CARD: blockers.append("MODEL_PRODUCT_COMPATIBILITY_UNESTABLISHED")
    # Contract readiness is not model validation; Phase 2B.6 remains inconclusive.
    warnings.append("PHASE_2B6_INCONCLUSIVE_EXTERNAL_VALIDATION_ABSENT")
    blockers=tuple(dict.fromkeys(blockers))
    computable=result.valid
    return CreditEvidenceEligibility(computable,computable and borrower_account_count==1 and account.product_type is ProductType.CREDIT_CARD and not blockers,blockers,tuple(warnings))
