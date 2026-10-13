"""Transparent contribution-based reasons, not SHAP or causal explanations."""

REASONS = {
    "recent_delinquency_level": "Recent repayment delinquency",
    "months_with_delinquency": "Repeated repayment delinquency",
    "payment_to_statement_ratio": "Payment relative to statement balances",
    "mean_statement_balance": "Average statement balance",
}


def rank_reasons(contributions: dict, feature_trace: dict) -> list[dict]:
    # Positive contribution increases the default logit; rank the largest first.
    adverse = [(f, float(c)) for f, c in contributions.items() if float(c) > 0]
    adverse.sort(key=lambda item: (-item[1], list(contributions).index(item[0])))
    return [{
        "code": feature,
        "label": REASONS[feature],
        "direction": "increases_default_logit",
        "contribution": value,
        "trace": feature_trace[feature],
    } for feature, value in adverse]
