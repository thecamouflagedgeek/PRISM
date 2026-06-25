"""
PRISM Specialised Feature Extraction Engines
Three separate extractors — Bank, Salary, Utility.
Each consumes a CanonicalDocument and produces the exact feature dict
expected by the existing PRISM risk scoring engine.

DO NOT merge these into one parser.
DO NOT modify the output keys — they feed directly into feature engineering.
"""

import logging
import statistics
from dataclasses import dataclass
from typing import Optional

from schema_mapper.canonical_mapper import CanonicalDocument

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared result container
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    features: dict
    confidence: float           # 0.0 – 1.0
    entities_found: list[str]
    missing_entities: list[str]
    quality_score: float        # 0.0 – 1.0
    doc_type: str               # "bank" | "salary" | "utility"
    diagnostics: list[str]      # human-readable extraction notes


# ---------------------------------------------------------------------------
# Bank Feature Extractor
# ---------------------------------------------------------------------------

class BankFeatureExtractor:
    """
    Produces the bank feature dict consumed by PRISM feature engineering.

    Required output keys:
        credit_debit_ratio      float
        cashflow_cv             float   (coefficient of variation of monthly cashflow)
        average_monthly_balance float
        minimum_balance         float
        inflow_consistency      float   (0-1)
    """

    REQUIRED_ENTITIES = [
        "credit_amount", "debit_amount", "running_balance",
        "transaction_date",
    ]

    def extract(self, doc: CanonicalDocument) -> ExtractionResult:
        found = []
        missing = []
        diagnostics = []

        credits = doc.credit_amounts
        debits = doc.debit_amounts
        balances = doc.running_balances

        if credits:
            found.append("credit_amount")
        else:
            missing.append("credit_amount")
            diagnostics.append("Credit/deposit values not detected")

        if debits:
            found.append("debit_amount")
        else:
            missing.append("debit_amount")
            diagnostics.append("Debit/withdrawal values not detected")

        if balances:
            found.append("running_balance")
        else:
            missing.append("running_balance")
            diagnostics.append("Running balance not detected")

        if doc.transaction_dates:
            found.append("transaction_date")
        else:
            missing.append("transaction_date")
            diagnostics.append("Transaction dates not detected")

        # ---- Compute features ----
        total_credit = sum(credits) if credits else 0.0
        total_debit = sum(debits) if debits else 0.0

        credit_debit_ratio = (
            total_credit / total_debit if total_debit > 0 else (1.0 if total_credit > 0 else 0.0)
        )

        # Cashflow CV: std/mean of (credit - debit) per period
        # Approximate with available values
        cashflow_cv = self._compute_cashflow_cv(credits, debits)

        average_monthly_balance = statistics.mean(balances) if balances else 0.0
        minimum_balance = min(balances) if balances else 0.0

        # Inflow consistency: fraction of months with at least one credit
        # Approximated from credit count vs date count
        inflow_consistency = self._compute_inflow_consistency(credits, doc.transaction_dates)

        features = {
            "credit_debit_ratio": round(credit_debit_ratio, 4),
            "cashflow_cv": round(cashflow_cv, 4),
            "average_monthly_balance": round(average_monthly_balance, 2),
            "minimum_balance": round(minimum_balance, 2),
            "inflow_consistency": round(inflow_consistency, 4),
        }

        confidence = self._compute_confidence(found, missing, doc)
        quality = len(found) / len(self.REQUIRED_ENTITIES)

        return ExtractionResult(
            features=features,
            confidence=confidence,
            entities_found=found,
            missing_entities=missing,
            quality_score=quality,
            doc_type="bank",
            diagnostics=diagnostics,
        )

    def _compute_cashflow_cv(self, credits: list[float], debits: list[float]) -> float:
        if not credits and not debits:
            return 0.0
        # Use net cashflows
        max_len = max(len(credits), len(debits))
        c = credits + [0.0] * (max_len - len(credits))
        d = debits + [0.0] * (max_len - len(debits))
        net = [ci - di for ci, di in zip(c, d)]
        if len(net) < 2:
            return 0.0
        mean = statistics.mean(net)
        if mean == 0:
            return 1.0
        stdev = statistics.stdev(net)
        return abs(stdev / mean)

    def _compute_inflow_consistency(self, credits: list[float], dates: list[str]) -> float:
        if not credits:
            return 0.0
        # Extract unique months from dates
        unique_months = set()
        for d in dates:
            parts = d.split("/")
            if len(parts) == 3:
                unique_months.add(f"{parts[1]}/{parts[2]}")
        n_months = max(len(unique_months), 1)
        # Count months with credit (approximate: if credits > months, 1.0)
        months_with_credit = min(len(credits), n_months)
        return months_with_credit / n_months

    def _compute_confidence(self, found: list, missing: list, doc: CanonicalDocument) -> float:
        base = len(found) / len(self.REQUIRED_ENTITIES)
        # Boost if we have both credits AND debits
        if "credit_amount" in found and "debit_amount" in found:
            base += 0.1
        # Boost if balances exist
        if "running_balance" in found:
            base += 0.1
        # Penalise if very few transactions
        if len(doc.credit_amounts) + len(doc.debit_amounts) < 3:
            base -= 0.15
        return max(0.0, min(1.0, base))


# ---------------------------------------------------------------------------
# Salary Feature Extractor
# ---------------------------------------------------------------------------

