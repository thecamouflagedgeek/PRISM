import pandas as pd
from validation.validators import validate_field
from validation.config import CONFIG


def validate_dataframe(df, field_rules, source_name):
    row_scores = []
    row_issues = []
    review_flags = []
    for _, row in df.iterrows():
        scores = []
        issues = []

        for field, rule in field_rules.items():
            mandatory, expected_type, min_val, max_val = rule
            _, field_issues, score = validate_field(
                row.get(field),
                field,
                mandatory,
                expected_type,
                min_val,
                max_val
            )
            scores.append(score)
            issues.extend(field_issues)
        confidence = round(sum(scores) / len(scores), 4)

        row_scores.append(confidence)
        row_issues.append("; ".join(issues))
        review_flags.append(
            confidence < CONFIG["confidence_threshold"]
        )
    out = df.copy()
    out["confidence_score"] = row_scores
    out["issues"] = row_issues
    out["review_required"] = review_flags
    return out