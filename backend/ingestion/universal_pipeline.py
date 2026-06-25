"""
PRISM Universal Financial Document Intelligence Pipeline
--------------------------------------------------------
Architecture: Confidence-driven extraction (no hard classifier)
Each extractor runs independently, highest confidence wins.
Backward compatible: outputs identical feature dicts to existing PRISM scoring engine.
"""

import re
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from ingestion.utils.pdf_utils import extract_txt_pdfplumber, extract_txt_pymupdf
from ingestion.utils.regex_utils import clean_amount


# ---------------------------------------------------------------------------
# 1. CANONICAL SYNONYM DICTIONARIES
# ---------------------------------------------------------------------------

BANK_SYNONYMS = {
    "credit": [
        "credit", "cr", "deposit", "deposited", "received", "inflow",
        "credited", "in", "receipt", "collection", "proceeds"
    ],
    "debit": [
        "debit", "dr", "withdrawal", "withdraw", "payment", "paid",
        "debited", "out", "expense", "charge", "transfer out", "sent"
    ],
    "opening_balance": [
        "opening balance", "open bal", "op bal", "brought forward",
        "b/f", "bf", "balance b/f", "opening"
    ],
    "closing_balance": [
        "closing balance", "close bal", "cl bal", "carried forward",
        "c/f", "cf", "balance c/f", "closing", "available balance",
        "current balance", "running balance", "balance"
    ],
    "account_number": [
        "account number", "account no", "account no.", "acct no",
        "a/c no", "a/c number", "acc no", "account"
    ],
}

SALARY_SYNONYMS = {
    "gross_salary": [
        "gross salary", "gross pay", "gross earnings", "gross income",
        "gross wages", "monthly gross", "total earnings", "ctc",
        "cost to company", "gross amount", "total gross"
    ],
    "net_salary": [
        "net salary", "net pay", "net earnings", "take home",
        "take-home pay", "net wages", "net amount", "in hand",
        "net payable", "amount payable", "total net"
    ],
    "basic_pay": [
        "basic", "basic pay", "basic salary", "basic wage",
        "base pay", "base salary"
    ],
    "hra": [
        "hra", "house rent allowance", "housing allowance",
        "rent allowance"
    ],
    "pf": [
        "pf", "epf", "provident fund", "employee pf",
        "employee provident fund", "pf deduction", "epf contribution"
    ],
    "tax": [
        "tds", "income tax", "tax deducted", "professional tax",
        "pt", "income tax deduction"
    ],
    "deductions": [
        "deductions", "total deductions", "deduction", "less"
    ],
}

UTILITY_SYNONYMS = {
    "bill_amount": [
        "bill amount", "total amount", "amount due", "payable amount",
        "net amount payable", "current charges", "total bill",
        "amount payable", "invoice amount", "total payable"
    ],
    "due_date": [
        "due date", "payment due", "last date", "pay by",
        "due by", "last date of payment", "payment deadline"
    ],
    "units_consumed": [
        "units", "units consumed", "consumption", "kwh", "kw",
        "unit consumed", "total units", "energy consumed"
    ],
    "consumer_number": [
        "consumer no", "consumer number", "customer no", "customer number",
        "account number", "ca no", "service no", "connection no"
    ],
    "payment_status": [
        "paid", "payment received", "receipt", "cleared",
        "settled", "payment confirmed"
    ],
}


# ---------------------------------------------------------------------------
# 2. DATE & AMOUNT PATTERNS (Indian + international formats)
# ---------------------------------------------------------------------------

DATE_PATTERNS = [
    # DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    re.compile(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}\b"),
    # DD/MM/YY, DD-MM-YY
    re.compile(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2}\b"),
    # DD Mon YYYY  (01 Jan 2025)
    re.compile(r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}\b",
               re.IGNORECASE),
    # DD-Mon-YY  (01-JAN-25)
    re.compile(r"\b\d{1,2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*-\d{2,4}\b",
               re.IGNORECASE),
    # YYYY-MM-DD  (ISO)
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    # Mon DD, YYYY  (Jan 01, 2025)
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
               re.IGNORECASE),
]

