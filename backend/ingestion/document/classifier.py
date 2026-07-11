# ingestion/document/classifier.py

CREDIT_CARD_DISCRIMINATIVE = [
    "credit card statement", "card statement", "minimum amount due",
    "total amount due", "sanctioned credit limit", "available credit limit",
    "payment due date", "cash limit", "reward points", "finance charges",
    "card no", "billed finance charges",
]

def is_credit_card_statement(text: str) -> bool:
    text_lower = text.lower()
    hits = sum(1 for kw in CREDIT_CARD_DISCRIMINATIVE if kw in text_lower)
    return hits >= 3  # conservative — avoids false-positives on savings statements