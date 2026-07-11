from ingestion.parsers.base_parser import BaseParser
from ingestion.universal_pipeline import UniversalParser
from ingestion.universal_pipeline import parse_statement_summary
import pandas as pd
import logging

logger = logging.getLogger("prism.extraction")

MIN_TRANSACTIONS_REQUIRED = 2  # tune based on typical real statement periods


class BankParser(BaseParser):
    def __init__(self, ocr_engine=None):
        self.universal_parser = UniversalParser(ocr_engine)

    def extract(self, file_path: str, password: str | None = None):
        doc_type, mapped_data, raw_text = self.universal_parser.process(file_path,password=password)
        summary = parse_statement_summary(raw_text)
        self._validate_extraction_quality(mapped_data,raw_text=raw_text,statement_summary=summary)
        print("BANK PARSER OUTPUT")
        print(mapped_data.head(20))
        print(mapped_data.dtypes)
        print(mapped_data.columns.tolist())
        return mapped_data
    
    def _validate_extraction_quality(self,df: pd.DataFrame, raw_text:str ="",statement_days:int = 30,statement_summary:dict =None):
        issues =[]
        if df is None or df.empty:
            raise ExtractionQualityError(["No transactions could be extracted"])
        
        summary=None
        try:
            summary = parse_statement_summary(raw_text)
            self._validate_extraction_quality(mapped_data,raw_text=raw_text,statement_summary=summary)
        except Exception:
            summary=None
        
        if summary:
            validation_score = 0
            total_checks = 0
            if getattr(summary,"transaction_count",None) is not None:
                total_checks +=1
                if abs(len(df) - summary.transaction_count) <= 1:
                    validation_score +=1
                else:
                    issues.append(f"Transaction count mismatch: extracted {len(df)} vs summary {summary.transaction_count}")
                
            if(getattr(summary,"credit_count",None) is not None and "type" in df.columns):
                total_checks +=1
                parsed_debit = (df["type"].astype(str).str.upper().eq("DR").sum())
                if abs(parsed_debit - summary.debit_count) <=1 :
                    validation_score +=1
                else:
                    issues.append(f"Debit count mismatch: extracted {parsed_debit} vs summary {summary.debit_count}")
            
            if(getattr(summary,"opening_balance",None) is not None and "closing_balance" in df.columns):
                total_checks +=1
                parsed_open = df.iloc[0]["closing_balance"]
                if abs(parsed_open - summary.opening_balance) <= 1:
                    validation_score +=1
                else:
                    issues.append(f"Opening balance mismatch: extracted {parsed_open} vs summary {summary.opening_balance}")
            if(getattr(summary,"closing_balance",None) is not None and "closing_balance" in df.columns):
                total_checks +=1
                parsed_close = df.iloc[-1]["closing_balance"]
                if abs(parsed_close - summary.closing_balance) <= 1:
                    validation_score +=1
                else:
                    issues.append(f"Closing balance mismatch: extracted {parsed_close} vs summary {summary.closing_balance}")
            if total_checks > 0:
                confidence = validation_score / total_checks
                if confidence < 0.70:
                    logger.warning("fSummary cross-check failed"f"({validation_score}/{total_checks})")
                    raise ExtractionQualityError(issues)
        else:
            required_colums=["date","amount","closing_balance"]
            missing_columns = [col for col in required_colums if col not in df.columns]
            if missing_columns:
                issues.append(f"Missing required columns: {missing_columns}")
        
        if "closing_balance" in df.columns:
            for i in range(1,len(df)):
                prev_bal = df.iloc[i-1]["closing_balance"]
                curr_bal = df.iloc[i]["closing_balance"]
                amt = df.iloc[i]["amount"]
                if pd.notna(prev_bal) and pd.notna(curr_bal) and pd.notna(amt):
                    implied_delta = abs(curr_bal - prev_bal)
                    tolerance=max(abs(amt)*0.5,100)
                    if(implied_delta > 0 and abs(implied_delta - abs(amt)) > tolerance):
                        issues.append(f"Transaction amount mismatch at row {i}: implied delta {implied_delta} vs extracted amount {curr_amt}")
        
        if issues:
            logger.warning(f"Extraction quality issues detected: {issues}")

    def transform(self, data):
        # The universal pipeline already mapped it to the canonical schema
        return data

    def validate(self, df):
        # Structural validation already performed by ValidationPipeline in UniversalParser
        return True


class ExtractionQualityError(Exception):
    """Raised when extracted data fails plausibility checks and should not be scored."""
    def __init__(self, issues):
        self.issues = issues
        super().__init__(f"Extraction quality insufficient: {issues}")