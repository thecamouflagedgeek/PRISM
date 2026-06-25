"""
PRISM – prompts.py
==================
All LLM prompt templates for:
  - Stage 4  : AI Extraction Agent  (Qwen 2.5 via Ollama)
  - Stage 11 : Explainability Agent (Qwen 2.5 via Ollama)

RULES enforced across ALL extraction prompts
---------------------------------------------
1. Return STRICT JSON only – no markdown, no prose, no code fences.
2. NEVER perform arithmetic. Copy numeric values exactly as they appear.
3. NEVER derive or compute fields (e.g. net = gross - deductions).
4. NEVER return expressions like "40500 - 4229" or "approximately 36271".
5. If a field is not found, use null – never guess or hallucinate.
6. Do not add fields that are not in the schema.
"""

# ---------------------------------------------------------------------------
# SALARY SLIP EXTRACTION
# ---------------------------------------------------------------------------

SALARY_SLIP_SYSTEM = """You are a document data-extraction engine. \
Your only job is to read salary slip text and output a single JSON object. \
You do NOT calculate, derive, or reason. You copy values exactly as printed. \
Return ONLY the JSON object. No markdown. No explanation. No code fences."""

SALARY_SLIP_USER_TEMPLATE = """Extract information from the salary slip text below.

STRICT RULES:
- Output ONLY a valid JSON object.
- Copy every numeric value EXACTLY as it appears in the document.
- Do NOT subtract, add, or compute any value.
- Do NOT return arithmetic expressions.
- Set missing fields to null.

REQUIRED SCHEMA:
{{
  "employee_name":   string | null,
  "employee_id":     string | null,
  "employer":        string | null,
  "designation":     string | null,
  "department":      string | null,
  "salary_month":    string | null,   // e.g. "2025-10"
  "salary_date":     string | null,   // ISO 8601 if available e.g. "2025-10-01"
  "gross_salary":    number | null,   // copy exactly, never compute
  "basic_salary":    number | null,
  "hra":             number | null,
  "other_allowances":number | null,
  "deductions":      number | null,   // total deductions as printed, never compute
  "pf_deduction":    number | null,
  "professional_tax":number | null,
  "tds":             number | null,
  "net_salary":      number | null,   // copy exactly as printed; null if not printed
  "bank_account":    string | null,
  "pan":             string | null
}}

SALARY SLIP TEXT:
{document_text}

Return ONLY the JSON object."""


# ---------------------------------------------------------------------------
# BANK STATEMENT EXTRACTION
# ---------------------------------------------------------------------------

BANK_STATEMENT_SYSTEM = """You are a document data-extraction engine. \
Your only job is to read bank statement text and output a single JSON object. \
You do NOT calculate, derive, or reason. You copy values exactly as printed. \
Return ONLY the JSON object. No markdown. No explanation. No code fences."""

BANK_STATEMENT_USER_TEMPLATE = """Extract information from the bank statement text below.

STRICT RULES:
- Output ONLY a valid JSON object.
- Copy every numeric value EXACTLY as it appears in the document.
- Do NOT subtract, add, or compute any value.
- Do NOT return arithmetic expressions.
- Set missing fields to null.
- For transactions, copy each entry; do NOT summarise or aggregate.

REQUIRED SCHEMA:
{{
  "account_holder_name": string | null,
  "account_number":      string | null,
  "ifsc_code":           string | null,
  "bank_name":           string | null,
  "branch":              string | null,
  "statement_period":    {{
                           "from": string | null,   // ISO 8601
                           "to":   string | null
                         }},
  "opening_balance":     number | null,
  "closing_balance":     number | null,
  "transactions": [
    {{
      "date":        string | null,   // ISO 8601 if parseable, else as-is
      "description": string | null,
      "debit":       number | null,
      "credit":      number | null,
      "balance":     number | null,
      "mode":        string | null    // UPI, IMPS, NACH, NEFT, ATM, CHQ, etc.
    }}
  ]
}}

BANK STATEMENT TEXT:
{document_text}

Return ONLY the JSON object."""


# ---------------------------------------------------------------------------
# UTILITY BILL EXTRACTION
# ---------------------------------------------------------------------------

UTILITY_BILL_SYSTEM = """You are a document data-extraction engine. \
Your only job is to read utility bill text and output a single JSON object. \
You do NOT calculate, derive, or reason. You copy values exactly as printed. \
Return ONLY the JSON object. No markdown. No explanation. No code fences."""

