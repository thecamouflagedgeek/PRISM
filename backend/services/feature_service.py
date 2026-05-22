from features.bank_features import BankFeatureEngineer
from features.salary_features import SalaryFeatureEngineer
from features.utility_features import UtilityFeatureEngineer
def build_features(df, doc_type):

    if df is None:
        return None

    if doc_type == "bank":
        return BankFeatureEngineer(df).build_features()

    if doc_type == "salary":
        return SalaryFeatureEngineer(df).build_features()

    if doc_type == "utility":
        return UtilityFeatureEngineer(df).build_features()

    return None