from typing import Optional, Dict
def compute_risk_score(
    bank: Optional[dict],
    salary: Optional[dict],
    utility: Optional[dict]
) -> Dict:

    score = 300
    reasons = []

    #bank
    if bank:
        cdr = bank.get("credit_debit_ratio", 1)
        cv  = bank.get("cashflow_cv", 0.5)

        score += cdr * 60
        score += (1 - cv) * 80

        reasons.append("bank_behavior")

    #salary
    if salary:
        ngr = salary.get("net_to_gross_ratio", 0)
        score += ngr * 100

        if salary.get("pf_contribution_flag"):
            score += 30

        reasons.append("salary_stability")

    #utility
    if utility:
        flag = utility.get("payment_discipline_flag", 0)
        score += flag * 50

        reasons.append("utility_discipline")

    #NORMALIZATION
    score = max(300, min(900, int(score)))

    if score >= 700:
        tier = "Low Risk"
    elif score >= 550:
        tier = "Medium Risk"
    else:
        tier = "High Risk"

    return {
        "risk_score": score,
        "risk_tier": tier,
        "reasons": reasons
    }