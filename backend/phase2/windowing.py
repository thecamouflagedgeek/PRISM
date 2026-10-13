"""Canonical complete-calendar-month windows shared by audits and experiments."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Union

DateLike = Union[date, datetime]


def _as_date(value: Optional[DateLike]) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"Expected date or datetime, got {type(value).__name__}")


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _subtract_months(month_start: date, months: int) -> date:
    if months <= 0:
        raise ValueError("months must be positive")
    month_index = month_start.year * 12 + (month_start.month - 1) - months
    year, month0 = divmod(month_index, 12)
    return date(year, month0 + 1, 1)


@dataclass(frozen=True)
class CalendarWindow:
    window_start: date
    window_end_exclusive: date
    complete_months: int
    eligible: bool
    coverage_state: str


def complete_calendar_window(
    loan_date: DateLike,
    months: int,
    *,
    account_open_date: Optional[DateLike] = None,
    source_coverage_start: Optional[DateLike] = None,
    source_coverage_end_exclusive: Optional[DateLike] = None,
) -> CalendarWindow:
    """Build the N full calendar months before loan month and assess coverage.

    The origination month is always excluded. A window is eligible only if the
    account existed at its first day and the source spans the whole interval.
    Coverage comparisons use calendar dates, never fixed day-count offsets.
    """
    if months <= 0:
        raise ValueError("months must be positive")
    loan = _as_date(loan_date)
    if loan is None:
        raise ValueError("loan_date is required")
    end = _month_start(loan)
    start = _subtract_months(end, months)
    opened = _as_date(account_open_date)
    source_start = _as_date(source_coverage_start)
    source_end = _as_date(source_coverage_end_exclusive)

    if opened is None:
        state = "ACCOUNT_OPEN_DATE_MISSING"
    elif opened > start:
        state = "ACCOUNT_OPENED_AFTER_WINDOW_START"
    elif source_start is None:
        state = "SOURCE_COVERAGE_START_MISSING"
    elif source_start > start:
        state = "SOURCE_START_AFTER_WINDOW_START"
    elif source_end is None:
        state = "SOURCE_COVERAGE_END_MISSING"
    elif source_end < end:
        state = "SOURCE_END_BEFORE_WINDOW_END"
    else:
        state = "ELIGIBLE"
    return CalendarWindow(start, end, months, state == "ELIGIBLE", state)


def transaction_is_observed(
    transaction_date: DateLike, loan_date: DateLike, window: CalendarWindow
) -> bool:
    """True only for records inside the complete-month window and before loan."""
    txn = _as_date(transaction_date)
    loan = _as_date(loan_date)
    if txn is None or loan is None:
        return False
    return window.window_start <= txn < window.window_end_exclusive and txn < loan