UTILITY_BILL_USER_TEMPLATE = """Extract information from the utility bill text below.

STRICT RULES:
- Output ONLY a valid JSON object.
- Copy every numeric value EXACTLY as it appears in the document.
- Do NOT subtract, add, or compute any value.
- Do NOT return arithmetic expressions.
- Set missing fields to null.

REQUIRED SCHEMA:
{{
  "consumer_name":     string | null,
  "consumer_number":   string | null,
  "service_address":   string | null,
  "utility_type":      string | null,   // ELECTRICITY, WATER, GAS, BROADBAND, etc.
  "provider":          string | null,
  "bill_number":       string | null,
  "bill_date":         string | null,   // ISO 8601
  "due_date":          string | null,   // ISO 8601
  "billing_period":    {{
                         "from": string | null,
                         "to":   string | null
                       }},
  "amount_due":        number | null,
  "previous_dues":     number | null,
  "current_charges":   number | null,
  "total_amount":      number | null,   // copy as printed; null if not printed
  "payment_status":    string | null,   // PAID / UNPAID / PARTIALLY PAID
  "payment_date":      string | null
}}

UTILITY BILL TEXT:
{document_text}

Return ONLY the JSON object."""


# ---------------------------------------------------------------------------
# BUREAU REPORT EXTRACTION
# ---------------------------------------------------------------------------

BUREAU_REPORT_SYSTEM = """You are a document data-extraction engine. \
Your only job is to read credit bureau report text and output a single JSON object. \
You do NOT calculate, derive, or reason. You copy values exactly as printed. \
Return ONLY the JSON object. No markdown. No explanation. No code fences."""

BUREAU_REPORT_USER_TEMPLATE = """Extract information from the bureau report text below.

STRICT RULES:
- Output ONLY a valid JSON object.
- Copy every numeric value EXACTLY as it appears in the document.
- Do NOT subtract, add, or compute any value.
- Do NOT return arithmetic expressions.
- Set missing fields to null.

REQUIRED SCHEMA:
{{
  "bureau_name":         string | null,   // CIBIL, EXPERIAN, EQUIFAX, CRIF
  "report_date":         string | null,
  "consumer_name":       string | null,
  "pan":                 string | null,
  "date_of_birth":       string | null,
  "credit_score":        number | null,   // as printed
  "total_accounts":      number | null,
  "active_accounts":     number | null,
  "closed_accounts":     number | null,
  "overdue_accounts":    number | null,
  "total_outstanding":   number | null,
  "total_credit_limit":  number | null,
  "enquiries_last_6m":   number | null,
  "enquiries_last_12m":  number | null,
  "accounts": [
    {{
      "lender":           string | null,
      "account_type":     string | null,  // HOME_LOAN, PERSONAL_LOAN, CC, AUTO, etc.
      "account_number":   string | null,
      "opened_date":      string | null,
      "status":           string | null,  // ACTIVE, CLOSED, WRITTEN_OFF, etc.
      "sanctioned_amount":number | null,
      "current_balance":  number | null,
      "overdue_amount":   number | null,
      "emi_amount":       number | null,
      "dpd_current":      number | null,  // days past due, as printed
      "dpd_history":      string | null   // e.g. "000000000000" as printed
    }}
  ]
}}

BUREAU REPORT TEXT:
{document_text}

Return ONLY the JSON object."""


# ---------------------------------------------------------------------------
# UNKNOWN / GENERIC FINANCIAL DOCUMENT EXTRACTION
# ---------------------------------------------------------------------------

GENERIC_SYSTEM = """You are a document data-extraction engine. \
Your only job is to read financial document text and output a single JSON object \
containing every structured financial data point you can identify. \
You do NOT calculate, derive, or reason. You copy values exactly as printed. \
Return ONLY the JSON object. No markdown. No explanation. No code fences."""

GENERIC_USER_TEMPLATE = """Extract all structured financial information from the document below.

STRICT RULES:
- Output ONLY a valid JSON object.
- Use snake_case keys.
- Copy every numeric value EXACTLY as it appears.
- Do NOT compute, derive, or return arithmetic expressions.
- Set missing or ambiguous fields to null.
- Include all dates, amounts, names, identifiers, and addresses present.

DOCUMENT TEXT:
{document_text}

Return ONLY the JSON object."""


# ---------------------------------------------------------------------------
# STAGE 11 – EXPLAINABILITY AGENT
# ---------------------------------------------------------------------------

EXPLAINABILITY_SYSTEM = """You are a credit risk explainability engine. \
You receive a borrower's financial features, their computed risk score, and \
reason codes generated by a logistic regression model. \
Your job is to translate these into plain English sentences that a loan officer \
or the borrower can understand. \
Be factual, concise, and avoid jargon. Do not speculate beyond what the data says."""

