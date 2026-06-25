"""
PRISM Validation Layer
Progressive 5-level validation gate before passing features to risk engine.
Rejects only on genuine data failure, not formatting differences.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from parsers.confidence_evaluator import EvaluationReport

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    passed: bool
    level_reached: int          # 1-5 (5 = fully passed)
    failure_reason: Optional[str]
    features: Optional[dict]
    doc_type: Optional[str]
    confidence: float
    diagnostics: list[str]


class ValidationLayer:
    """
    Five progressive checks before the risk engine receives features.
    Never fails on cosmetic/formatting grounds.
    """

    # Minimum features required per doc type to pass Level 4
    MINIMUM_FEATURES: dict[str, list[str]] = {
        "bank": ["credit_debit_ratio", "average_monthly_balance"],
        "salary": ["gross_salary", "net_salary"],
        "utility": ["bill_amount", "payment_discipline_flag"],
    }

    def validate(self, report: EvaluationReport) -> ValidationResult:
        diagnostics = []

        # Level 1: Was the document readable at all?
        if report.rejected:
            return ValidationResult(
                passed=False,
                level_reached=1,
                failure_reason=report.rejection_reason or "Document not readable",
                features=None,
                doc_type=None,
                confidence=0.0,
                diagnostics=[report.rejection_reason or "Document not readable"],
            )
        diagnostics.append("Level 1 PASS: Document is readable")

        # Level 2: Was text extracted successfully?
        result = report.selected_result
        if not result.entities_found:
            return ValidationResult(
                passed=False,
                level_reached=2,
                failure_reason="No financial entities could be extracted from document text",
                features=None,
                doc_type=report.selected_doc_type,
                confidence=result.confidence,
                diagnostics=diagnostics + ["Level 2 FAIL: No entities extracted"],
            )
        diagnostics.append(f"Level 2 PASS: {len(result.entities_found)} entities extracted")

        # Level 3: Minimum financial entities detected?
        if result.quality_score < 0.25:
            missing_str = ", ".join(result.missing_entities[:3])
            return ValidationResult(
                passed=False,
                level_reached=3,
                failure_reason=f"Insufficient financial data. Missing: {missing_str}",
                features=None,
                doc_type=report.selected_doc_type,
                confidence=result.confidence,
                diagnostics=diagnostics + [f"Level 3 FAIL: quality_score={result.quality_score:.2f}"],
            )
        diagnostics.append(f"Level 3 PASS: quality_score={result.quality_score:.2f}")

        # Level 4: Required features computed?
        doc_type = report.selected_doc_type
        required = self.MINIMUM_FEATURES.get(doc_type, [])
        features = result.features
        missing_features = [k for k in required if not features.get(k)]

        if missing_features:
            return ValidationResult(
                passed=False,
                level_reached=4,
                failure_reason=f"Required features not computable: {', '.join(missing_features)}",
                features=None,
                doc_type=doc_type,
                confidence=result.confidence,
                diagnostics=diagnostics + [f"Level 4 FAIL: missing features {missing_features}"],
            )
        diagnostics.append("Level 4 PASS: All required features computed")

        # Level 5: Pass to risk engine
        diagnostics.append("Level 5 PASS: Ready for PRISM risk scoring engine")

        return ValidationResult(
            passed=True,
            level_reached=5,
            failure_reason=None,
            features=features,
            doc_type=doc_type,
            confidence=result.confidence,
            diagnostics=diagnostics,
        )
