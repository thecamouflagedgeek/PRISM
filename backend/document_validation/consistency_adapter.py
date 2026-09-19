"""
PRISM - Consistency Input Adapter

Purpose
-------
Converts the different document outputs used by PRISM into the
normalized dictionaries expected by the cross-document consistency
engine.

Important:
- Bank documents may arrive as pandas DataFrames.
- Utility documents may arrive as pandas DataFrames.
- Salary documents arrive as dictionaries.
- Application data is a dictionary.
- Missing information is preserved as None.
- This adapter must not invent identity information.
- Existing credit-scoring and fraud inputs are not modified.
"""

from typing import Any, Dict, Optional

import re

import pandas as pd


# ---------------------------------------------------------------------------
# SALARY TRANSACTION IDENTIFICATION
# ---------------------------------------------------------------------------

SALARY_KEYWORDS = [
    "salary",
    "sal",
    "payroll",
    "wages",
    "salary credit",
    "salary transfer",
]


# ---------------------------------------------------------------------------
# GENERIC HELPERS
# ---------------------------------------------------------------------------

def _first_present(
    data: Optional[Dict[str, Any]],
    *keys: str,
) -> Any:
    """
    Return the first non-empty value found among the supplied keys.
    """

    if not isinstance(data, dict):
        return None

    for key in keys:

        value = data.get(key)

        if value is None:
            continue

        if isinstance(value, str):

            value = value.strip()

            if value:
                return value

        else:
            return value

    return None


def _clean_string(
    value: Any,
) -> Optional[str]:
    """
    Normalize a value into a non-empty string.
    """

    if value is None:
        return None

    value = str(value).strip()

    return value if value else None


def _clean_number(
    value: Any,
) -> Optional[float]:
    """
    Convert a value into a finite float.

    Invalid / missing values become None.
    """

    if value is None:
        return None

    try:
        number = float(value)

    except (TypeError, ValueError):
        return None

    if not (-float("inf") < number < float("inf")):
        return None

    return number


def _normalize_date(
    value: Any,
) -> Optional[str]:
    """
    Convert a date-like value into ISO format.

    Returns None when the value cannot be parsed.
    """

    if value is None:
        return None

    try:

        parsed = pd.to_datetime(
            value,
            errors="coerce",
        )

        if pd.isna(parsed):
            return None

        return parsed.isoformat()

    except Exception:
        return None


# ---------------------------------------------------------------------------
# APPLICATION
# ---------------------------------------------------------------------------