# Matches Indian lakh notation (1,00,000) and standard (10,000) with optional decimals
AMOUNT_PATTERN = re.compile(
    r"\b(?:\d{1,2},)?(?:\d{2},)*\d{3}(?:\.\d{1,2})?\b"
    r"|\b\d{1,6}\.\d{2}\b"
)


def find_date(text: str) -> Optional[str]:
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group()
    return None


def find_all_amounts(text: str) -> List[float]:
    """Return all parseable amounts from a string, largest to smallest."""
    raw = AMOUNT_PATTERN.findall(text)
    results = []
    for r in raw:
        try:
            results.append(float(r.replace(",", "")))
        except ValueError:
            pass
    return sorted(results, reverse=True)


def find_amount(text: str) -> Optional[float]:
    amounts = find_all_amounts(text)
    return amounts[0] if amounts else None


def synonym_present(text_lower: str, synonyms: List[str]) -> bool:
    return any(s in text_lower for s in synonyms)


def synonym_score(text_lower: str, synonyms: List[str]) -> int:
    return sum(1 for s in synonyms if s in text_lower)


# ---------------------------------------------------------------------------
# 3. TEXT EXTRACTOR
# ---------------------------------------------------------------------------

class TextExtractor:
    def __init__(self, ocr_engine=None, poppler_path=None, tesseract_cmd=None):
        self.ocr_engine = ocr_engine
        self.poppler_path = poppler_path
        self.tesseract_cmd = tesseract_cmd

    def extract(self, file_path: str) -> str:
        text = ""
        ocr_used = False

        try:
            text = extract_txt_pdfplumber(file_path)
            if not text:
                text = extract_txt_pymupdf(file_path)
                print("PDFPLUMBER TEXT LENGTH:", len(text))
                print("PYMUPDF TEXT LENGTH:", len(text))
        except Exception:
            pass

        if len(text.strip()) < 50:
            try:
                text = extract_txt_pymupdf(file_path)
            except Exception:
                pass

        if len(text.strip()) < 50 and self.ocr_engine:
            try:
                text = self.ocr_engine.extract_text_from_pdf(file_path)
                ocr_used = True
            except Exception:
                pass

        # OCR output skips normalize() stripping — just clean whitespace
        if ocr_used:
            text = re.sub(r" +", " ", text)
            text = re.sub(r"\n+", "\n", text)
            return text.strip()

        return self.normalize(text)

    def normalize(self, text: str) -> str:
        if not text:
            return ""
        # Preserve ₹ % ° and Indian financial characters; only strip true garbage
        text = re.sub(r"[^\x00-\x7F₹%°]", " ", text)
        # Normalize currency markers to empty (amounts handled separately)
        text = re.sub(r"(Rs\.?|INR|₹)\s*", "", text, flags=re.IGNORECASE)
        # Normalize spaces and newlines
        text = re.sub(r" +", " ", text)
        text = re.sub(r"\n+", "\n", text)
        # Repair common OCR splits: "clos ing" → "closing"
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        return text.strip()


# ---------------------------------------------------------------------------
# 4. EXTRACTION RESULT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    doc_type: str
    data: Any                          # pd.DataFrame or dict
    confidence: float                  # 0.0 – 1.0
    entities_found: List[str] = field(default_factory=list)
    missing_entities: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    diagnostics: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 5. BASE EXTRACTOR
# ---------------------------------------------------------------------------

