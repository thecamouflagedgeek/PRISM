from ingestion.parsers.base_parser import BaseParser
from ingestion.universal_pipeline import UniversalParser

class BankParser(BaseParser):
    def __init__(self, ocr_engine=None):
        self.universal_parser = UniversalParser(ocr_engine)
        self.metadata = {}

    def extract(self, file_path: str, password: str = None):
        from ingestion.bank_layout import extract_native_table
        from ingestion.universal_pipeline import TextExtractor
        from ingestion.identity import extract_person_name
        import fitz
        native = extract_native_table(file_path, password)
        if native is not None:
            transactions, diagnostics = native
            if diagnostics['rejected_rows']:
                raise ValueError('REVIEW_REQUIRED: transaction columns could not be reconstructed reliably')
            with fitz.open(file_path) as document:
                if document.needs_pass: document.authenticate(password or '')
                text = '\n\f\n'.join(page.get_text() for page in document)
            self.metadata = {**TextExtractor._safe_source_metadata(text, 'native_coordinates', False, file_path),
                **diagnostics, 'document_type':'BANK', 'valid_transaction_coverage':1.0,
                'holder_name':extract_person_name(text)}
            return transactions
        # We process everything in transform to respect the base_parser interface,
        # or we just process it here and pass the df to transform.
        doc_type, mapped_data = self.universal_parser.process(file_path, password=password)
        self.metadata = dict(self.universal_parser.last_metadata)
        with fitz.open(file_path) as document:
            if document.needs_pass: document.authenticate(password or '')
            source_text = '\n\f\n'.join(page.get_text() for page in document)
        self.metadata['holder_name'] = extract_person_name(source_text)
        if doc_type != "BANK":
            raise ValueError(f"Expected BANK document, but classified as {doc_type}")
        return mapped_data

    def transform(self, data):
        # The universal pipeline already mapped it to the canonical schema
        return data

    def validate(self, df):
        # Validation was already performed by ValidationPipeline in UniversalParser
        return True
