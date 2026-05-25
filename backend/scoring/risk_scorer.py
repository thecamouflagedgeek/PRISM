from typing import Dict, List, Optional
import math
import numpy as np


# =========================================================
# CONFIG (FINTECH SCORECARD PARAMETERS)
# =========================================================

BASE_POINTS = 600
PDO = 50          # points to double odds
BASE_ODDS = 1/20  # industry standard starting odds

FACTOR = PDO / math.log(2)
OFFSET = BASE_POINTS - FACTOR * math.log(BASE_ODDS)


# =========================================================
# WOE TABLES (YOU WILL LATER TRAIN THESE FROM DATA)
# =========================================================

WOE_TABLES = {
    "credit_debit_ratio": [
        (0.0, 0.8, -1.2),
        (0.8, 1.2, -0.3),
        (1.2, 1.8, 0.7),
        (1.8, 10.0, 1.4)
    ],

    "cashflow_cv": [
        (0.0, 0.25, 1.3),
        (0.25, 0.5, 0.4),
        (0.5, 0.8, -0.6),
        (0.8, 10.0, -1.4)
    ],

    "net_to_gross_ratio": [
        (0.0, 0.5, -1.1),
        (0.5, 0.7, -0.2),
        (0.7, 0.85, 0.9),
        (0.85, 1.0, 1.3)
    ]
}


IV_TABLE = {
    "credit_debit_ratio": 0.45,
    "cashflow_cv": 0.38,
    "net_to_gross_ratio": 0.30
}


# =========================================================
# SAFE WOE FUNCTION
# =========================================================

def woe(value, bins):
    if value is None:
        return 0.0

    for low, high, w in bins:
        if low <= value < high:
            return w

    return 0.0


# =========================================================
# LOGISTIC MODEL (PD ESTIMATION CORE)
# =========================================================

def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def compute_log_odds(bank, salary, utility):
    """
    Converts WoE features → log-odds (this is REAL scorecard logic)
    """

    score = 0.0

    # BANK
    if bank:
        score += woe(bank.get("credit_debit_ratio"), WOE_TABLES["credit_debit_ratio"]) * 1.2
        score += woe(bank.get("cashflow_cv"), WOE_TABLES["cashflow_cv"]) * 1.0

    # SALARY
    if salary:
        score += woe(salary.get("net_to_gross_ratio"), WOE_TABLES["net_to_gross_ratio"]) * 1.1

        pf = salary.get("pf_contribution_flag")
        score += 0.4 if pf else -0.3

    # UTILITY (simple signal)
    if utility:
        score += 0.5 if utility.get("payment_discipline_flag") else -0.5

    return score


# =========================================================
# SCORE TRANSLATION (LOG ODDS → CREDIT SCORE)
# =========================================================

def to_credit_score(log_odds: float) -> int:
    score = OFFSET + FACTOR * log_odds
    return int(max(300, min(900, score)))


# =========================================================
# CONFIDENCE MODEL (REAL VERSION)
# =========================================================

def compute_confidence(bank, salary, utility):

    def valid(x):
        return x is not None and x != 0

    bank_q = sum([
        valid(bank.get("credit_debit_ratio") if bank else None),
        valid(bank.get("cashflow_cv") if bank else None)
    ]) / 2 if bank else 0

    salary_q = sum([
        valid(salary.get("net_to_gross_ratio") if salary else None),
        salary.get("pf_contribution_flag") is not None if salary else 0
    ]) / 2 if salary else 0

    utility_q = sum([
        utility is not None,
        utility.get("payment_discipline_flag") is not None if utility else 0
    ]) / 2 if utility else 0

    return round(
        0.5 * bank_q +
        0.3 * salary_q +
        0.2 * utility_q,
        2
    )


# =========================================================
# MAIN ENGINE (PRODUCTION SCORECARD)
# =========================================================

def compute_risk_score(
    bank: Optional[dict],
    salary: Optional[dict],
    utility: Optional[dict]
) -> Dict:

    # 1. LOG ODDS FROM WOE MODEL
    log_odds = compute_log_odds(bank, salary, utility)

    # 2. CONVERT TO SCORE
    score = to_credit_score(log_odds)

    # 3. PD (Probability of Default)
    pd = sigmoid(-log_odds)

    # 4. CONFIDENCE
    confidence = compute_confidence(bank, salary, utility)

    # 5. RISK TIER (BASED ON PD — INDUSTRY STYLE)
    if pd < 0.2:
        tier = "Low Risk"
    elif pd < 0.4:
        tier = "Medium Risk"
    elif pd < 0.7:
        tier = "High Risk"
    else:
        tier = "Very High Risk"

    # 6. IV SUMMARY (FEATURE IMPORTANCE)
    iv = IV_TABLE
        # =========================================================
    # EXPLANATION LAYER (NEW - SAFE ADDITION)
    # =========================================================

    reason_codes = []
    shap_reasons = []

    # -------------------------
    # BANK REASONS
    # -------------------------
    if bank:
        cdr = bank.get("credit_debit_ratio")
        cv = bank.get("cashflow_cv")

        reason_codes.append({
            "factor": "Credit-Debit Ratio",
            "value": cdr,
            "impact": "positive" if cdr and cdr > 1.2 else "negative"
        })

        reason_codes.append({
            "factor": "Cashflow Stability",
            "value": cv,
            "impact": "positive" if cv and cv < 0.5 else "negative"
        })

        shap_reasons.extend([
            {
                "factor": "Credit-Debit Ratio (WoE)",
                "value": cdr,
                "source": "Bank Statement"
            },
            {
                "factor": "Cashflow CV (WoE)",
                "value": cv,
                "source": "Bank Statement"
            }
        ])

    # -------------------------
    # SALARY REASONS
    # -------------------------
    if salary:
        ngr = salary.get("net_to_gross_ratio")

        reason_codes.append({
            "factor": "Income Stability",
            "value": ngr,
            "impact": "positive" if ngr and ngr > 0.7 else "negative"
        })

        shap_reasons.append({
            "factor": "Net to Gross Ratio",
            "value": ngr,
            "source": "Salary Slip"
        })

    # -------------------------
    # UTILITY REASONS
    # -------------------------
    if utility:
        flag = utility.get("payment_discipline_flag")

        reason_codes.append({
            "factor": "Utility Discipline",
            "value": flag,
            "impact": "positive" if flag else "negative"
        })

        shap_reasons.append({
            "factor": "Payment Discipline",
            "value": flag,
            "source": "Utility Bill"
        })
        
    return {
        "risk_score": score,
        "probability_of_default": round(pd, 4),
        "risk_tier": tier,
        "confidence_score": confidence,
        "iv_scores": iv,
        "model_type": "WoE_Logistic_Scorecard",
        "notes": "Production-style scorecard using WoE + logistic PD scaling"
    }