class BaseExtractor:
    doc_type: str = "UNKNOWN"
    required_entities: List[str] = []
    optional_entities: List[str] = []

    def extract(self, text: str) -> ExtractionResult:
        raise NotImplementedError

    def _score_result(self, found: List[str], missing: List[str]) -> Tuple[float, float]:
        """
        Returns (confidence, quality_score).
        Confidence = weighted hit rate on required entities.
        Quality   = overall entity coverage including optional.
        """
        req = self.required_entities
        opt = self.optional_entities

        req_found = [e for e in found if e in req]
        req_score = len(req_found) / max(len(req), 1)

        opt_found = [e for e in found if e in opt]
        opt_score = len(opt_found) / max(len(opt), 1)

        confidence = req_score * 0.8 + opt_score * 0.2
        quality = (len(req_found) + len(opt_found)) / max(len(req) + len(opt), 1)
        return round(confidence, 3), round(quality, 3)


# ---------------------------------------------------------------------------
# 6. BANK EXTRACTOR
# ---------------------------------------------------------------------------

class BankExtractor(BaseExtractor):
    doc_type = "BANK"
    required_entities = ["transactions", "closing_balance"]
    optional_entities = ["opening_balance", "account_number", "ifsc"]

    def extract(self, text: str) -> ExtractionResult:
        lines = text.split("\n")
        found, missing, diagnostics = [], [], []

        # --- Detect column order from header line ---
        cr_col_pos, dr_col_pos = None, None
        for line in lines[:40]:
            lower = line.lower()
            has_cr = synonym_present(lower, ["credit", "cr ", "deposit"])
            has_dr = synonym_present(lower, ["debit", "dr ", "withdrawal"])
            if has_cr and has_dr:
                cr_col_pos = min(
                    (lower.index(s) for s in ["credit", "cr ", "deposit"] if s in lower),
                    default=None
                )
                dr_col_pos = min(
                    (lower.index(s) for s in ["debit", "dr ", "withdrawal"] if s in lower),
                    default=None
                )
                break

        # --- Parse transactions ---
        rows = []
        for line in lines:
            date = find_date(line)
            if not date:
                continue

            amounts = find_all_amounts(line)
            if not amounts:
                continue

            line_upper = line.upper()
            line_lower = line.lower()

            # Determine CR / DR using column position, then inline markers, then position
            debit, credit = None, None

            if cr_col_pos is not None and dr_col_pos is not None:
                split = max(cr_col_pos, dr_col_pos)
                left_amt = find_all_amounts(line[:split])
                right_amt = find_all_amounts(line[split:])
                if dr_col_pos < cr_col_pos:
                    debit = left_amt[0] if left_amt else None
                    credit = right_amt[0] if right_amt else None
                else:
                    credit = left_amt[0] if left_amt else None
                    debit = right_amt[0] if right_amt else None
            elif "CR" in line_upper or synonym_present(line_lower, BANK_SYNONYMS["credit"]):
                credit = amounts[0] if amounts else None
            elif "DR" in line_upper or synonym_present(line_lower, BANK_SYNONYMS["debit"]):
                debit = amounts[0] if amounts else None
            else:
                # Fallback: if 2+ amounts, first=debit, last=balance; if 1, treat as balance only
                if len(amounts) >= 2:
                    debit = amounts[0]

            balance = amounts[-1]  # last amount on a transaction line is almost always balance
            narration = line.replace(date, "").strip()
            narration = re.sub(r"\b[\d,]+(?:\.\d{1,2})?\b", "", narration).strip()

            rows.append({
                "date": date,
                "narration": narration,
                "debit": debit,
                "credit": credit,
                "closing_balance": balance,
            })

        if rows:
            found.append("transactions")
            found.append("closing_balance")
        else:
            missing.append("transactions")
            diagnostics.append("No date-anchored transaction rows detected.")

        if not rows:
            diagnostics.append(
                "Unable to locate transaction lines. "
                "Possible causes: scanned image, non-standard layout, or wrong document type."
            )

        # --- Account number ---
        for line in lines:
            if synonym_present(line.lower(), BANK_SYNONYMS["account_number"]):
                nums = re.findall(r"\b\d{9,18}\b", line)
                if nums:
                    found.append("account_number")
                    break
        if "account_number" not in found:
            missing.append("account_number")

        # --- Build DataFrame ---
        df = self._build_df(rows)
        confidence, quality = self._score_result(found, missing)

        # Boost confidence if we have a solid transaction set
        if len(rows) >= 5:
            confidence = min(confidence + 0.15, 1.0)

        return ExtractionResult(
            doc_type=self.doc_type,
            data=df,
            confidence=confidence,
            entities_found=found,
            missing_entities=missing,
            quality_score=quality,
            diagnostics=diagnostics,
        )

    def _build_df(self, rows: List[dict]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=["date", "amount", "type", "narration", "closing_balance"])

        df = pd.DataFrame(rows)

        # Ensure all columns exist safely
        for col in ["date", "narration", "debit", "credit", "closing_balance"]:
            if col not in df.columns:
                df[col] = None

        df["debit"] = df["debit"].apply(clean_amount)
        df["credit"] = df["credit"].apply(clean_amount)
        df["closing_balance"] = df["closing_balance"].apply(clean_amount)

        df["amount"] = df.apply(
            lambda r: r["credit"] if pd.notna(r.get("credit")) and r.get("credit", 0) > 0
            else (r["debit"] if pd.notna(r.get("debit")) else 0),
            axis=1
        )

        def detect_type(row):
            if pd.notna(row.get("credit")) and row.get("credit", 0) > 0:
                return "CR"
            if pd.notna(row.get("debit")) and row.get("debit", 0) > 0:
                return "DR"
            return None

        df["type"] = df.apply(detect_type, axis=1)

        final = df[["date", "amount", "type", "narration", "closing_balance"]].copy()
        final = final.dropna(subset=["date"]).reset_index(drop=True)
        return final


