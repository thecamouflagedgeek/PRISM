import unittest
from datetime import date

from phase2.windowing import complete_calendar_window, transaction_is_observed


class CompleteCalendarWindowTests(unittest.TestCase):
    def eligible(self, loan, n, opened=None):
        opened = opened or date(1990, 1, 1)
        return complete_calendar_window(
            loan, n, account_open_date=opened,
            source_coverage_start=date(1990, 1, 1),
            source_coverage_end_exclusive=date(2000, 1, 1),
        )

    def test_october_28_3m_and_6m(self):
        loan = date(1998, 10, 28)
        w3, w6 = self.eligible(loan, 3), self.eligible(loan, 6)
        self.assertEqual((w3.window_start, w3.window_end_exclusive), (date(1998, 7, 1), date(1998, 10, 1)))
        self.assertEqual((w6.window_start, w6.window_end_exclusive), (date(1998, 4, 1), date(1998, 10, 1)))

    def test_october_first_excludes_origination_month(self):
        w = self.eligible(date(1998, 10, 1), 3)
        self.assertEqual((w.window_start, w.window_end_exclusive), (date(1998, 7, 1), date(1998, 10, 1)))

    def test_year_boundary(self):
        w = self.eligible(date(2000, 2, 20), 3)
        self.assertEqual((w.window_start, w.window_end_exclusive), (date(1999, 11, 1), date(2000, 2, 1)))

    def test_leap_year_uses_calendar_months(self):
        w = self.eligible(date(2024, 3, 15), 1)
        self.assertEqual((w.window_start, w.window_end_exclusive), (date(2024, 2, 1), date(2024, 3, 1)))

    def test_start_included_last_day_included_origination_month_and_loan_date_excluded(self):
        loan = date(1998, 10, 28)
        w = self.eligible(loan, 3)
        self.assertTrue(transaction_is_observed(date(1998, 7, 1), loan, w))
        self.assertTrue(transaction_is_observed(date(1998, 9, 30), loan, w))
        self.assertFalse(transaction_is_observed(date(1998, 10, 1), loan, w))
        self.assertFalse(transaction_is_observed(loan, loan, w))

    def test_account_opened_after_window_start_is_ineligible(self):
        w = self.eligible(date(1998, 10, 28), 3, date(1998, 7, 15))
        self.assertFalse(w.eligible)
        self.assertEqual(w.coverage_state, "ACCOUNT_OPENED_AFTER_WINDOW_START")

    def test_account_opened_exactly_at_window_start_is_eligible(self):
        w = self.eligible(date(1998, 10, 28), 3, date(1998, 7, 1))
        self.assertTrue(w.eligible)

    def test_source_must_cover_full_window(self):
        w = complete_calendar_window(
            date(1998, 10, 28), 3,
            account_open_date=date(1990, 1, 1),
            source_coverage_start=date(1998, 7, 2),
            source_coverage_end_exclusive=date(1999, 1, 1),
        )
        self.assertFalse(w.eligible)
        self.assertEqual(w.coverage_state, "SOURCE_START_AFTER_WINDOW_START")


if __name__ == "__main__":
    unittest.main()
