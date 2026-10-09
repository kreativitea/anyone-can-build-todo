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

    def test_monthly_last_day_stays_last_day(self):
        self.assert_steps(
            "monthly",
            [
                (date(2027, 1, 31), date(2027, 2, 28)),
                (date(2028, 1, 31), date(2028, 2, 29)),
                (date(2027, 2, 28), date(2027, 3, 31)),
                (date(2028, 2, 29), date(2028, 3, 31)),
                (date(2027, 3, 31), date(2027, 4, 30)),
                (date(2027, 4, 30), date(2027, 5, 31)),
                (date(2027, 6, 30), date(2027, 7, 31)),
                (date(2027, 8, 31), date(2027, 9, 30)),
                (date(2027, 9, 30), date(2027, 10, 31)),
                (date(2027, 11, 30), date(2027, 12, 31)),
                (date(2026, 12, 31), date(2027, 1, 31)),
            ],
        )

    def test_monthly_short_month(self):
        self.assert_steps(
            "monthly",
            [
                (date(2027, 1, 29), date(2027, 2, 28)),
                (date(2027, 1, 30), date(2027, 2, 28)),
                (date(2028, 1, 30), date(2028, 2, 29)),
            ],
        )

    def test_monthly_29_and_30_move_to_month_end_after_february(self):
        # The accepted drift: a day that happens to be the last day of its
        # month is treated as "the end of the month" from then on.
        self.assert_steps(
            "monthly",
            [
                (date(2027, 1, 30), date(2027, 2, 28)),
                (date(2027, 2, 28), date(2027, 3, 31)),
                (date(2027, 3, 29), date(2027, 4, 29)),  # not the last day: stays
                (date(2027, 3, 30), date(2027, 4, 30)),
                (date(2027, 4, 30), date(2027, 5, 31)),
            ],
        )

    def chain(self, start, repeat, steps):
        """The dates after calling next_due_date `steps` times in a row."""
        dates = []
        for _ in range(steps):
            start = next_due_date(start, repeat)
            dates.append(start)
        return dates

    def test_monthly_twelve_steps_from_the_31st(self):
        self.assertEqual(
            self.chain(date(2027, 1, 31), "monthly", 12),
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

    def test_monthly_twelve_steps_from_the_15th(self):
        expected = [date(2027, month, 15) for month in range(1, 13)]
        self.assertEqual(self.chain(date(2026, 12, 15), "monthly", 12), expected)

    def test_none_is_a_mistake(self):
        with self.assertRaises(ValueError):
            next_due_date(date(2026, 10, 12), "none")

    def test_unknown_word_is_a_mistake(self):
        with self.assertRaises(ValueError):
            next_due_date(date(2026, 10, 12), "yearly")
