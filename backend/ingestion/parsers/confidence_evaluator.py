"""
PRISM Document Confidence Evaluator
Runs all three feature extractors on the canonical document,
picks the highest-confidence extractor, and rejects only when
ALL extractors fall below the minimum confidence threshold.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from schema_mapper.canonical_mapper import CanonicalDocument
from extractors.feature_extractors import (
    BankFeatureExtractor,
    SalaryFeatureExtractor,
    UtilityFeatureExtractor,
    ExtractionResult,
)

logger = logging.getLogger(__name__)

# Minimum confidence to accept any single extractor's output
MIN_CONFIDENCE_THRESHOLD = 0.20


@dataclass
class EvaluationReport:
    selected_doc_type: str
    selected_result: ExtractionResult
    all_results: dict[str, ExtractionResult]
    rejected: bool
    rejection_reason: Optional[str]


class DocumentConfidenceEvaluator:
    """
    Runs all extractors in parallel (functionally) and selects the best.
    Never rejects a document because of formatting — only when financial
    information cannot be recovered at all.
    """

    def __init__(self):
        self._bank = BankFeatureExtractor()
        self._salary = SalaryFeatureExtractor()
        self._utility = UtilityFeatureExtractor()

    def evaluate(self, canonical_doc: CanonicalDocument) -> EvaluationReport:
        results = {
            "bank": self._bank.extract(canonical_doc),
            "salary": self._salary.extract(canonical_doc),
            "utility": self._utility.extract(canonical_doc),
        }

        for doc_type, result in results.items():
            logger.info(
                "[%s] confidence=%.2f quality=%.2f found=%s missing=%s",
                doc_type,
                result.confidence,
                result.quality_score,
                result.entities_found,
                result.missing_entities,
            )

        # Pick best
        best_type = max(results, key=lambda t: results[t].confidence)
        best_result = results[best_type]

        # Reject only if everything is below threshold
        all_below = all(r.confidence < MIN_CONFIDENCE_THRESHOLD for r in results.values())
        if all_below:
            rejection_reason = self._build_rejection_reason(results)
            logger.warning("All extractors below threshold. Rejecting document. Reason: %s", rejection_reason)
            return EvaluationReport(
                selected_doc_type=best_type,
                selected_result=best_result,
                all_results=results,
                rejected=True,
                rejection_reason=rejection_reason,
            )

        logger.info("Selected extractor: %s (confidence=%.2f)", best_type, best_result.confidence)
        return EvaluationReport(
            selected_doc_type=best_type,
            selected_result=best_result,
            all_results=results,
            rejected=False,
            rejection_reason=None,
        )

    def _build_rejection_reason(self, results: dict[str, ExtractionResult]) -> str:
        all_diagnostics = []
        for doc_type, result in results.items():
            for diag in result.diagnostics:
                all_diagnostics.append(diag)

        if not all_diagnostics:
            return "Document does not appear to contain financial information"

        unique = list(dict.fromkeys(all_diagnostics))  # preserve order, dedupe
        return "; ".join(unique[:5])  # cap at 5 messages