def normalize_application(
    application: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Normalize borrower/application information.

    No values are inferred if they are not explicitly supplied.
    """

    application = application or {}

    return {
        "name": _clean_string(
            _first_present(
                application,
                "name",
                "full_name",
                "applicant_name",
                "borrower_name",
            )
        ),

        "pan": _clean_string(
            _first_present(
                application,
                "pan",
                "pan_number",
                "pan_no",
            )
        ),

        "bank_account": _clean_string(
            _first_present(
                application,
                "bank_account",
                "account_number",
                "account_no",
            )
        ),

        "monthly_income": _clean_number(
            _first_present(
                application,
                "monthly_income",
                "declared_monthly_income",
                "income",
            )
        ),

        "employer": _clean_string(
            _first_present(
                application,
                "employer",
                "employer_name",
                "company_name",
            )
        ),
    }


# ---------------------------------------------------------------------------
# SALARY DOCUMENT
# ---------------------------------------------------------------------------

def normalize_salary(
    salary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Normalize structured salary-document data.

    Current SalaryParser output is expected to contain fields such as:

        employer
        gross_salary
        net_salary
        pf
        pay_period

    Identity fields are supported when available but are never invented.
    """

    salary = salary or {}

    return {
        "name": _clean_string(
            _first_present(
                salary,
                "name",
                "employee_name",
                "employee",
                "full_name",
            )
        ),

        "pan": _clean_string(
            _first_present(
                salary,
                "pan",
                "pan_number",
                "pan_no",
            )
        ),

        "net_salary": _clean_number(
            _first_present(
                salary,
                "net_salary",
                "net_pay",
                "net_monthly_salary",
                "monthly_net_salary",
            )
        ),

        "gross_salary": _clean_number(
            _first_present(
                salary,
                "gross_salary",
                "gross_pay",
                "gross_monthly_salary",
                "monthly_gross_salary",
            )
        ),

        "employer": _clean_string(
            _first_present(
                salary,
                "employer",
                "employer_name",
                "company_name",
                "company",
            )
        ),
    }


# ---------------------------------------------------------------------------
# BANK DATAFRAME HELPERS
# ---------------------------------------------------------------------------

def _find_bank_column(
    df: pd.DataFrame,
    *candidates: str,
) -> Optional[str]:
    """
    Find a matching DataFrame column.

    Matching is case-insensitive and whitespace-insensitive.
    """

    if df is None or df.empty:
        return None

    normalized_columns = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in candidates:

        key = candidate.strip().lower()

        if key in normalized_columns:
            return normalized_columns[key]

    return None


def _extract_bank_salary_credit(
    bank: pd.DataFrame,
) -> Optional[float]:
    """
    Estimate the average salary credit from bank transactions.

    IMPORTANT:
    Only transactions whose narration matches the existing PRISM
    salary-keyword logic are considered.

    This avoids incorrectly treating every credit transaction as salary.
    """

    if not isinstance(bank, pd.DataFrame):
        return None

    if bank.empty:
        return None

    narration_column = _find_bank_column(
        bank,
        "narration",
        "description",
        "remarks",
        "transaction_description",
    )

    amount_column = _find_bank_column(
        bank,
        "amount",
        "transaction_amount",
        "credit_amount",
    )

    type_column = _find_bank_column(
        bank,
        "type",
        "transaction_type",
        "credit_debit",
    )

    if narration_column is None or amount_column is None:
        return None

    data = bank.copy()

    narration = (
        data[narration_column]
        .fillna("")
        .astype(str)
        .str.lower()
    )

    # Same conceptual salary identification used by
    # BankFeatureEngineer.
    pattern = "|".join(
        re.escape(keyword)
        for keyword in SALARY_KEYWORDS
    )

    salary_mask = narration.str.contains(
        pattern,
        case=False,
        regex=True,
        na=False,
    )

    # If transaction type exists, restrict to credits.
    if type_column is not None:

        transaction_type = (
            data[type_column]
            .fillna("")
            .astype(str)
            .str.lower()
        )

        credit_mask = transaction_type.str.contains(
            r"credit|cr",
            regex=True,
            na=False,
        )

        salary_mask = salary_mask & credit_mask

    salary_amounts = pd.to_numeric(
        data.loc[
            salary_mask,
            amount_column,
        ],
        errors="coerce",
    )

    salary_amounts = salary_amounts[
        salary_amounts.notna()
    ]

    if salary_amounts.empty:
        return None

    return float(
        salary_amounts.mean()
    )


def _extract_bank_identity(
    bank: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Extract identity information only when the bank DataFrame
    actually contains those fields.

    The current BankParser may not expose these fields, in which
    case None is returned.
    """

    if not isinstance(bank, pd.DataFrame):
        return {
            "name": None,
            "pan": None,
            "bank_account": None,
        }

    name_column = _find_bank_column(
        bank,
        "name",
        "account_holder_name",
        "account_holder",
        "customer_name",
        "full_name",
    )

    pan_column = _find_bank_column(
        bank,
        "pan",
        "pan_number",
        "pan_no",
    )

    account_column = _find_bank_column(
        bank,
        "bank_account",
        "account_number",
        "account_no",
    )

    result = {
        "name": None,
        "pan": None,
        "bank_account": None,
    }

    if not bank.empty:

        if name_column is not None:
            result["name"] = _clean_string(
                bank[name_column]
                .dropna()
                .iloc[0]
                if not bank[name_column]
                .dropna()
                .empty
                else None
            )

        if pan_column is not None:
            result["pan"] = _clean_string(
                bank[pan_column]
                .dropna()
                .iloc[0]
                if not bank[pan_column]
                .dropna()
                .empty
                else None
            )

        if account_column is not None:
            result["bank_account"] = _clean_string(
                bank[account_column]
                .dropna()
                .iloc[0]
                if not bank[account_column]
                .dropna()
                .empty
                else None
            )

    return result


def _extract_bank_period(
    bank: pd.DataFrame,
) -> Dict[str, Optional[str]]:
    """
    Derive statement start/end dates from transaction dates.

    This uses the actual transaction date range available in the
    canonical bank DataFrame.
    """

    if not isinstance(bank, pd.DataFrame):
        return {
            "statement_start_date": None,
            "statement_end_date": None,
        }

    date_column = _find_bank_column(
        bank,
        "date",
        "transaction_date",
        "transaction_datetime",
    )

    if date_column is None or bank.empty:
        return {
            "statement_start_date": None,
            "statement_end_date": None,
        }

    dates = pd.to_datetime(
        bank[date_column],
        errors="coerce",
    ).dropna()

    if dates.empty:
        return {
            "statement_start_date": None,
            "statement_end_date": None,
        }

    return {
        "statement_start_date": dates.min().isoformat(),
        "statement_end_date": dates.max().isoformat(),
    }


def _extract_bank_monthly_income(
    bank: pd.DataFrame,
) -> Optional[float]:
    """
    Return the average salary-related credit from the bank statement.

    This is intentionally based on salary-labelled transactions,
    not all credits.
    """

    return _extract_bank_salary_credit(
        bank
    )


# ---------------------------------------------------------------------------
# BANK DOCUMENT
# ---------------------------------------------------------------------------

def normalize_bank(
    bank: Any = None,
) -> Dict[str, Any]:
    """
    Normalize raw bank document data.

    Supports:
        - pandas DataFrame
        - dictionary

    For the current PRISM pipeline, the expected raw bank input is
    the canonical transaction DataFrame.
    """

    # -----------------------------------------------------------------------
    # DataFrame path
    # -----------------------------------------------------------------------

    if isinstance(bank, pd.DataFrame):

        identity = _extract_bank_identity(
            bank
        )

        period = _extract_bank_period(
            bank
        )

        return {
            **identity,

            "average_salary_credit":
                _extract_bank_monthly_income(
                    bank
                ),

            "statement_start_date":
                period["statement_start_date"],

            "statement_end_date":
                period["statement_end_date"],
        }

    # -----------------------------------------------------------------------
    # Dictionary fallback
    # -----------------------------------------------------------------------

    if isinstance(bank, dict):

        return {
            "name": _clean_string(
                _first_present(
                    bank,
                    "name",
                    "account_holder_name",
                    "account_holder",
                    "customer_name",
                    "full_name",
                )
            ),

            "pan": _clean_string(
                _first_present(
                    bank,
                    "pan",
                    "pan_number",
                    "pan_no",
                )
            ),

            "bank_account": _clean_string(
                _first_present(
                    bank,
                    "bank_account",
                    "account_number",
                    "account_no",
                )
            ),

            "average_salary_credit": _clean_number(
                _first_present(
                    bank,
                    "average_salary_credit",
                    "avg_salary_credit",
                    "average_monthly_salary_credit",
                )
            ),

            "statement_start_date":
                _normalize_date(
                    _first_present(
                        bank,
                        "statement_start_date",
                        "start_date",
                        "period_start",
                    )
                ),

            "statement_end_date":
                _normalize_date(
                    _first_present(
                        bank,
                        "statement_end_date",
                        "end_date",
                        "period_end",
                    )
                ),
        }

    # -----------------------------------------------------------------------
    # Missing / unsupported input
    # -----------------------------------------------------------------------

    return {
        "name": None,
        "pan": None,
        "bank_account": None,
        "average_salary_credit": None,
        "statement_start_date": None,
        "statement_end_date": None,
    }


# ---------------------------------------------------------------------------
# UTILITY DOCUMENT
# ---------------------------------------------------------------------------

def normalize_utility(
    utility: Any = None,
) -> Dict[str, Any]:
    """
    Normalize utility document data.

    The current UtilityParser output is a DataFrame.

    Identity fields are extracted only if they actually exist in
    the DataFrame. No name/account/PAN is fabricated from unrelated
    utility fields such as consumer_number.
    """

    # -----------------------------------------------------------------------
    # DataFrame path
    # -----------------------------------------------------------------------

    if isinstance(utility, pd.DataFrame):

        name_column = _find_bank_column(
            utility,
            "name",
            "customer_name",
            "account_holder_name",
            "full_name",
        )

        result = {
            "name": None,
        }

        if (
            name_column is not None
            and not utility.empty
        ):

            values = (
                utility[name_column]
                .dropna()
            )

            if not values.empty:
                result["name"] = _clean_string(
                    values.iloc[0]
                )

        return result

    # -----------------------------------------------------------------------
    # Dictionary fallback
    # -----------------------------------------------------------------------

    if isinstance(utility, dict):

        return {
            "name": _clean_string(
                _first_present(
                    utility,
                    "name",
                    "customer_name",
                    "account_holder_name",
                    "full_name",
                )
            ),
        }

    return {
        "name": None,
    }


# ---------------------------------------------------------------------------
# COMPLETE CONSISTENCY INPUT BUILDER
# ---------------------------------------------------------------------------

def build_consistency_inputs(
    application: Optional[Dict[str, Any]] = None,
    salary: Optional[Dict[str, Any]] = None,
    bank: Any = None,
    utility: Any = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Build the normalized inputs expected by ConsistencyEngine.

    Returns:

        {
            "application": {...},
            "salary": {...},
            "bank": {...},
            "utility": {...},
        }

    This function intentionally keeps document consistency
    independent from credit scoring and fraud scoring.
    """

    return {
        "application": normalize_application(
            application
        ),

        "salary": normalize_salary(
            salary
        ),

        "bank": normalize_bank(
            bank
        ),

        "utility": normalize_utility(
            utility
        ),
    }