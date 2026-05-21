from ingestion.parsers.bank_parser import BankParser
from ingestion.parsers.salary_parser import SalaryParser
from ingestion.parsers.utility_parser import UtilityParser


def process_document(file_path: str, doc_type: str):

    parsers = {
        "bank": BankParser(),
        "salary": SalaryParser(),
        "utility": UtilityParser()
    }

    parser = parsers.get(doc_type)

    if not parser:
        raise ValueError(f"Unsupported document type: {doc_type}")
    #Extract raw data
    raw_df = parser.extract(file_path)
    #Transform
    transformed_df = parser.transform(raw_df)
    #Validate
    parser.validate(transformed_df)
    return transformed_df