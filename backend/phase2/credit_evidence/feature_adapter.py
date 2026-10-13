"""Pure implementation of the four frozen Phase 2B.6 features."""
from dataclasses import dataclass
from decimal import Decimal
from .models import CreditAccountEvidence, ValueState, RepaymentStatusKind
from .validation import validate_account
from .provenance import derived_provenance

@dataclass(frozen=True)
class FeatureResult:
    state: str
    values: dict | None
    provenance: dict | None
    blockers: tuple[str, ...]

def compute_features(account: CreditAccountEvidence, *, at=None) -> FeatureResult:
    valid=validate_account(account,at=at)
    if not valid.valid: return FeatureResult(valid.state,None,None,valid.blockers)
    records=tuple(sorted(account.monthly_records,key=lambda r:r.statement_month))
    # UCI PAY_0 is most recent September; PAY_2..PAY_6 are August through April.
    levels=[r.repayment_status.delinquency_level for r in records]
    recent=levels[-1]
    months=sum(x>0 for x in levels)
    denominator=sum((max(r.statement_balance.value,Decimal(0)) for r in records),Decimal(0))
    numerator=sum((r.payment_amount.value for r in records),Decimal(0))
    if denominator<=0: return FeatureResult("ZERO_DENOMINATOR",None,None,("ZERO_DENOMINATOR",))
    mean=sum((r.statement_balance.value for r in records),Decimal(0))/Decimal(6)
    values={"recent_delinquency_level":int(recent),"months_with_delinquency":int(months),
            "payment_to_statement_ratio":numerator/denominator,"mean_statement_balance":mean}
    prov={}
    names=("recent_delinquency_level","months_with_delinquency","payment_to_statement_ratio","mean_statement_balance")
    for name in names:
        fields=("repayment_status.delinquency_level",) if name in names[:2] else (("payment_amount","statement_balance") if name==names[2] else ("statement_balance",))
        selected=records[-1:] if name=="recent_delinquency_level" else records
        source_ids=[]
        for r in selected:
            lineage_values=(r.repayment_status,) if name in names[:2] else ((r.payment_amount,r.statement_balance) if name==names[2] else (r.statement_balance,))
            source_ids.extend(p.page_or_record_id for v in lineage_values for p in v.provenance)
        prov[name]=derived_provenance("phase2b6_frozen_formula_v1",fields,tuple(dict.fromkeys(source_ids)))
    return FeatureResult("COMPUTABLE",values,prov,())
