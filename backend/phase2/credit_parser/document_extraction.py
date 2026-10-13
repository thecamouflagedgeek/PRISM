"""Strict, provenance-aware extraction for explicitly labeled card statements.

This adapter reuses PRISM's PDF text/OCR services and Phase 2E controlled-text
normalizer. It intentionally does not guess issuer-specific table layouts.
"""
from __future__ import annotations

from pathlib import Path
import re

from ingestion.document.classifier import is_credit_card_statement
from ingestion.extractors.pdf_text import extract_digital_text
from phase2.credit_parser.field_mapping import TEXT_LABELS


_BANK_MARKERS = ("bank statement", "statement of account", "ifsc", "micr", "upi", "neft", "rtgs", "imps")
_AUXILIARY_LABELS = {
    "STATEMENT DATE": "statement_date", "STATEMENT PERIOD": "statement_period",
    "TOTAL AMOUNT DUE": "amount_due", "MINIMUM AMOUNT DUE": "minimum_amount_due",
    "PAYMENT DATE": "payment_date", "PAYMENT DUE DATE": "payment_due_date",
    "STATEMENT REFERENCE": "statement_reference", "PAYMENT STATEMENT REFERENCE": "payment_statement_reference",
    "PAYMENT SETTLEMENT STATUS": "payment_settlement_status", "REPAYMENT OBSERVATION DATE": "repayment_observation_date",
    "PREDICTION CUTOFF MONTH (EXCLUSIVE)": "declared_cutoff_month",
}


def extract_document_text(path: str, ocr_engine):
    """Return text, method, confidence, page count; supports PDF and common images."""
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png"}:
        from PIL import Image
        import pytesseract
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image)
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        confidence_values = []
        for item in data.get("conf", []):
            try:
                number = float(item)
                if number >= 0:
                    confidence_values.append(number)
            except (TypeError, ValueError):
                continue
        confidence = sum(confidence_values) / (100 * len(confidence_values)) if confidence_values else 0.0
        return text, "tesseract_image_ocr", confidence, 1
    if suffix != ".pdf":
        raise ValueError("Unsupported statement file type")

    import fitz
    import pytesseract
    from PIL import Image
    pages, confidences, methods = [], [], set()
    with fitz.open(path) as pdf:
        if pdf.needs_pass:
            raise ValueError("Encrypted PDF: upload an unlocked statement")
        page_count = len(pdf)
        for page in pdf:
            page_text = page.get_text("text") or ""
            if len(page_text.strip()) < 30:
                if ocr_engine is None:
                    pages.append(page_text)
                    methods.add("unreadable_page")
                    continue
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
                page_text = pytesseract.image_to_string(image)
                values = []
                for token_confidence in data.get("conf", []):
                    try:
                        value = float(token_confidence)
                        if value >= 0:
                            values.append(value)
                    except (TypeError, ValueError):
                        continue
                if values:
                    confidences.extend(values)
                methods.add("tesseract_scanned_page_ocr")
            else:
                methods.add("native_pdf_text")
            pages.append(page_text)
    text = "\n\f\n".join(pages)
    if not text.strip():
        return text, "no_readable_text", 0.0, page_count
    if "unreadable_page" in methods:
        return text, "partial_page_extraction", (sum(confidences) / (100 * len(confidences)) if confidences else 0.0), page_count
    method = "mixed_pdf_text_and_ocr" if len(methods) > 1 else next(iter(methods))
    # Native text is not assigned an accuracy percentage. Zero is fail-closed until
    # field validation plus account authentication supplies verifiable confidence.
    confidence = sum(confidences) / (100 * len(confidences)) if confidences else 0.0
    return text, method, confidence, page_count


def classify_card_statement(text: str) -> tuple[bool, str]:
    """Require a card-statement header and conservative card field signals."""
    lowered = text.casefold()
    card_header = bool(re.search(r"\b(?:credit\s+card|card)\s+(?:monthly\s+)?statement\b", lowered))
    strong_fields = sum(term in lowered for term in (
        "minimum amount due", "total amount due", "payment due date",
        "sanctioned credit limit", "available credit limit", "card no", "card account",
    ))
    bank_fields = sum(term in lowered for term in _BANK_MARKERS)
    # A true labeled card title plus summary fields is required. Incidental
    # card/loan transaction descriptions in bank statements cannot qualify.
    is_card = card_header and is_credit_card_statement(text) and strong_fields >= 2
    if bank_fields >= 3 and not ("credit card statement" in lowered and strong_fields >= 3):
        return False, "BANK_STATEMENT_OR_AMBIGUOUS_CLASSIFICATION"
    return is_card, "CREDIT_CARD_STATEMENT" if is_card else "CARD_STATEMENT_SIGNATURE_NOT_CONFIRMED"


