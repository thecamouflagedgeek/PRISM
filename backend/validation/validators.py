from validation.helpers import *

def validate_field(value, field_name,
                   mandatory,
                   expected_type,
                   min_val,
                   max_val):
    issues = []
    score = 1.0
    if value is None or str(value).strip() == "":
        if mandatory:
            issues.append(f"{field_name} missing")
            return False, issues, 0.0
        return True, issues, 0.8

    if expected_type == "date":

        if try_parse_date(value) is None:
            issues.append(f"{field_name} invalid date")
            score -= 0.4
    elif expected_type == "float":

        if not is_valid_float(value):
            issues.append(f"{field_name} not numeric")
            score -= 0.5
    elif expected_type == "cr_dr":
        if not is_valid_cr_dr(value):
            issues.append(f"{field_name} must be CR/DR")
            score -= 0.4
    elif expected_type == "str":

        if not is_valid_str(value):
            issues.append(f"{field_name} empty")
            score -= 0.2
    return len(issues) == 0, issues, max(score, 0.0)