"""
PRISM - Document Validation Engine

P1 Document Intelligence Engine.

Responsibilities:
    1. Validate individual documents.
    2. Validate cross-document consistency.
    3. Produce structured findings.
    4. Determine document review status.

This engine does NOT:
    - calculate credit score
    - calculate PD
    - calculate fraud score
    - modify model artifacts
"""

from __future__ import annotations

from typing import Any, Dict, List

from .validation_rules import (
    validate_document,
    validate_cross_documents,
)


ENGINE_VERSION = "P1-DOC-v1"


# ============================================================
# SEVERITY ORDER
# ============================================================

SEVERITY_ORDER = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


# ============================================================
# STATUS
# ============================================================

def _determine_status(
    findings: List[Dict[str, Any]],
) -> str:
    """
    Convert validation findings into a document status.
    """

    if not findings:
        return "VERIFIED"

    severities = [
        SEVERITY_ORDER.get(
            finding.get("severity", "LOW"),
            1,
        )
        for finding in findings
    ]

    highest = max(severities)

    if highest >= SEVERITY_ORDER["CRITICAL"]:
        return "REJECT"

    if highest >= SEVERITY_ORDER["HIGH"]:
        return "REVIEW"

    return "REVIEW"


# ============================================================
# DOCUMENT VALIDATION
# ============================================================

class DocumentValidationEngine:
    """
    PRISM P1 document validation engine.
    """

    def __init__(
        self,
        engine_version: str = ENGINE_VERSION,
    ) -> None:

        self.engine_version = engine_version

    # --------------------------------------------------------
    # Single document
    # --------------------------------------------------------

    def validate_single(
        self,
        document_type: str,
        document: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate one document.
        """

        document_type = document_type.upper()

        findings = validate_document(
            document_type,
            document,
        )

        status = _determine_status(
            findings
        )

        return {
            "document_type": document_type,
            "status": status,
            "valid": not bool(findings),
            "finding_count": len(findings),
            "findings": findings,
            "engine_version": self.engine_version,
        }

    # --------------------------------------------------------
    # Cross-document
    # --------------------------------------------------------

    def validate_cross_documents(
        self,
        documents: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Validate consistency across documents.
        """

        normalized_documents = {
            str(document_type).upper(): document
            for document_type, document
            in documents.items()
        }

        findings = validate_cross_documents(
            normalized_documents
        )

        status = _determine_status(
            findings
        )

        return {
            "status": status,
            "valid": not bool(findings),
            "finding_count": len(findings),
            "findings": findings,
            "engine_version": self.engine_version,
        }

    # --------------------------------------------------------
    # Full assessment
    # --------------------------------------------------------

    def assess(
        self,
        documents: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Run complete document validation.

        Example input:

            {
                "BANK": {...},
                "SALARY": {...},
                "UTILITY": {...},
                "APPLICATION": {...}
            }
        """

        document_results: Dict[str, Any] = {}

        all_findings: List[Dict[str, Any]] = []

        # ----------------------------------------------------
        # 1. Individual document validation
        # ----------------------------------------------------

        for document_type, document in documents.items():

            result = self.validate_single(
                document_type,
                document,
            )

            document_results[
                document_type.upper()
            ] = result

            all_findings.extend(
                result["findings"]
            )

        # ----------------------------------------------------
        # 2. Cross-document validation
        # ----------------------------------------------------

        cross_document_result = (
            self.validate_cross_documents(
                documents
            )
        )

        all_findings.extend(
            cross_document_result["findings"]
        )

        # ----------------------------------------------------
        # 3. Overall status
        # ----------------------------------------------------

        overall_status = _determine_status(
            all_findings
        )

        return {
            "document_status": overall_status,
            "documents": document_results,
            "cross_document": cross_document_result,
            "findings": all_findings,
            "finding_count": len(all_findings),
            "engine_version": self.engine_version,
        }


# ============================================================
# CONVENIENCE FUNCTION
# ============================================================

def validate_documents(
    documents: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Convenience wrapper around DocumentValidationEngine.
    """

    return DocumentValidationEngine().assess(
        documents
    )


__all__ = [
    "DocumentValidationEngine",
    "validate_documents",
]