def extract_labeled_fields(text: str) -> tuple[dict, list[str]]:
    """Extract explicit fields from common label variants, retaining page/line lineage."""
    found, auxiliary = {}, {}
    page_number = 1
    page_line = 0
    for line_number, line in enumerate(text.split("\n"), start=1):
        if "\f" in line:
            page_number += 1
            page_line = 0
            continue
        page_line += 1
        if ":" in line:
            label, value = line.split(":", 1)
        else:
            # Accept a clearly delimited label/value pair from statement layouts;
            # never search arbitrary transaction narration for a candidate value.
            match = re.match(r"^\s*([A-Za-z][A-Za-z /()_-]{2,45})\s{2,}(.+?)\s*$", line)
            if not match:
                continue
            label, value = match.groups()
        if not value.strip():
            continue
        key = label.strip().upper()
        aliases = {"CARD REFERENCE": "account_reference",
            "PAYMENT APPLIED TO THIS STATEMENT": "payment_amount",
            "EXPLICIT DELINQUENCY LEVEL": "delinquency_severity",
            "REPAYMENT STATUS CODE (SYNTHETIC TRAINING-STYLE)": "synthetic_status_code"}
        field = aliases.get(key) or TEXT_LABELS.get(re.sub(r"\s+", " ", key))
        auxiliary_field = _AUXILIARY_LABELS.get(re.sub(r"\s+", " ", key))
        location = {"page": page_number, "line": page_line}
        if auxiliary_field:
            value = value.strip()
            if auxiliary_field in auxiliary and auxiliary[auxiliary_field][0] != value:
                return {}, [f"CONFLICTING_FIELD:{auxiliary_field}"]
            auxiliary[auxiliary_field] = (value.strip(), location)
        if field:
            # Duplicate labels with different values are conflicting evidence.
            value = value.strip()
            if field == "statement_month":
                from phase2.credit_parser.parser import normalize_month
                try:
                    normalize_month(value)
                except ValueError:
                    return {}, ["INVALID_STATEMENT_MONTH"]
            if field in found and found[field][0] != value:
                if field == "statement_month" and normalize_month(found[field][0]) == normalize_month(value):
                    if key in {"STATEMENT MONTH", "BILLING MONTH"}:
                        found[field] = (value, location)
                    continue
                return {}, [f"CONFLICTING_FIELD:{field}"]
            found[field] = (value.strip(), location)
    # A fictional token is an explicit account identifier, never a guessed real PAN.
    ref = found.get("account_reference")
    if ref and re.fullmatch(r"TEST-CARD-[A-Za-z0-9-]+", ref[0]) and "SYNTHETIC TEST DOCUMENT" in text:
        found.setdefault("masked_account_number", ref)
    if "synthetic_status_code" in found and "SYNTHETIC TEST DOCUMENT" in text:
        code, location = found["synthetic_status_code"]
        level = found.get("delinquency_severity", (None,))[0]
        if code in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"} and code == level:
            found.setdefault("status", ("CURRENT" if code == "0" else "DELINQUENT", location))
        else:
            return {}, ["CONFLICTING_SYNTHETIC_REPAYMENT_CODE"]
    gaps = [f"MISSING_FIELD:{field}" for field in (
        "statement_month", "account_reference", "provider", "masked_account_number",
        "currency", "statement_balance", "payment_amount", "status",
        "delinquency_severity",
    ) if field not in found]
    payload = {field: row[0] for field, row in found.items()}
    payload["_line_numbers"] = {field: row[1]["line"] for field, row in found.items()}
    payload["_field_provenance"] = {field: row[1] for field, row in found.items()}
    payload["_auxiliary_fields"] = {field: row[0] for field, row in auxiliary.items()}
    payload["_auxiliary_line_numbers"] = {field: row[1]["line"] for field, row in auxiliary.items()}
    payload["_auxiliary_provenance"] = {field: row[1] for field, row in auxiliary.items()}
    gaps.extend(validate_statement_dates(payload['_auxiliary_fields']))
    return payload, gaps


def validate_statement_dates(auxiliary):
    """Validate dates only when explicitly supplied; never infer repayment labels."""
    from datetime import datetime
    parsed, gaps = {}, []
    for key in ('statement_date', 'payment_due_date', 'payment_date', 'repayment_observation_date'):
        value = auxiliary.get(key)
        if not value: continue
        for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
            try: parsed[key] = datetime.strptime(value, fmt).date(); break
            except ValueError: pass
        if key not in parsed: gaps.append(f'INVALID_EXPLICIT_DATE:{key}')
    issue, due, paid, observed = (parsed.get(k) for k in ('statement_date','payment_due_date','payment_date','repayment_observation_date'))
    if issue and due and due <= issue: gaps.append('PAYMENT_DUE_DATE_NOT_AFTER_STATEMENT_DATE')
    if issue and paid and paid < issue: gaps.append('PAYMENT_PRECEDES_STATEMENT_DATE')
    if observed and paid and paid > observed: gaps.append('PAYMENT_AFTER_REPAYMENT_OBSERVATION')
    if observed and issue and observed < issue: gaps.append('REPAYMENT_OBSERVATION_PRECEDES_STATEMENT')
    if auxiliary.get('payment_statement_reference') and auxiliary.get('payment_statement_reference') != auxiliary.get('statement_reference'):
        gaps.append('PAYMENT_STATEMENT_REFERENCE_MISMATCH')
    if auxiliary.get('payment_settlement_status') and auxiliary['payment_settlement_status'].upper() != 'SETTLED':
        gaps.append('PAYMENT_NOT_EXPLICITLY_SETTLED')
    return gaps
