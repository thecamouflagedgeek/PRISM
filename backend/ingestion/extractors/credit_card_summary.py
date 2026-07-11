# ingestion/extractors/credit_card_summary.py
import re
from ingestion.extractors.table import clean_amount

def extract_credit_card_summary(text: str) -> dict:
    summary = {}

    m = re.search(r"Sanctioned Credit Limit:\s*₹?\s*([\d,]+)", text)
    if m:
        summary["credit_limit"] = clean_amount(m.group(1).replace(",", ""))

    # Minimum Amount Due and Total Amount Due appear together on one line,
    # e.g. '1,537.15 ₹ 25,066.80DR' — two amounts, second may have DR/CR glued on
    m = re.search(r"([\d,]+\.\d{2})\s*₹?\s*([\d,]+\.\d{2})\s*(DR|CR)?", text)
    if m:
        summary["minimum_amount_due"] = clean_amount(m.group(1).replace(",", ""))
        summary["total_amount_due"] = clean_amount(m.group(2).replace(",", ""))

    m = re.search(r"(\d{2}/\d{2}/\d{4})", text[text.find("Payment Due Date"):text.find("Payment Due Date") + 200]) if "Payment Due Date" in text else None
    if m:
        summary["payment_due_date"] = m.group(1)

    # Account Summary row: Opening, Payment/Credits, Purchases/Debits, Closing — in that order
    m = re.search(
        r"₹\s*([\d,]+\.\d{2})\s*₹\s*([\d,]+\.\d{2})\s*₹\s*([\d,]+\.\d{2})\s*₹\s*([\d,]+\.\d{2})",
        text
    )
    if m:
        summary["opening_balance"] = clean_amount(m.group(1).replace(",", ""))
        summary["payments_credits"] = clean_amount(m.group(2).replace(",", ""))
        summary["purchases_debits"] = clean_amount(m.group(3).replace(",", ""))
        summary["closing_balance"] = clean_amount(m.group(4).replace(",", ""))

    return summary