import subprocess
import json
import re

from llm.prompts import build_extraction_prompt, build_repair_prompt

MODEL_NAME = "qwen2.5:3b"


# ---------------------------------------------------------------------------
# LLM CALL
# ---------------------------------------------------------------------------

def call_llm(system_prompt: str, user_prompt: str) -> str:
    full_prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"

    result = subprocess.run(
        ["ollama", "run", MODEL_NAME],
        input=full_prompt,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    if result.returncode != 0:
        raise Exception(f"Ollama error: {result.stderr}")

    return result.stdout.strip()


# ---------------------------------------------------------------------------
# OUTPUT CLEANING
# ---------------------------------------------------------------------------

def strip_code_fences(raw: str) -> str:
    """Remove markdown ```json ... ``` wrappers."""
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    return raw.strip("`").strip()


def strip_json_comments(raw: str) -> str:
    """
    Remove JavaScript-style inline comments from JSON.
    Handles:   "key": value,  // some comment
    Also:      "key": value   /* block comment */
    """
    # Single-line comments: // ...  (only outside quoted strings)
    raw = re.sub(r'(?<!["\w])//.*', '', raw)
    # Block comments: /* ... */
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
    return raw


def sanitize_arithmetic_values(raw: str) -> str:
    """
    Replace JSON values that contain arithmetic expressions or
    unparseable garbage with null.

    Targets lines like:
        "other_allowances": 3592.00 + 4gs4.oo - 1800.00,
        "net_salary": 40500 - 4229,
        "gross": gross_salary - deductions,

    Strategy: find JSON value positions that are NOT valid
    (number / string / null / true / false / array / object)
    and contain an operator, then replace the whole value with null.
    """
    def replace_bad_value(m):
        key   = m.group(1)   # "key":
        value = m.group(2)   # the raw value text (before comma/newline)

        # A clean value is: null, true, false, a quoted string,
        # a plain number (int or float, optionally negative), or starts { / [
        clean = value.strip().rstrip(',')
        is_clean = bool(re.fullmatch(
            r'null|true|false|"[^"]*"|-?\d+(\.\d+)?|\[.*\]|\{.*\}',
            clean,
            re.DOTALL
        ))

        if is_clean:
            return m.group(0)   # leave untouched

        # Has arithmetic operator outside a string → replace with null
        has_op = bool(re.search(r'[\d\w]\s*[+\-*/]\s*[\d\w]', clean))
        if has_op:
            # Preserve trailing comma if present
            trailing_comma = ',' if value.rstrip().endswith(',') else ''
            return f'{key} null{trailing_comma}'

        return m.group(0)

    # Match  "key": <anything up to newline or end of object>
    pattern = r'("[\w_]+"\s*:\s*)([^\n\]}"\']+)'
    return re.sub(pattern, replace_bad_value, raw)


def has_arithmetic_expression(raw: str) -> bool:
    """
    Check whether the cleaned JSON (after sanitization) still contains
    bare arithmetic in value positions.

    Strips quoted strings first to avoid false positives from dates,
    PAN numbers, account numbers, etc.
    """
    without_strings = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', raw)

    patterns = [
        r'\d+\s*\+\s*\d+',    # addition
        r'\d+\s*\*\s*\d+',    # multiplication
        r'\d+\s*/\s*\d+',     # division
        r'\d+\s+-\s+\d+',     # subtraction (spaces required on both sides)
    ]

    return any(re.search(p, without_strings) for p in patterns)


# ---------------------------------------------------------------------------
# FULL CLEANING PIPELINE
# ---------------------------------------------------------------------------

def clean_llm_output(raw: str) -> str:
    """
    Multi-step cleaning pipeline:
    1. Strip markdown code fences
    2. Strip JSON comments  (// and /* */)
    3. Replace arithmetic value expressions with null
    """
    raw = strip_code_fences(raw)
    raw = strip_json_comments(raw)
    raw = sanitize_arithmetic_values(raw)
    return raw


# ---------------------------------------------------------------------------
# EXTRACTION ENTRY POINT
# ---------------------------------------------------------------------------

def extract_financial_data(text: str, doc_type: str = "salary_slip") -> dict:
    """
    Extract structured financial data from raw document text.

    Parameters
    ----------
    text     : Raw text from pdfplumber / Tesseract OCR
    doc_type : One of "salary_slip", "bank_statement", "utility_bill",
               "bureau_report", "unknown"

    Returns
    -------
    dict : Parsed and validated JSON from LLM
    """
    prompt = build_extraction_prompt(doc_type, text[:10000])
    raw    = call_llm(prompt["system"], prompt["user"])

    print("\n========== LLM RAW RESPONSE ==========")
    print(raw)
    print("=======================================\n")

    cleaned = clean_llm_output(raw)

    # --- Attempt 1: parse after cleaning ---
    try:
        result = json.loads(cleaned)
        print("✓ JSON parsed successfully after cleaning.")
        return result

    except json.JSONDecodeError as e:
        print(f"\n⚠ JSON parse failed after cleaning: {e}")
        print(f"Cleaned output:\n{cleaned}\n")

    # --- Attempt 2: repair via LLM ---
    print("↺ Attempting LLM repair...")

    repair_prompt = build_repair_prompt(
        validation_errors=[str(e)],
        broken_json=cleaned,
        document_text=text[:5000],
        schema_json=_get_schema_hint(doc_type),
    )

    repaired_raw     = call_llm(repair_prompt["system"], repair_prompt["user"])
    repaired_cleaned = clean_llm_output(repaired_raw)

    print("\n========== LLM REPAIR RESPONSE ==========")
    print(repaired_raw)
    print("==========================================\n")

    # Final arithmetic check on repaired output
    if has_arithmetic_expression(repaired_cleaned):
        raise ValueError(
            "LLM repair response still contains arithmetic expressions. "
            "Cannot safely extract data from this document."
        )

    try:
        result = json.loads(repaired_cleaned)
        print("✓ JSON parsed successfully after repair.")
        return result

    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM repair failed to produce valid JSON: {e}\n"
            f"Repaired output:\n{repaired_cleaned}"
        )


