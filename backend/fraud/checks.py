def check_fraud(data):
    if data.income == 0 or data.credit_score == 0:
        return "High"
    return "Low"