class SalaryFeatureExtractor:
    """
    Produces the salary feature dict consumed by PRISM feature engineering.

    Required output keys:
        gross_salary            float
        net_salary              float
        net_to_gross_ratio      float
        pf_contribution_flag    int     (0 or 1)
        employer_consistency    float   (0-1, proxy: 1.0 if employer found)
    """

    REQUIRED_ENTITIES = [
        "gross_salary", "net_salary", "pay_period",
    ]

    def extract(self, doc: CanonicalDocument) -> ExtractionResult:
        found = []
        missing = []
        diagnostics = []

        gross = doc.gross_salary
        net = doc.net_salary
        pf = doc.pf_contribution
        employer = doc.employer_name

        if gross:
            found.append("gross_salary")
        else:
            missing.append("gross_salary")
            diagnostics.append("Gross salary not detected")

        if net:
            found.append("net_salary")
        else:
            missing.append("net_salary")
            diagnostics.append("Net/take-home salary not detected")

        if doc.pay_period:
            found.append("pay_period")
        else:
            missing.append("pay_period")
            diagnostics.append("Pay period not detected")

        # Validation: net should not exceed gross
        if gross and net and net > gross:
            logger.warning("net_salary (%.2f) > gross_salary (%.2f); swapping.", net, gross)
            gross, net = net, gross

        gross = gross or 0.0
        net = net or 0.0

        net_to_gross_ratio = (net / gross) if gross > 0 else 0.0
        # Sanity bound
        net_to_gross_ratio = max(0.0, min(1.0, net_to_gross_ratio))

        pf_flag = 1 if (pf and pf > 0) else 0
        if pf_flag:
            found.append("pf_contribution")

        employer_consistency = 1.0 if employer else 0.5
        if employer:
            found.append("employer_name")

        features = {
            "gross_salary": round(gross, 2),
            "net_salary": round(net, 2),
            "net_to_gross_ratio": round(net_to_gross_ratio, 4),
            "pf_contribution_flag": pf_flag,
            "employer_consistency": round(employer_consistency, 4),
        }

        confidence = self._compute_confidence(found, missing, gross, net)
        quality = len([e for e in self.REQUIRED_ENTITIES if e in found]) / len(self.REQUIRED_ENTITIES)

        return ExtractionResult(
            features=features,
            confidence=confidence,
            entities_found=found,
            missing_entities=missing,
            quality_score=quality,
            doc_type="salary",
            diagnostics=diagnostics,
        )

    def _compute_confidence(self, found, missing, gross, net) -> float:
        base = 0.0
        if "gross_salary" in found and gross > 0:
            base += 0.45
        if "net_salary" in found and net > 0:
            base += 0.45
        if "pay_period" in found:
            base += 0.05
        if "employer_name" in found:
            base += 0.05
        return min(1.0, base)


# ---------------------------------------------------------------------------
# Utility Feature Extractor
# ---------------------------------------------------------------------------

class UtilityFeatureExtractor:
    """
    Produces the utility feature dict consumed by PRISM feature engineering.

    Required output keys:
        payment_discipline_flag int     (1 = paid on time, 0 = overdue/missed)
        utility_stability       float   (0-1, proxy from bill regularity)
        payment_delay           int     (days overdue; 0 if on time)
        average_bill            float
    """

    REQUIRED_ENTITIES = [
        "bill_amount", "due_date", "payment_status",
    ]

    # Paid-status keywords
    PAID_KEYWORDS = {"paid", "cleared", "received", "settled", "success", "credited"}
    OVERDUE_KEYWORDS = {"overdue", "unpaid", "pending", "due", "outstanding", "not paid"}

    def extract(self, doc: CanonicalDocument) -> ExtractionResult:
        found = []
        missing = []
        diagnostics = []

        bill = doc.bill_amount
        status_raw = (doc.payment_status or "").lower().strip()
        due_date = doc.due_date
        units = doc.units_consumed

        if bill:
            found.append("bill_amount")
        else:
            missing.append("bill_amount")
            diagnostics.append("Bill/payable amount not detected")

        if due_date:
            found.append("due_date")
        else:
            missing.append("due_date")
            diagnostics.append("Due date not detected")

        if status_raw:
            found.append("payment_status")
        else:
            missing.append("payment_status")
            diagnostics.append("Payment status not detected")

        if units:
            found.append("units_consumed")

        # Determine payment discipline
        payment_discipline_flag = self._resolve_payment_flag(status_raw)
        payment_delay = 0 if payment_discipline_flag == 1 else self._estimate_delay(status_raw)

        # Utility stability: 1.0 if paid, 0.0 if overdue, 0.5 if unknown
        if payment_discipline_flag == 1:
            utility_stability = 1.0
        elif payment_discipline_flag == 0:
            utility_stability = 0.0
        else:
            utility_stability = 0.5

        average_bill = bill or 0.0

        features = {
            "payment_discipline_flag": payment_discipline_flag,
            "utility_stability": round(utility_stability, 4),
            "payment_delay": payment_delay,
            "average_bill": round(average_bill, 2),
        }

        confidence = self._compute_confidence(found, missing)
        quality = len([e for e in self.REQUIRED_ENTITIES if e in found]) / len(self.REQUIRED_ENTITIES)

        return ExtractionResult(
            features=features,
            confidence=confidence,
            entities_found=found,
            missing_entities=missing,
            quality_score=quality,
            doc_type="utility",
            diagnostics=diagnostics,
        )

    def _resolve_payment_flag(self, status_raw: str) -> int:
        for kw in self.PAID_KEYWORDS:
            if kw in status_raw:
                return 1
        for kw in self.OVERDUE_KEYWORDS:
            if kw in status_raw:
                return 0
        return 0  # default conservative

    def _estimate_delay(self, status_raw: str) -> int:
        # If we can't determine days, return a standard penalty value
        return 30 if "overdue" in status_raw else 0

    def _compute_confidence(self, found: list, missing: list) -> float:
        base = len(found) / len(self.REQUIRED_ENTITIES)
        # Must have at least bill amount to be a valid utility doc
        if "bill_amount" not in found:
            base *= 0.3
        return min(1.0, base)
