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


def next_due_date(due: date, repeat: str, day: int | None = None) -> date:
    """The due date of the next copy, counted from this due date.

    Monthly comes back on `day`, the day of the month the person chose (the
    to-do remembers it). If the next month is shorter, it uses its last day:
    the 31st gives 28 Feb, then 31 Mar. Without `day`, it uses the due
    date's own day. Daily and weekly do not use `day`.

    "none" or an unknown word is a programming mistake: ValueError.
    A date after 31 Dec 9999 (the last one Python has): OverflowError.
    """
    if repeat == DAILY:
        return due + timedelta(days=1)
    if repeat == WEEKLY:
        return due + timedelta(days=7)
    if repeat == MONTHLY:
        year, month = (
            (due.year + 1, 1) if due.month == 12 else (due.year, due.month + 1)
        )
        if year > date.max.year:
            raise OverflowError("date value out of range")
        wanted = day or due.day
        return date(year, month, min(wanted, days_in_month(year, month)))
    raise ValueError(f"Not a repeat: {repeat!r}")
