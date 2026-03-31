def generate_reasons(data):
    reasons = []

    if data.expenses > data.income * 0.7:
        reasons.append("High expense to income ratio")

    if data.credit_score < 600:
        reasons.append("Low credit score")
    elif data.credit_score < 700:
        reasons.append("Moderate credit score")

    if data.existing_loans > 1:
        reasons.append("Multiple existing loans")

    return reasons