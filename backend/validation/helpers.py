import pandas as pd
from datetime import datetime
from validation.config import CONFIG

def try_parse_date(value):
    if pd.isna(value) or value is None:
        return None
    value = str(value).strip()
    
    for fmt in CONFIG["date_formats"]:
        try:
            return datetime.strptime(value, fmt)
        except:
            continue
    return None


def is_valid_float(value):
    try:
        float(str(value).replace(",", ""))
        return True
    except:
        return False

def is_valid_cr_dr(value):
    return str(value).upper() in ["CR", "DR"]

def is_valid_str(value):
    return value is not None and str(value).strip() != ""