# ---------------------------------------------------------------------------
# 7. SALARY EXTRACTOR
# ---------------------------------------------------------------------------

class SalaryExtractor(BaseExtractor):
    doc_type = "SALARY"
    required_entities = ["net_salary"]
    optional_entities = ["gross_salary", "basic_pay", "hra", "pf", "tax", "deductions", "pay_period"]

    def extract(self, text: str) -> ExtractionResult:
        lines = text.split("\n")
        found, missing, diagnostics = [], [], []
        entities: Dict[str, Any] = {}

        for line in lines:
            lower = line.lower()

            if "gross_salary" not in entities and synonym_present(lower, SALARY_SYNONYMS["gross_salary"]):
                amt = find_amount(line)
                if amt:
                    entities["gross_salary"] = amt
                    found.append("gross_salary")

            if "net_salary" not in entities and synonym_present(lower, SALARY_SYNONYMS["net_salary"]):
                amt = find_amount(line)
                if amt:
                    entities["net_salary"] = amt
                    found.append("net_salary")

            if "basic_pay" not in entities and synonym_present(lower, SALARY_SYNONYMS["basic_pay"]):
                amt = find_amount(line)
                if amt:
                    entities["basic_pay"] = amt
                    found.append("basic_pay")

            if "hra" not in entities and synonym_present(lower, SALARY_SYNONYMS["hra"]):
                amt = find_amount(line)
                if amt:
                    entities["hra"] = amt
                    found.append("hra")

            if synonym_present(lower, SALARY_SYNONYMS["pf"]):
                entities["pf_contribution_flag"] = True
                if "pf" not in found:
                    found.append("pf")

            if synonym_present(lower, SALARY_SYNONYMS["tax"]):
                entities["tax_deduction_flag"] = True

            # Pay period detection
            if "pay_period" not in entities:
                date = find_date(line)
                if date and synonym_present(lower, ["period", "month", "for the month", "pay date", "salary for"]):
                    entities["pay_period"] = date
                    found.append("pay_period")

        if "pf_contribution_flag" not in entities:
            entities["pf_contribution_flag"] = False

        # net_salary fallback: if gross found but not net, try computing
        if "net_salary" not in entities and "gross_salary" in entities:
            diagnostics.append("net_salary not explicitly found; gross_salary detected.")
            missing.append("net_salary")
        elif "net_salary" not in entities:
            missing.append("net_salary")
            diagnostics.append(
                "Unable to locate salary amount. "
                "Document may not be a salary slip, or keywords differ from known synonyms."
            )

        entities.update({
            "gross_salary": entities.get("gross_salary"),
            "net_salary": entities.get("net_salary"),
        })

        confidence, quality = self._score_result(found, missing)

        # Confidence boost: salary docs often have both earnings and deductions tables
        if synonym_score(text.lower(), SALARY_SYNONYMS["gross_salary"]) >= 2:
            confidence = min(confidence + 0.1, 1.0)

        return ExtractionResult(
            doc_type=self.doc_type,
            data=pd.DataFrame([entities]) if entities else pd.DataFrame(),
            confidence=confidence,
            entities_found=found,
            missing_entities=missing,
            quality_score=quality,
            diagnostics=diagnostics,
        )


