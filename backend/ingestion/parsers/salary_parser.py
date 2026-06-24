import re
import json
import pandas as pd
class SalaryParser:

    def __init__(self, ocr_engine):
        self.ocr = ocr_engine

    def parse(self, image_path: str):

        if hasattr(self.ocr, "extract_text_from_pdf"):
            full_text = self.ocr.extract_text_from_pdf(image_path)
        
        elif hasattr(self.ocr, "predict"):
            results = self.ocr.predict(image_path)
            full_text = ""
            for page in results:
                try:
                    full_text += "\n".join(page.get("rec_texts", []))
                except:
                    full_text += str(page)
        else:
            raise ValueError("Unsupported OCR engine provided")
        
        if hasattr(self.ocr, "clean_text"):
            full_text = self.ocr.clean_text(full_text)
            
        if not full_text.strip():
            return pd.DataFrame([{"employer": None,"pay_period": None,"gross_salary": 0,"net_salary": 0}])
        
        salary_data = {}

        lines = [
            line.strip()
            for line in full_text.split("\n")
            if line.strip()
        ]

        ignore_words = [
            "payslip","salary","month","employee","name",
            "designation","pan","gpf","pran","earnings",
            "deductions","account","office","level","index",
            "empid","pay slip"
        ]

        candidates = []

        for line in lines[:25]:
            lower = line.lower()

            if any(word in lower for word in ignore_words):
                continue

            if re.search(r"\d", line):
                continue

            if len(line) < 5:
                continue

            candidates.append(line)

        priority_words = [
            "limited","ltd","bank","corp","corporation",
            "services","solutions","technologies","industries",
            "post","company"
        ]

        best = None
        best_score = -1

        for line in candidates:
            score = 0

            for word in priority_words:
                if word in line.lower():
                    score += 5

            score += len(line) / 20

            if score > best_score:
                best_score = score
                best = line

        salary_data["employer"] = best

        # ---- pay period ----
        period_match = re.search(
            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}",
            full_text,
            re.IGNORECASE
        )

        salary_data["pay_period"] = period_match.group(0) if period_match else None

        # ---- aliases ----
        salary_aliases = {
            "basic_pay": ["basic pay","basic salary","basic"],
            "da": ["dearness allowance","da"],
            "hra": ["house rent allowance","hra"],
            "transport_allowance": ["transport allowance","conveyance allowance"],
            "nps_contribution": ["nps contribution"]
        }

        def extract_amount_after_label(labels):
            for label in labels:
                pattern = rf"{re.escape(label)}\s*[\n\r ]+([\d,]+\.\d+)"
                match = re.search(pattern, full_text, re.IGNORECASE)

                if match:
                    try:
                        return float(match.group(1).replace(",", ""))
                    except:
                        pass
            return None

        for field, aliases in salary_aliases.items():
            salary_data[field] = extract_amount_after_label(aliases)

        # ---- net salary ----
        salary_data["net_salary"] = None

        net_patterns = [
            r"take\s*home\s*pay.*?([\d,]+\.\d+)",
            r"net\s*salary.*?([\d,]+\.\d+)",
            r"net\s*pay.*?([\d,]+\.\d+)"
        ]

        for pattern in net_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                salary_data["net_salary"] = float(match.group(1).replace(",", ""))
                break

        # ---- gross ----
        totals = re.findall(r"Total\s*[\n\r ]+([\d,]+\.\d+)", full_text, re.IGNORECASE)

        if totals:
            salary_data["gross_salary"] = float(totals[0].replace(",", ""))
        else:
            gross = 0
            for field in ["basic_pay","da","hra","transport_allowance"]:
                if salary_data.get(field):
                    gross += salary_data[field]

            if gross > 0:
                salary_data["gross_salary"] = round(gross, 2)

        # ---- derived metrics ----
        if salary_data.get("gross_salary") and salary_data.get("net_salary"):

            salary_data["net_to_gross_ratio"] = round(
                salary_data["net_salary"] / salary_data["gross_salary"], 4
            )

            salary_data["deduction_amount"] = round(
                salary_data["gross_salary"] - salary_data["net_salary"], 2
            )

            salary_data["salary_consistency_score"] = 1
        else:
            salary_data["salary_consistency_score"] = 0

        