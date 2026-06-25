"""
PRISM Text Normalization Layer
Cleans and standardises raw extracted text before entity recognition.
Handles: OCR artifacts, currency formats, date formats, decimal formats,
         broken words, invisible characters, duplicate whitespace.
"""

import re
import unicodedata
import logging

logger = logging.getLogger(__name__)


class TextNormalizer:
    """
    Converts raw extracted text (native or OCR) into clean, consistent text
    suitable for entity recognition.
    """

    # ------------------------------------------------------------------
    # Currency synonyms → strip to bare number
    # ------------------------------------------------------------------
    CURRENCY_PREFIXES = re.compile(
        r"(?:Rs\.?|INR|₹|USD|\$|EUR|€)\s*", re.IGNORECASE
    )

    # Comma-separated number like 1,00,000.00 or 10,000
    COMMA_NUMBER = re.compile(r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?)")

    # OCR commonly confuses these pairs in financial docs
    OCR_CORRECTIONS = [
        (re.compile(r"\bO\b"), "0"),          # standalone O → 0
        (re.compile(r"(?<=\d)O(?=\d)"), "0"), # digit-O-digit
        (re.compile(r"(?<=\d)l(?=\d)"), "1"), # digit-l-digit
        (re.compile(r"(?<=\d)I(?=\d)"), "1"), # digit-I-digit
        (re.compile(r"(?<=\d)S(?=\d)"), "5"), # digit-S-digit  (common scan error)
    ]

    # Date patterns to normalise → DD/MM/YYYY
    DATE_PATTERNS = [
        # DD-MM-YYYY or DD.MM.YYYY
        (re.compile(r"\b(\d{1,2})[-.](\d{1,2})[-.](\d{4})\b"), r"\1/\2/\3"),
        # YYYY-MM-DD
        (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), r"\3/\2/\1"),
        # DD Mon YYYY  e.g. 01 Jan 2024
        (re.compile(
            r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})\b",
            re.IGNORECASE,
        ), _date_month_word_to_slash),
    ]

    def normalise(self, raw_text: str) -> str:
        text = raw_text
        text = self._remove_invisible_chars(text)
        text = self._fix_ocr_errors(text)
        text = self._normalise_line_breaks(text)
        text = self._remove_duplicate_spaces(text)
        text = self._normalise_dates(text)
        text = self._normalise_currencies(text)
        text = self._normalise_decimal_formats(text)
        text = self._merge_broken_words(text)
        return text.strip()

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _remove_invisible_chars(self, text: str) -> str:
        # Remove zero-width chars, non-breaking spaces, soft hyphens
        cleaned = "".join(
            ch for ch in text
            if not unicodedata.category(ch).startswith("C") or ch in "\n\t "
        )
        return cleaned

    def _fix_ocr_errors(self, text: str) -> str:
        for pattern, replacement in self.OCR_CORRECTIONS:
            text = pattern.sub(replacement, text)
        return text

    def _normalise_line_breaks(self, text: str) -> str:
        text = re.sub(r"\r\n|\r", "\n", text)
        # Collapse 3+ blank lines into 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _remove_duplicate_spaces(self, text: str) -> str:
        # Collapse multiple spaces/tabs to single space (preserve newlines)
        lines = []
        for line in text.split("\n"):
            lines.append(re.sub(r"[ \t]+", " ", line).strip())
        return "\n".join(lines)

    def _normalise_dates(self, text: str) -> str:
        for pattern, replacement in self.DATE_PATTERNS:
            if callable(replacement):
                text = pattern.sub(replacement, text)
            else:
                text = pattern.sub(replacement, text)
        return text

    def _normalise_currencies(self, text: str) -> str:
        # Strip currency symbols/prefixes
        text = self.CURRENCY_PREFIXES.sub("", text)
        # Remove commas from numbers: 1,00,000.50 → 100000.50
        def remove_commas(m):
            return m.group(0).replace(",", "")
        text = self.COMMA_NUMBER.sub(remove_commas, text)
        return text

    def _normalise_decimal_formats(self, text: str) -> str:
        # European format: 1.000,50 → 100050 (rare in India but handle it)
        text = re.sub(
            r"\b(\d{1,3})\.(\d{3}),(\d{2})\b",
            lambda m: f"{m.group(1)}{m.group(2)}.{m.group(3)}",
            text,
        )
        return text

    def _merge_broken_words(self, text: str) -> str:
        # Merge hyphen-broken words across line breaks: "transac-\ntion" → "transaction"
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        return text


def _date_month_word_to_slash(m: re.Match) -> str:
    months = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    day = m.group(1).zfill(2)
    month = months.get(m.group(2).lower()[:3], m.group(2))
    year = m.group(3)
    return f"{day}/{month}/{year}"
