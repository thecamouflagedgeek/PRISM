import re

DATE_PATTERN = r"\d{2}[/-]\d{2}[/-]\d{2,4}"
AMOUNT_PATTERN = r"[\d,]+\.\d{2}"

def clean_amount(value):
    if not value:
        return None
    value=str(value)
    value=value.replace(",", "")

    value=re.sub(r"[^\d.]", "", value)
    try:
        return float(value)
    except:
        return None
