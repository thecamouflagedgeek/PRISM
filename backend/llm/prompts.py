SALARY_PROMPT = """
You are a financial document extraction engine.

Return ONLY valid JSON.

Extract:

{
    "employer": null,
    "gross_salary": null,
    "net_salary": null,
    "pf": null,
    "pay_period": null
}

Rules:
- Return only JSON.
- No markdown.
- No explanation.
- If a value is missing use null.

DOCUMENT:

{text}
"""
