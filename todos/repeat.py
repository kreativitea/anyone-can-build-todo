"""The date math for repeating to-dos.

A pure function: it only takes values and gives back a value. It never reads
the database or the clock, so the tests can try many dates.
"""

import calendar
from datetime import date, timedelta

# The words the database keeps. The model's choices use these, so there is one spelling.
NONE = "none"
DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"


def days_in_month(year, month):
    """28, 29, 30 or 31. calendar knows the leap years."""
    return calendar.monthrange(year, month)[1]


def next_due_date(due: date, repeat: str) -> date:
    """The due date of the next copy, counted from this due date.

    Monthly keeps the day number. The last day of a month goes to the last day
    of the next month. If the next month is too short, it uses its last day.
    "none" or an unknown word is a programming mistake: ValueError.
    """
    if repeat == DAILY:
        return due + timedelta(days=1)
    if repeat == WEEKLY:
        return due + timedelta(days=7)
    if repeat == MONTHLY:
        year, month = (
            (due.year + 1, 1) if due.month == 12 else (due.year, due.month + 1)
        )
        last = days_in_month(year, month)
        if due.day == days_in_month(due.year, due.month):
            return date(year, month, last)
        return date(year, month, min(due.day, last))
    raise ValueError(f"Not a repeat: {repeat!r}")
