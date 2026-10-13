"""One-command demonstration of the real P1 integrated assessment service."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from services.assessment_service import assess_borrower


def main() -> None:
    reference = datetime(2026, 9, 18, 12, 0, 0)
    borrower = {"application_id": "APP-DEMO-001", "pan": "ABCDE1234F", "application_date": reference.isoformat()}
    history = [{"application_id": "APP-OLD-001", "pan": "ABCDE1234F", "application_date": (reference - timedelta(days=3)).isoformat(), "status": "ACTIVE"}]
    transactions = [
        {"date": "2026-09-01", "amount": 1000, "type": "CR", "closing_balance": 5000},
        {"date": "2026-09-02", "amount": 1200, "type": "CR", "closing_balance": 6200},
        {"date": "2026-09-03", "amount": 1100, "type": "CR", "closing_balance": 7300},
        {"date": "2026-09-04", "amount": 5000, "type": "CR", "closing_balance": 12300},
    ]
    result = assess_borrower(
        bank={"credit_debit_ratio": 1.25, "cashflow_cv": 0.35, "min_balance_l3m": 25000},
        salary={"net_to_gross_ratio": 0.82}, utility={"utility_stability": 0.20},
        borrower=borrower, application_history=history, transactions=transactions, reference_time=reference,
    )
    credit, fraud = result["credit_risk"], result["fraud_risk"]
    print("=" * 60)
    print("PRISM — INTEGRATED RISK ASSESSMENT")
    print("=" * 60)
    print(f"APPLICATION: {result['application_id']}")
    print("\n---------------- CREDIT RISK ----------------")
    print(f"Credit Score       : {credit['score']}")
    print(f"Probability Default: {credit['pd']:.2%}")
    print(f"Risk Tier          : {credit['risk_tier']}")
    print(f"Confidence         : {credit['confidence']['band']}")
    print("\n---------------- FRAUD RISK -----------------")
    print(f"Fraud Score         : {fraud['fraud_score']} / 100")
    print(f"Fraud Status        : {fraud['fraud_status']}")
    print(f"Rules Triggered     : {fraud['rule_count']}")
    print(f"Engine Version      : {fraud['engine_version']}")
    for index, flag in enumerate(fraud["flags"], 1):
        print(f"\n{index}. {flag['rule']}")
        print(f"   Category : {flag['category']}")
        print(f"   Severity : {flag['severity']}")
        print(f"   Weight   : {flag['weight']}")
        print(f"   Message  : {flag['message']}")
        print(f"   Evidence : {json.dumps(flag['evidence'], default=str)}")
    print("\n" + "=" * 60)
    print("ASSESSMENT COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
