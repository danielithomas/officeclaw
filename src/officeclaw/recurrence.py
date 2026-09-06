"""
Recurrence patterns, shared by calendar events and tasks.

Microsoft Graph expresses recurrence as a ``patternedRecurrence`` — a pattern
(how often) plus a range (until when). Both events and tasks use the same
shape, so the shorthand people type on the command line is parsed once here.

Accepted spellings, from simplest up:

    daily              every day
    daily:3            every third day
    weekly             weekly, on the weekday the series starts
    weekly:MON,WED     weekly, on the named days
    fortnightly        every second week
    weekdays           Monday to Friday
    monthly            monthly, on the day of month the series starts
    monthly:15         monthly, on the 15th
    yearly             annually, on the start date

Full RRULE is deliberately not supported: these cover what a CLI is for.

Derived from the shorthand proposed in PR #9 by danbryant201, extended with the
range handling (``until`` / ``count``) already used for calendar events.
"""

from __future__ import annotations

from datetime import date
from typing import Any

DAY_NAMES = {
    "MON": "monday",
    "TUE": "tuesday",
    "WED": "wednesday",
    "THU": "thursday",
    "FRI": "friday",
    "SAT": "saturday",
    "SUN": "sunday",
}

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]

KINDS = ("daily", "weekly", "fortnightly", "weekdays", "monthly", "yearly")


def build(
    spec: str,
    start: str,
    until: str | None = None,
    count: int | None = None,
    timezone: str = "UTC",
) -> dict[str, Any]:
    """
    Turn a shorthand recurrence spec into a Graph patternedRecurrence.

    Args:
        spec: One of the accepted spellings above
        start: First occurrence, as a date or ISO datetime
        until: Last date the series may run to
        count: Number of occurrences (alternative to ``until``)
        timezone: Timezone the range is expressed in

    Returns:
        A patternedRecurrence object

    Raises:
        ValueError: If the spec is unrecognised, its argument is not a number
            where one is required, a weekday abbreviation is unknown, or both
            ``until`` and ``count`` are given.
    """
    if until and count:
        raise ValueError("Give either an end date or an occurrence count, not both.")

    kind, _, argument = spec.strip().lower().partition(":")
    start_date = start.split("T")[0]

    try:
        anchor = date.fromisoformat(start_date)
    except ValueError as e:
        raise ValueError(f"Recurrence needs a valid start date, got {start!r}.") from e

    pattern = _pattern(kind, argument, anchor, spec)
    return {"pattern": pattern, "range": _range(start_date, until, count, timezone)}


def _pattern(kind: str, argument: str, anchor: date, spec: str) -> dict[str, Any]:
    """Build the pattern half, which is where the shorthand's argument applies."""
    if kind == "daily":
        return {"type": "daily", "interval": _interval(argument, spec)}

    if kind in ("weekly", "fortnightly"):
        interval = 2 if kind == "fortnightly" else 1
        days = _weekdays(argument, spec) if argument else [anchor.strftime("%A").lower()]
        return {
            "type": "weekly",
            "interval": interval,
            "daysOfWeek": days,
            "firstDayOfWeek": "sunday",
        }

    if kind == "weekdays":
        return {
            "type": "weekly",
            "interval": 1,
            "daysOfWeek": list(WEEKDAYS),
            "firstDayOfWeek": "sunday",
        }

    if kind == "monthly":
        return {
            "type": "absoluteMonthly",
            "interval": 1,
            "dayOfMonth": _day_of_month(argument, anchor, spec),
        }

    if kind == "yearly":
        return {
            "type": "absoluteYearly",
            "interval": 1,
            "dayOfMonth": anchor.day,
            "month": anchor.month,
        }

    raise ValueError(
        f"Unrecognised recurrence {spec!r}. Expected one of: {', '.join(KINDS)} — "
        "optionally with an argument, such as daily:3, weekly:MON,WED or monthly:15."
    )


def _range(start_date: str, until: str | None, count: int | None, timezone: str) -> dict[str, Any]:
    """Build the range half: open-ended, until a date, or a fixed count."""
    if until:
        recurrence_range: dict[str, Any] = {
            "type": "endDate",
            "startDate": start_date,
            "endDate": until,
        }
    elif count:
        recurrence_range = {
            "type": "numbered",
            "startDate": start_date,
            "numberOfOccurrences": count,
        }
    else:
        recurrence_range = {"type": "noEnd", "startDate": start_date}

    recurrence_range["recurrenceTimeZone"] = timezone
    return recurrence_range


def _interval(argument: str, spec: str) -> int:
    if not argument:
        return 1
    try:
        interval = int(argument)
    except ValueError as e:
        raise ValueError(f"{spec!r}: interval must be a number, e.g. daily:3.") from e
    if interval < 1:
        raise ValueError(f"{spec!r}: interval must be at least 1.")
    return interval


def _weekdays(argument: str, spec: str) -> list[str]:
    days = []
    for token in argument.split(","):
        name = DAY_NAMES.get(token.strip().upper()[:3])
        if name is None:
            raise ValueError(
                f"{spec!r}: unknown day {token.strip()!r}. Expected: {', '.join(DAY_NAMES)}."
            )
        if name not in days:
            days.append(name)
    return days


def _day_of_month(argument: str, anchor: date, spec: str) -> int:
    if not argument:
        return anchor.day
    try:
        day = int(argument)
    except ValueError as e:
        raise ValueError(f"{spec!r}: day of month must be a number, e.g. monthly:15.") from e
    if not 1 <= day <= 31:
        raise ValueError(f"{spec!r}: day of month must be between 1 and 31.")
    return day