# ---------------------------------------------------------------------------
# SCHEMA HINTS (for repair prompt)
# ---------------------------------------------------------------------------

def _get_schema_hint(doc_type: str) -> str:
    hints = {
        "salary_slip": (
            '{"employee_name": null, "employee_id": null, "employer": null, '
            '"designation": null, "department": null, "salary_month": null, '
            '"salary_date": null, "gross_salary": null, "basic_salary": null, '
            '"hra": null, "other_allowances": null, "deductions": null, '
            '"pf_deduction": null, "professional_tax": null, "tds": null, '
            '"net_salary": null, "bank_account": null, "pan": null}'
        ),
        "bank_statement": (
            '{"account_holder_name": null, "account_number": null, '
            '"ifsc_code": null, "bank_name": null, "branch": null, '
            '"statement_period": {"from": null, "to": null}, '
            '"opening_balance": null, "closing_balance": null, "transactions": []}'
        ),
        "utility_bill": (
            '{"consumer_name": null, "consumer_number": null, '
            '"service_address": null, "utility_type": null, "provider": null, '
            '"bill_number": null, "bill_date": null, "due_date": null, '
            '"billing_period": {"from": null, "to": null}, '
            '"amount_due": null, "previous_dues": null, "current_charges": null, '
            '"total_amount": null, "payment_status": null, "payment_date": null}'
        ),
        "bureau_report": (
            '{"bureau_name": null, "report_date": null, "consumer_name": null, '
            '"pan": null, "date_of_birth": null, "credit_score": null, '
            '"total_accounts": null, "active_accounts": null, '
            '"closed_accounts": null, "overdue_accounts": null, '
            '"total_outstanding": null, "total_credit_limit": null, '
            '"enquiries_last_6m": null, "enquiries_last_12m": null, "accounts": []}'
        ),
    }
    return hints.get(doc_type, '{}')