# ---------------------------------------------------------------------------
# 8. UTILITY EXTRACTOR
# ---------------------------------------------------------------------------

class UtilityExtractor(BaseExtractor):
    doc_type = "UTILITY"
    required_entities = ["bill_amount", "payment_discipline_flag"]
    optional_entities = ["due_date", "units_consumed", "consumer_number", "billing_period"]

    def extract(self, text: str) -> ExtractionResult:
        lines = text.split("\n")
        found, missing, diagnostics = [], [], []
        entities: Dict[str, Any] = {}
        text_lower = text.lower()

        for line in lines:
            lower = line.lower()

            if "bill_amount" not in entities and synonym_present(lower, UTILITY_SYNONYMS["bill_amount"]):
                amt = find_amount(line)
                if amt:
                    entities["bill_amount"] = amt
                    found.append("bill_amount")

            if "due_date" not in entities and synonym_present(lower, UTILITY_SYNONYMS["due_date"]):
                date = find_date(line)
                if date:
                    entities["due_date"] = date
                    found.append("due_date")

            if "units_consumed" not in entities and synonym_present(lower, UTILITY_SYNONYMS["units_consumed"]):
                amt = find_amount(line)
                if amt:
                    entities["units_consumed"] = amt
                    found.append("units_consumed")

            if "consumer_number" not in entities and synonym_present(lower, UTILITY_SYNONYMS["consumer_number"]):
                nums = re.findall(r"\b\d{6,15}\b", line)
                if nums:
                    entities["consumer_number"] = nums[0]
                    found.append("consumer_number")

        # Payment discipline: look for paid/receipt markers
        entities["payment_discipline_flag"] = synonym_present(
            text_lower, UTILITY_SYNONYMS["payment_status"]
        )
        found.append("payment_discipline_flag")

        if "bill_amount" not in entities:
            missing.append("bill_amount")
            diagnostics.append(
                "Bill amount not detected. "
                "Possible causes: amount on image layer, non-standard label, or wrong document type."
            )
        if "due_date" not in entities:
            missing.append("due_date")

        confidence, quality = self._score_result(found, missing)

        return ExtractionResult(
            doc_type=self.doc_type,
            data=pd.DataFrame([entities]) if entities else pd.DataFrame(),
            confidence=confidence,
            entities_found=found,
            missing_entities=missing,
            quality_score=quality,
            diagnostics=diagnostics,
        )


# ---------------------------------------------------------------------------
# 9. CONFIDENCE EVALUATOR — runs all extractors, picks best
# ---------------------------------------------------------------------------

