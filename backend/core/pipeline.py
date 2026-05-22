from services.parser_service import process_document
from services.feature_service import extract_features
from scoring.risk_scorer import compute_risk_score

def run_assessment(bank_file, salary_file, utility_file, session):

    # BANK
    bank_df, bank_conf = process_document(bank_file, "bank")
    bank_features = extract_features(bank_df, "bank")

    session.bank_features = bank_features
    session.bank_confidence = bank_conf

    # SALARY
    salary_features = None
    salary_conf = 0.0
    if salary_file:
        df, salary_conf = process_document(salary_file, "salary")
        salary_features = extract_features(df, "salary")
        session.salary_features = salary_features
        session.salary_confidence = salary_conf

    # UTILITY
    utility_features = None
    utility_conf = 0.0
    if utility_file:
        df, utility_conf = process_document(utility_file, "utility")
        utility_features = extract_features(df, "utility")
        session.utility_features = utility_features
        session.utility_confidence = utility_conf

    # SCORE
    result = compute_risk_score(
        bank_features,
        salary_features,
        utility_features,
        bank_conf,
        salary_conf,
        utility_conf
    )

    session.assessment_result = result
    return result