"""FY-window tests — the fix for the wall-clock FY bug found in review.

The FY that governs the ₹5L threshold is the case's OWN financial year
(1 April – 31 March), derived from its remittance/creation date, never from
the date the classifier happens to run.
"""

from __future__ import annotations

from datetime import date

from app.services.classification import fy_bounds


class TestFYBounds:
    def test_mid_fy_date(self):
        assert fy_bounds(date(2026, 7, 21)) == (date(2026, 4, 1), date(2027, 3, 31))

    def test_january_belongs_to_previous_fy(self):
        assert fy_bounds(date(2026, 1, 15)) == (date(2025, 4, 1), date(2026, 3, 31))

    def test_march_31_is_last_day_of_fy(self):
        assert fy_bounds(date(2026, 3, 31)) == (date(2025, 4, 1), date(2026, 3, 31))

    def test_april_1_starts_new_fy(self):
        assert fy_bounds(date(2026, 4, 1)) == (date(2026, 4, 1), date(2027, 3, 31))

    def test_march_case_stays_in_old_fy_even_if_classified_in_april(self):
        # The review finding: a 30 March remittance classified on 2 April must
        # aggregate against FY25-26, not FY26-27. fy_bounds takes the case
        # date, so the window is fully determined by the remittance itself.
        march_case_window = fy_bounds(date(2026, 3, 30))
        april_case_window = fy_bounds(date(2026, 4, 2))
        assert march_case_window == (date(2025, 4, 1), date(2026, 3, 31))
        assert april_case_window == (date(2026, 4, 1), date(2027, 3, 31))
        assert march_case_window != april_case_window
