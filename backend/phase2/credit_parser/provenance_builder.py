"""Construct Phase 2D lineage values from deterministic extracted fields."""
from ..credit_evidence.models import Provenance, EvidenceSource, SourceType, SourceRole

def provenance(*, document_id, source_type, field, original, normalized, method, confidence, record_id, transform="normalized"):
    return Provenance(source_document_id=document_id,source_type=source_type,source_field=field,extraction_method=method,
        extraction_confidence=confidence,normalization_transform=transform,original_value=original,normalized_value=normalized,page_or_record_id=record_id)

def source(*, document_id, source_type, role, account_reference, confidence, authenticated, record_ids=()):
    return EvidenceSource(document_id,source_type,role,account_reference,confidence,authenticated,tuple(record_ids))
