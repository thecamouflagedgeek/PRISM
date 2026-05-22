def parse_document(file_path, doc_type):
    from ingestion.parsers.bank_parser import BankParser
    from ingestion.parsers.salary_parser import SalaryParser
    from ingestion.parsers.utility_parser import UtilityParser

    parsers = {
        "bank": BankParser(),
        "salary": SalaryParser(),
        "utility": UtilityParser()
    }

    parser = parsers[doc_type]

    raw = parser.extract(file_path)
    df = parser.transform(raw)
    valid = parser.validate(df)

    confidence = 1.0
    if isinstance(valid, dict):
        if not valid.get("valid", True):
            confidence -= 0.3

    return df, max(0.0, confidence)