EXPLAINABILITY_USER_TEMPLATE = """Generate plain-English explanations for the credit risk assessment below.

RISK SCORE     : {risk_score}  (scale 300–900)
RISK BAND      : {risk_band}
PROB. DEFAULT  : {probability_of_default}

FINANCIAL FEATURES:
{features_json}

REASON CODES (model-generated):
{reason_codes_json}

INSTRUCTIONS:
1. Write one sentence per reason code that explains its impact on the score.
2. Clearly state whether each factor had a POSITIVE or NEGATIVE impact.
3. Use simple language — avoid technical terms unless essential.
4. Do NOT mention probability values or WoE scores in the output.
5. Return a JSON object in this exact structure:

{{
  "summary": "<2-3 sentence overall summary of the borrower's credit profile>",
  "explanations": [
    {{
      "reason_code": "<reason code exactly as given>",
      "impact":      "POSITIVE" | "NEGATIVE" | "NEUTRAL",
      "explanation": "<one plain-English sentence>"
    }}
  ],
  "recommendation": "<optional 1-sentence guidance for the borrower or officer>"
}}

Return ONLY the JSON object. No markdown. No code fences."""


# ---------------------------------------------------------------------------
# REPAIR FALLBACK PROMPT
# (used when Stage 5 Pydantic validation fails and re-extraction is needed)
# ---------------------------------------------------------------------------

REPAIR_SYSTEM = """You are a JSON repair engine. \
You receive broken or incomplete JSON extracted from a financial document, \
along with the original document text. \
Your only job is to return a corrected, complete JSON object. \
You do NOT calculate or derive values. Copy all numbers exactly as they appear \
in the original document text. \
Return ONLY valid JSON. No markdown. No code fences. No explanation."""

REPAIR_USER_TEMPLATE = """The following JSON extraction failed validation.

VALIDATION ERRORS:
{validation_errors}

BROKEN JSON:
{broken_json}

ORIGINAL DOCUMENT TEXT:
{document_text}

REQUIRED SCHEMA:
{schema_json}

Fix the JSON so it passes validation. \
Copy all numeric values exactly from the document. \
Do NOT compute or evaluate any expressions. \
Return ONLY the corrected JSON object."""


# ---------------------------------------------------------------------------
# PROMPT BUILDER HELPERS
# ---------------------------------------------------------------------------

def build_extraction_prompt(doc_type: str, document_text: str) -> dict:
    """
    Returns {"system": str, "user": str} for the given document type.

    doc_type values (match Stage 3 classifier output):
        "salary_slip", "bank_statement", "utility_bill",
        "bureau_report", "unknown"
    """
    _map = {
        "salary_slip": (SALARY_SLIP_SYSTEM, SALARY_SLIP_USER_TEMPLATE),
        "bank_statement": (BANK_STATEMENT_SYSTEM, BANK_STATEMENT_USER_TEMPLATE),
        "utility_bill": (UTILITY_BILL_SYSTEM, UTILITY_BILL_USER_TEMPLATE),
        "bureau_report": (BUREAU_REPORT_SYSTEM, BUREAU_REPORT_USER_TEMPLATE),
        "unknown": (GENERIC_SYSTEM, GENERIC_USER_TEMPLATE),
    }

    system_prompt, user_template = _map.get(doc_type, (GENERIC_SYSTEM, GENERIC_USER_TEMPLATE))

    return {
        "system": system_prompt,
        "user": user_template.format(document_text=document_text),
    }


def build_explainability_prompt(
    risk_score: int,
    risk_band: str,
    probability_of_default: float,
    features: dict,
    reason_codes: list,
) -> dict:
    """
    Returns {"system": str, "user": str} for the explainability agent.
    """
    import json

    return {
        "system": EXPLAINABILITY_SYSTEM,
        "user": EXPLAINABILITY_USER_TEMPLATE.format(
            risk_score=risk_score,
            risk_band=risk_band,
            probability_of_default=probability_of_default,
            features_json=json.dumps(features, indent=2, ensure_ascii=False),
            reason_codes_json=json.dumps(reason_codes, indent=2, ensure_ascii=False),
        ),
    }


def build_repair_prompt(
    validation_errors: list,
    broken_json: str,
    document_text: str,
    schema_json: str,
) -> dict:
    """
    Returns {"system": str, "user": str} for the repair fallback agent.
    """
    return {
        "system": REPAIR_SYSTEM,
        "user": REPAIR_USER_TEMPLATE.format(
            validation_errors="\n".join(str(e) for e in validation_errors),
            broken_json=broken_json,
            document_text=document_text,
            schema_json=schema_json,
        ),
    }