class ConfidenceEvaluator:
    CONFIDENCE_THRESHOLD = 0.25

    def __init__(self):
        self.extractors = [
            BankExtractor(),
            SalaryExtractor(),
            UtilityExtractor(),
        ]

    def evaluate(self, text: str) -> ExtractionResult:
        results: List[ExtractionResult] = []

        for extractor in self.extractors:
            try:
                result = extractor.extract(text)
                results.append(result)
            except Exception as e:
                results.append(ExtractionResult(
                    doc_type=extractor.doc_type,
                    data=None,
                    confidence=0.0,
                    diagnostics=[f"Extractor error: {str(e)}"],
                ))

        best = max(results, key=lambda r: r.confidence)

        if best.confidence < self.CONFIDENCE_THRESHOLD:
            all_diags = [d for r in results for d in r.diagnostics]
            raise ValueError(
                f"Document does not appear to contain recoverable financial information. "
                f"Best confidence: {best.confidence:.0%}. "
                f"Diagnostics: {'; '.join(all_diags) or 'No specific diagnostics available.'}"
            )

        return best


# ---------------------------------------------------------------------------
# 10. VALIDATION PIPELINE (progressive, descriptive errors)
# ---------------------------------------------------------------------------

class ValidationPipeline:
    def validate(self, result: ExtractionResult) -> None:
        # Level 1: doc type resolved
        if result.doc_type == "UNKNOWN":
            raise ValueError("Document classification failed: no extractor reached confidence threshold.")

        # Level 2: data exists
        if result.data is None:
            raise ValueError(f"[{result.doc_type}] Extraction produced no data structure.")

        # Level 3: not empty
        if isinstance(result.data, pd.DataFrame) and result.data.empty:
            missing = ", ".join(result.missing_entities) or "unknown entities"
            diag = "; ".join(result.diagnostics) or "No diagnostics available."
            raise ValueError(
                f"[{result.doc_type}] Required financial entities missing: {missing}. {diag}"
            )

        # Level 4: type-specific required columns
        if result.doc_type == "BANK":
            self._check_columns(
                result.data,
                ["date", "amount", "type", "narration", "closing_balance"],
                result.doc_type,
            )
        elif result.doc_type == "SALARY":
            if "net_salary" not in result.data.columns and "gross_salary" not in result.data.columns:
                raise ValueError(
                    "[SALARY] Missing critical entities: neither net_salary nor gross_salary detected."
                )
        elif result.doc_type == "UTILITY":
            if "payment_discipline_flag" not in result.data.columns:
                raise ValueError("[UTILITY] Could not determine utility payment discipline status.")

    def _check_columns(self, df: pd.DataFrame, cols: List[str], doc_type: str) -> None:
        for col in cols:
            if col not in df.columns:
                raise ValueError(f"[{doc_type}] Missing standardized entity column: '{col}'")


# ---------------------------------------------------------------------------
# 11. UNIVERSAL PARSER — public entry point
# ---------------------------------------------------------------------------

class UniversalParser:
    def __init__(self, ocr_engine=None,poppler_path=None,tesseract_cmd=None):
        self.extractor = TextExtractor(ocr_engine, poppler_path=poppler_path,tesseract_cmd=tesseract_cmd)
        self.evaluator = ConfidenceEvaluator()
        self.validator = ValidationPipeline()

    def process(self, file_path: str) -> Tuple[str, Any]:
        """
        Returns (doc_type, mapped_data) where mapped_data is a DataFrame
        compatible with the existing PRISM feature engineering layer.
        """
        # Stage A: Extract & normalize text
        text = self.extractor.extract(file_path)

        # Only reject if ALL extraction strategies (including OCR) produced nothing
        if not text.strip():
            raise ValueError(
                "Text extraction failed: no readable content recovered from document. "
                "The file may be corrupted, password-protected, or an unsupported format."
            )

        # Stage B–D: Run all extractors, evaluate confidence, pick best
        result = self.evaluator.evaluate(text)

        # Stage E: Validate
        self.validator.validate(result)

        return result.doc_type, result.data