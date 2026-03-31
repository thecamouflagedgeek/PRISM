def calculate_score(data):
    risk_score = 0

    if data.expenses > data.income * 0.7:
        risk_score += 0.3

    if data.credit_score < 600:
        risk_score += 0.4
    elif data.credit_score < 700:
        risk_score += 0.2

    if data.existing_loans > 3:
        risk_score += 0.3
    elif data.existing_loans > 1:
        risk_score += 0.1

    return round(risk_score, 2)