"""
PRISM Canonical Financial Schema Mapper
Maps detected entities to canonical PRISM field names.
This is the key abstraction that makes the parser bank/employer/utility agnostic.

Example:
  "Deposit"  → credit_amount
  "Take Home" → net_salary
  "Amount Due" → bill_amount
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from entity_recognition.fere import EntitySet, DetectedEntity

logger = logging.getLogger(__name__)


@dataclass
class CanonicalDocument:
    """
    Vendor-neutral financial representation.
    All fields are optional — presence drives confidence scoring.
    """
    # Bank fields
    credit_amounts: list[float] = field(default_factory=list)
    debit_amounts: list[float] = field(default_factory=list)
    running_balances: list[float] = field(default_factory=list)
    transaction_dates: list[str] = field(default_factory=list)
    transaction_descriptions: list[str] = field(default_factory=list)

    # Salary fields
    gross_salary: Optional[float] = None
    net_salary: Optional[float] = None
    pf_contribution: Optional[float] = None
    tax_deduction: Optional[float] = None
    total_deductions: Optional[float] = None
    employee_name: Optional[str] = None
    employer_name: Optional[str] = None
    pay_period: Optional[str] = None

    # Utility fields
    bill_amount: Optional[float] = None
    due_date: Optional[str] = None
    payment_status: Optional[str] = None
    units_consumed: Optional[float] = None
    billing_period: Optional[str] = None
    consumer_number: Optional[str] = None

    # Extraction metadata
    entity_confidences: dict[str, float] = field(default_factory=dict)


class CanonicalSchemaMapper:
    """
    Takes an EntitySet (output of FERE) and produces a CanonicalDocument.
    All mapping decisions are centralised here.
    """

    def map(self, entity_set: EntitySet) -> CanonicalDocument:
        doc = CanonicalDocument()
        entities = entity_set.entities

        # ---- Bank ----
        for e in entities.get("credit_amount", []):
            if e.numeric_value is not None:
                doc.credit_amounts.append(e.numeric_value)
                doc.entity_confidences["credit_amount"] = max(
                    doc.entity_confidences.get("credit_amount", 0), e.confidence
                )

        for e in entities.get("debit_amount", []):
            if e.numeric_value is not None:
                doc.debit_amounts.append(e.numeric_value)
                doc.entity_confidences["debit_amount"] = max(
                    doc.entity_confidences.get("debit_amount", 0), e.confidence
                )

        for e in entities.get("running_balance", []):
            if e.numeric_value is not None:
                doc.running_balances.append(e.numeric_value)
                doc.entity_confidences["running_balance"] = max(
                    doc.entity_confidences.get("running_balance", 0), e.confidence
                )

        for e in entities.get("transaction_date", []):
            if e.raw_value:
                doc.transaction_dates.append(e.raw_value)

        for e in entities.get("transaction_description", []):
            if e.raw_value:
                doc.transaction_descriptions.append(e.raw_value)

        # ---- Salary ----
        doc.gross_salary = self._best_numeric(entities, "gross_salary", doc)
        doc.net_salary = self._best_numeric(entities, "net_salary", doc)
        doc.pf_contribution = self._best_numeric(entities, "pf_contribution", doc)
        doc.tax_deduction = self._best_numeric(entities, "tax_deduction", doc)
        doc.total_deductions = self._best_numeric(entities, "total_deductions", doc)
        doc.employee_name = self._best_text(entities, "employee_name")
        doc.employer_name = self._best_text(entities, "employer_name")
        doc.pay_period = self._best_text(entities, "pay_period")

        # ---- Utility ----
        doc.bill_amount = self._best_numeric(entities, "bill_amount", doc)
        doc.due_date = self._best_text(entities, "due_date")
        doc.payment_status = self._best_text(entities, "payment_status")
        doc.units_consumed = self._best_numeric(entities, "units_consumed", doc)
        doc.billing_period = self._best_text(entities, "billing_period")
        doc.consumer_number = self._best_text(entities, "consumer_number")

        # Salary inference: if we have net but not gross, estimate gross
        if doc.net_salary and not doc.gross_salary and doc.total_deductions:
            doc.gross_salary = doc.net_salary + doc.total_deductions
            logger.info("Inferred gross_salary from net + deductions: %.2f", doc.gross_salary)

        return doc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _best_numeric(
        self,
        entities: dict[str, list[DetectedEntity]],
        key: str,
        doc: CanonicalDocument,
    ) -> Optional[float]:
        candidates = entities.get(key, [])
        if not candidates:
            return None
        best = max(candidates, key=lambda e: e.confidence)
        if best.numeric_value is not None:
            doc.entity_confidences[key] = best.confidence
        return best.numeric_value

    def _best_text(
        self,
        entities: dict[str, list[DetectedEntity]],
        key: str,
    ) -> Optional[str]:
        candidates = entities.get(key, [])
        if not candidates:
            return None
        best = max(candidates, key=lambda e: e.confidence)
        return best.raw_value if best.raw_value else None
