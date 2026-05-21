from datetime import datetime

CONFIG = {
    "confidence_threshold": 0.60,
    "bank_fields": {
        "date": (True, "date", None, None),
        "amount": (True, "float", 0.01, 10_000_000),
        "type": (True, "cr_dr", None, None),
        "narration": (True, "str", None, None),
        "closing_balance": (False, "float", -500_000, 50_000_000),
    },
    "salary_fields": {
        "gross_salary": (True, "float", 1000, 10_000_000),
        "net_salary": (True, "float", 500, 10_000_000),
        "pf": (False, "float", 0, 500_000),
    },
    "utility_fields": {
        "bill_amount": (True, "float", 0.01, 500_000),
    },
    "date_formats": [
        "%d/%m/%y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ],

    "date_min": datetime(2000, 1, 1),
    "date_max": datetime(2030, 12, 31),
}