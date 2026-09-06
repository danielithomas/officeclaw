"""
Tests for the shared recurrence shorthand used by tasks and calendar events.

The shorthand comes from PR #9 (danbryant201), extended with the range
handling calendar events already had.
"""

from __future__ import annotations

import pytest

from officeclaw import recurrence

# 2026-09-08 is a Tuesday.
START = "2026-09-08"


class TestPatterns:
    def test_daily(self):
        assert recurrence.build("daily", START)["pattern"] == {"type": "daily", "interval": 1}

    def test_daily_with_interval(self):
        assert recurrence.build("daily:3", START)["pattern"]["interval"] == 3

    def test_weekly_defaults_to_the_start_weekday(self):
        assert recurrence.build("weekly", START)["pattern"]["daysOfWeek"] == ["tuesday"]

    def test_weekly_with_named_days(self):
        pattern = recurrence.build("weekly:MON,WED", START)["pattern"]
        assert pattern["daysOfWeek"] == ["monday", "wednesday"]

    def test_day_names_are_case_and_length_insensitive(self):
        pattern = recurrence.build("weekly:monday,fri", START)["pattern"]
        assert pattern["daysOfWeek"] == ["monday", "friday"]

    def test_duplicate_days_collapse(self):
        assert recurrence.build("weekly:MON,MON", START)["pattern"]["daysOfWeek"] == ["monday"]

    def test_fortnightly_is_every_second_week(self):
        pattern = recurrence.build("fortnightly", START)["pattern"]
        assert (pattern["type"], pattern["interval"]) == ("weekly", 2)

    def test_weekdays(self):
        assert recurrence.build("weekdays", START)["pattern"]["daysOfWeek"] == [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
        ]

    def test_monthly_defaults_to_the_start_day(self):
        assert recurrence.build("monthly", START)["pattern"]["dayOfMonth"] == 8

    def test_monthly_with_explicit_day(self):
        assert recurrence.build("monthly:15", START)["pattern"]["dayOfMonth"] == 15

    def test_yearly_pins_day_and_month(self):
        pattern = recurrence.build("yearly", START)["pattern"]
        assert (pattern["dayOfMonth"], pattern["month"]) == (8, 9)

    def test_iso_datetime_start_is_accepted(self):
        assert recurrence.build("weekly", "2026-09-08T10:00:00")["pattern"]["daysOfWeek"] == [
            "tuesday"
        ]


class TestRange:
    def test_open_ended_by_default(self):
        assert recurrence.build("daily", START)["range"]["type"] == "noEnd"

    def test_until_gives_an_end_date(self):
        rng = recurrence.build("daily", START, until="2026-12-01")["range"]
        assert (rng["type"], rng["endDate"]) == ("endDate", "2026-12-01")

    def test_count_gives_a_numbered_range(self):
        rng = recurrence.build("daily", START, count=6)["range"]
        assert (rng["type"], rng["numberOfOccurrences"]) == ("numbered", 6)

    def test_timezone_is_carried(self):
        rng = recurrence.build("daily", START, timezone="Australia/Melbourne")["range"]
        assert rng["recurrenceTimeZone"] == "Australia/Melbourne"


class TestRejections:
    @pytest.mark.parametrize(
        "spec", ["hourly", "weekly:XYZ", "daily:many", "daily:0", "monthly:0", "monthly:41"]
    )
    def test_bad_specs_are_refused(self, spec):
        with pytest.raises(ValueError):
            recurrence.build(spec, START)

    def test_until_and_count_together(self):
        with pytest.raises(ValueError, match="not both"):
            recurrence.build("daily", START, until="2026-12-01", count=3)

    def test_bad_start_date(self):
        with pytest.raises(ValueError, match="valid start date"):
            recurrence.build("daily", "not-a-date")

    def test_error_names_the_accepted_spellings(self):
        with pytest.raises(ValueError, match="weekly:MON,WED"):
            recurrence.build("hourly", START)
