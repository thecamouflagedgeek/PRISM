import numpy as np
import pandas as pd

from backend.scoring.pipeline import inject_document_missingness


def test_inject_document_missingness_sets_document_features_to_nan():
    df = pd.DataFrame(
        {
            "credit_debit_ratio": [1.2, 0.9, 1.5],
            "cashflow_cv": [0.4, 0.3, 0.2],
            "net_to_gross_ratio": [0.8, 0.75, 0.9],
            "utility_stability": [0.4, 0.6, 0.5],
            "min_balance": [10000, 20000, 30000],
            "default": [0, 1, 1],
        }
    )

    result = inject_document_missingness(df, seed=7, salary_missing_rate=0.5, utility_missing_rate=0.5)

    salary_missing = result["net_to_gross_ratio"].isna()
    utility_missing = result["utility_stability"].isna()

    assert salary_missing.any() or utility_missing.any()
    assert result["credit_debit_ratio"].notna().all()
    assert result["cashflow_cv"].notna().all()
    assert result["min_balance"].notna().all()
    assert result.loc[salary_missing, "net_to_gross_ratio"].isna().all()
    assert result.loc[utility_missing, "utility_stability"].isna().all()
