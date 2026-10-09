"""The date math for repeating to-dos (feature 19): next_due_date.

A pure function, so these tests need no database: SimpleTestCase.
"""

from datetime import date

from django.test import SimpleTestCase

from todos.repeat import next_due_date


class NextDueDateTests(SimpleTestCase):
    def assert_steps(self, repeat, cases):
        """Each (from, to) pair: next_due_date(from, repeat) is `to`."""
        for start, expected in cases:
            with self.subTest(start=start):
                self.assertEqual(next_due_date(start, repeat), expected)

    def test_daily(self):
        self.assert_steps(
            "daily",
            [
                (date(2026, 10, 12), date(2026, 10, 13)),
                (date(2026, 10, 31), date(2026, 11, 1)),
                (date(2026, 12, 31), date(2027, 1, 1)),
                (date(2027, 2, 28), date(2027, 3, 1)),
                (date(2028, 2, 28), date(2028, 2, 29)),  # leap year
                (date(2028, 2, 29), date(2028, 3, 1)),
            ],
        )

    def test_weekly(self):
        self.assert_steps(
            "weekly",
            [
                (date(2026, 10, 12), date(2026, 10, 19)),
                (date(2026, 12, 28), date(2027, 1, 4)),
                (date(2027, 2, 25), date(2027, 3, 4)),
                (date(2028, 2, 26), date(2028, 3, 4)),  # leap year
            ],
        )

    def test_monthly_same_day(self):
        self.assert_steps(
            "monthly",
            [
                (date(2026, 10, 12), date(2026, 11, 12)),
                (date(2026, 12, 15), date(2027, 1, 15)),
                (date(2027, 1, 28), date(2027, 2, 28)),
                # In a leap year, 28 Feb is not the last day: it stays the 28th.
                (date(2028, 2, 28), date(2028, 3, 28)),
            ],
        )

    def test_monthly_remembers_the_day(self):
        # (from, the remembered day, to). The day of the month the person
        # chose comes back when the month is long enough (owner decision).
        cases = [
            (date(2027, 1, 31), 31, date(2027, 2, 28)),
            (date(2027, 2, 28), 31, date(2027, 3, 31)),
            (date(2027, 3, 31), 31, date(2027, 4, 30)),
            (date(2027, 4, 30), 31, date(2027, 5, 31)),
            (date(2028, 1, 31), 31, date(2028, 2, 29)),  # leap year
            (date(2028, 2, 29), 31, date(2028, 3, 31)),
            (date(2026, 12, 31), 31, date(2027, 1, 31)),
            (date(2027, 2, 28), 30, date(2027, 3, 30)),
            (date(2027, 2, 28), 29, date(2027, 3, 29)),
            (date(2027, 2, 28), 28, date(2027, 3, 28)),
            (date(2028, 2, 28), 28, date(2028, 3, 28)),
        ]
        for start, day, expected in cases:
            with self.subTest(start=start, day=day):
                self.assertEqual(next_due_date(start, "monthly", day), expected)

    def test_monthly_short_month(self):
        self.assert_steps(
            "monthly",
            [
                (date(2027, 1, 29), date(2027, 2, 28)),
                (date(2027, 1, 30), date(2027, 2, 28)),
                (date(2027, 1, 31), date(2027, 2, 28)),
                (date(2028, 1, 30), date(2028, 2, 29)),
            ],
        )

    def test_monthly_without_a_day_uses_the_due_dates_day(self):
        # An old row, or one made in the shell, has no remembered day.
        # A last day of a month is NOT "the end of the month" any more.
        self.assert_steps(
            "monthly",
            [
                (date(2027, 2, 28), date(2027, 3, 28)),
                (date(2027, 4, 30), date(2027, 5, 30)),
                (date(2028, 2, 29), date(2028, 3, 29)),
            ],
        )

    def test_daily_and_weekly_ignore_the_day(self):
        self.assertEqual(
            next_due_date(date(2026, 10, 12), "daily", 31), date(2026, 10, 13)
        )
        self.assertEqual(
            next_due_date(date(2026, 10, 12), "weekly", 31), date(2026, 10, 19)
        )

    def chain(self, start, repeat, steps, day=None):
        """The dates after calling next_due_date `steps` times in a row.

        With `day`, each call gets it (the day the to-do remembers).
        """
        dates = []
        for _ in range(steps):
            if day is None:
                start = next_due_date(start, repeat)
            else:
                start = next_due_date(start, repeat, day)
            dates.append(start)
        return dates

    def test_monthly_twelve_steps_from_the_31st(self):
        self.assertEqual(
            self.chain(date(2027, 1, 31), "monthly", 12, day=31),
            [
                date(2027, 2, 28),
                date(2027, 3, 31),
                date(2027, 4, 30),
                date(2027, 5, 31),
                date(2027, 6, 30),
                date(2027, 7, 31),
                date(2027, 8, 31),
                date(2027, 9, 30),
                date(2027, 10, 31),
                date(2027, 11, 30),
                date(2027, 12, 31),
                date(2028, 1, 31),
            ],
        )

    def test_monthly_twelve_steps_from_the_30th_never_drift(self):
        expected = [date(2027, 2, 28)]
        expected += [date(2027, month, 30) for month in range(3, 13)]
        expected += [date(2028, 1, 30)]
        self.assertEqual(self.chain(date(2027, 1, 30), "monthly", 12, day=30), expected)

    def test_monthly_twelve_steps_from_the_28th_never_drift(self):
        # No remembered day is needed for the 28th: every month has one. In
        # a year that is not a leap year, 28 Feb is the last day of February,
        # and the old rule moved it to 31 Mar.
        for year in [2027, 2028]:
            with self.subTest(year=year):
                expected = [date(year, month, 28) for month in range(2, 13)]
                expected += [date(year + 1, 1, 28)]
                self.assertEqual(self.chain(date(year, 1, 28), "monthly", 12), expected)

    def test_monthly_twelve_steps_from_the_15th(self):
        expected = [date(2027, month, 15) for month in range(1, 13)]
        self.assertEqual(self.chain(date(2026, 12, 15), "monthly", 12), expected)

    def test_year_9999_is_too_far(self):
        # The last date Python has is 31 Dec 9999. The caller makes no copy.
        for repeat, start in [
            ("daily", date(9999, 12, 31)),
            ("weekly", date(9999, 12, 28)),
            ("monthly", date(9999, 12, 15)),
        ]:
            with self.subTest(repeat=repeat):
                with self.assertRaises(OverflowError):
                    next_due_date(start, repeat)

    def test_none_is_a_mistake(self):
        with self.assertRaises(ValueError):
            next_due_date(date(2026, 10, 12), "none")

    def test_unknown_word_is_a_mistake(self):
        with self.assertRaises(ValueError):
            next_due_date(date(2026, 10, 12), "yearly")
