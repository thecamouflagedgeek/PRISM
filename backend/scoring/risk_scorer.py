from typing import Optional, Dict


def compute_risk_score(
    bank: Optional[dict],
    salary: Optional[dict],
    utility: Optional[dict]
) -> Dict:

    score = 300
    reasons = []
    shap_reasons = []
    fraud_flags = []

    available_sources = 0

    # -------------------------
    # BANK FEATURES
    # -------------------------
    if bank:
        available_sources += 1

        cdr = bank.get("credit_debit_ratio", 1)
        cv = bank.get("cashflow_cv", 0.5)

        cdr_pts = int(cdr * 60)
        cv_pts = int((1 - cv) * 80)

        score += cdr_pts
        score += cv_pts

        reasons.append("bank_behavior")

        shap_reasons.extend([
            {
                "factor": "Credit Debit Ratio",
                "impact_pts": cdr_pts,
                "direction": "positive" if cdr_pts >= 0 else "negative",
                "source": "Bank Statement"
            },
            {
                "factor": "Cashflow Stability",
                "impact_pts": cv_pts,
                "direction": "positive" if cv_pts >= 0 else "negative",
                "source": "Bank Statement"
            }
        ])

    # -------------------------
    # SALARY FEATURES
    # -------------------------
    if salary:
        available_sources += 1

        ngr = salary.get("net_to_gross_ratio", 0)

        ngr_pts = int(ngr * 100)

        score += ngr_pts

        shap_reasons.append({
            "factor": "Net To Gross Ratio",
            "impact_pts": ngr_pts,
            "direction": "positive" if ngr_pts >= 0 else "negative",
            "source": "Salary Slip"
        })

        if salary.get("pf_contribution_flag"):

            score += 30

            shap_reasons.append({
                "factor": "PF Contribution",
                "impact_pts": 30,
                "direction": "positive",
                "source": "Salary Slip"
            })

        reasons.append("salary_stability")

    # -------------------------
    # UTILITY FEATURES
    # -------------------------
    if utility:
        available_sources += 1

        flag = utility.get("payment_discipline_flag", 0)

        utility_pts = int(flag * 50)

        score += utility_pts

        shap_reasons.append({
            "factor": "Payment Discipline",
            "impact_pts": utility_pts,
            "direction": "positive" if utility_pts >= 0 else "negative",
            "source": "Utility Bill"
        })

        reasons.append("utility_discipline")

    # -------------------------
    # SCORE NORMALIZATION
    # -------------------------
    score = max(300, min(900, int(score)))

    if score >= 700:
        tier = "Low Risk"
    elif score >= 550:
        tier = "Medium Risk"
    else:
        tier = "High Risk"

    # -------------------------
    # DATA QUALITY
    # -------------------------
    feature_coverage = int((available_sources / 3) * 100)

    confidence_score = round(
        0.5 + (feature_coverage / 100) * 0.5,
        2
    )

    thin_file = available_sources < 2

    # -------------------------
    # RETURN RESPONSE
    # -------------------------
    return {
        "risk_score": score,
        "risk_tier": tier,

        "confidence_score": confidence_score,

        "data_quality": {
            "feature_coverage": feature_coverage,
            "thin_file": thin_file,
            "thin_file_note":
                "Limited document coverage may reduce score reliability."
                if thin_file else None
        },

        "review_required": score < 450,

        "fraud_flags": fraud_flags,

        "shap_reasons": shap_reasons,

        "features": {
            "bank": bank,
            "salary": salary,
            "utility": utility
        },

        "warnings": [],

        "reasons": reasons
    }