"""
PRISM FastAPI Parser Adapter
Drop-in integration for assessment_routes.py.
Replace your existing parser imports with this module.

Before (old):
    from parsers.bank_parser import BankParser
    from parsers.salary_parser import SalaryParser
    from parsers.utility_parser import UtilityParser

After (new):
    from parsers.parser_adapter import parse_document

The returned dict is identical in structure to what the old parsers returned,
so risk_scorer.py and feature engineering require zero changes.
"""

import logging
import os
from typing import Optional

from fastapi import UploadFile, HTTPException

from ingestion.universal_pipeline import UniversalParser, ParseResult

logger = logging.getLogger(__name__)

# Singleton parser (initialised once, reused per request)
_parser: Optional[UniversalParser] = None


def get_parser() -> UniversalParser:
    global _parser
    if _parser is None:
        _parser = UniversalParser(
            # Set POPPLER_PATH env var on Windows if needed
            poppler_path=os.environ.get("POPPLER_PATH"),
            tesseract_cmd=os.environ.get("TESSERACT_CMD"),
        )
    return _parser


async def parse_document(upload_file: UploadFile) -> dict:
    """
    Async wrapper for FastAPI routes.

    Returns the feature dict directly — same format as old parsers.
    Raises HTTPException on parse failure with a diagnostic message.

    Usage in assessment_routes.py:
        from parsers.parser_adapter import parse_document

        @router.post("/assess")
        async def assess(file: UploadFile = File(...)):
            features = await parse_document(file)
            score = risk_scorer.score(features)
            ...
    """
    contents = await upload_file.read()
    filename = upload_file.filename or "document"

    parser = get_parser()
    result: ParseResult = parser.parse_bytes(contents, filename)

    if not result.success:
        logger.warning(
            "Parse failed for %s: %s | diagnostics: %s",
            filename,
            result.error,
            result.diagnostics,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": result.error or "Document parsing failed",
                "diagnostics": result.diagnostics,
                "entities_found": result.entities_found,
                "missing_entities": result.missing_entities,
            },
        )

    logger.info(
        "Parsed %s → doc_type=%s confidence=%.2f method=%s",
        filename,
        result.doc_type,
        result.confidence,
        result.extraction_method,
    )

    # Return features with metadata attached (non-breaking — old risk scorer
    # ignores unknown keys via dict.get())
    return {
        **result.features,
        "_doc_type": result.doc_type,
        "_confidence": result.confidence,
        "_extraction_method": result.extraction_method,
        "_quality_score": result.quality_score,
    }


def parse_document_sync(file_path: str) -> dict:
    """
    Synchronous version for CLI / test usage.

    Usage:
        python -c "from parsers.parser_adapter import parse_document_sync; \
                   print(parse_document_sync('tests/sample_bank.pdf'))"
    """
    parser = get_parser()
    result: ParseResult = parser.parse(file_path)

    if not result.success:
        raise ValueError(
            f"Parse failed: {result.error}\nDiagnostics: {result.diagnostics}"
        )

    return {
        **result.features,
        "_doc_type": result.doc_type,
        "_confidence": result.confidence,
        "_extraction_method": result.extraction_method,
        "_quality_score": result.quality_score,
    }
