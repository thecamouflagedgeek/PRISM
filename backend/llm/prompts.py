SALARY_PROMPT = """
You are a financial document extraction engine.

Return ONLY valid JSON.

Extract salary information and return ONLY valid JSON.

{{
    "employer": "",
    "gross_salary": 0,
    "net_salary": 0,
    "salary_date": "",
    "employee_name": ""
}}

Rules:
- Return only JSON.
- No markdown.
- No explanation.
- If a value is missing use null.

DOCUMENT:

{text}
"""
