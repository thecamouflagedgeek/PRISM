"""Field-level lineage validation and derived feature provenance."""
from .models import EvidenceValue, RepaymentStatus

def value_provenance_complete(value: EvidenceValue) -> bool:
    return bool(value.provenance) and all(p.complete() for p in value.provenance)

def status_provenance_complete(value: RepaymentStatus) -> bool:
    return bool(value.provenance) and all(p.complete() for p in value.provenance)

def derived_provenance(method: str, fields: tuple[str, ...], sources: tuple[str, ...]):
    return {"derivation_method": method, "input_fields": list(fields), "source_record_ids": list(sources)}
