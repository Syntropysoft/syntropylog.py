"""The retention arithmetic. Pure functions, so these are plain table tests.

The property under test everywhere: **the window never ends early.** Ending it
early is the failure retention exists to prevent; ending it late costs storage.
"""

from datetime import date

import pytest

from slpy.retention import RetentionPolicy
from slpy.retention_window import has_ambiguous_unit, to_iso, until


def _until(at, **policy):
    return until(at, RetentionPolicy(**policy))


# ---------------------------------------------------------------------------
# Short months roll FORWARD, never back
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("at,months,expected", [
    # 31-Jan has no 31-Feb to land on. Clamping (what .NET's AddMonths does, and
    # what a naive replace(month=...) cannot even express) would give 28-Feb and
    # end the window three days early.
    (date(2026, 1, 31), 1, date(2026, 3, 3)),    # Feb 2026: 28 days
    (date(2024, 1, 31), 1, date(2024, 3, 2)),    # Feb 2024: 29 days, one day less to roll
    (date(2026, 3, 31), 1, date(2026, 5, 1)),    # April: 30 days
    (date(2026, 5, 31), 1, date(2026, 7, 1)),    # June: 30 days
    (date(2026, 8, 31), 1, date(2026, 10, 1)),   # September: 30 days
    (date(2026, 10, 31), 1, date(2026, 12, 1)),  # November: 30 days
    (date(2026, 11, 30), 3, date(2027, 3, 2)),   # across the year boundary, into short Feb
    (date(2026, 1, 31), 13, date(2027, 3, 3)),   # more than a year of months
])
def test_short_month_rolls_forward(at, months, expected):
    assert _until(at, months=months) == expected
    assert _until(at, months=months) > at


@pytest.mark.parametrize("at,months,expected", [
    (date(2026, 8, 23), 1, date(2026, 9, 23)),
    (date(2026, 8, 23), 12, date(2027, 8, 23)),
    (date(2026, 1, 15), 6, date(2026, 7, 15)),
    (date(2026, 12, 1), 1, date(2027, 1, 1)),    # December wraps the year
])
def test_month_arithmetic_when_the_day_exists(at, months, expected):
    assert _until(at, months=months) == expected


# ---------------------------------------------------------------------------
# Leap day
# ---------------------------------------------------------------------------

def test_leap_day_rolls_forward():
    """29-Feb plus one year has no 29-Feb to land on: 1-Mar, kept one day longer."""
    assert _until(date(2024, 2, 29), years=1) == date(2025, 3, 1)


def test_leap_day_lands_exactly_when_the_target_year_is_also_leap():
    assert _until(date(2024, 2, 29), years=4) == date(2028, 2, 29)


def test_year_arithmetic_ordinary_case():
    assert _until(date(2026, 8, 23), years=7) == date(2033, 8, 23)


# ---------------------------------------------------------------------------
# Why the docs say "prefer the calendar unit"
# ---------------------------------------------------------------------------

def test_2555_days_is_not_seven_years():
    """2555 = 7 x 365. It misses the leap days in between and ends the window
    early — which is the whole reason `years` exists as a unit."""
    at = date(2026, 8, 23)
    assert _until(at, years=7) == date(2033, 8, 23)
    assert _until(at, days=2555) == date(2033, 8, 21)
    assert _until(at, days=2555) < _until(at, years=7)


def test_days_are_exact():
    assert _until(date(2026, 8, 23), days=90) == date(2026, 11, 21)


# ---------------------------------------------------------------------------
# Nothing declared means nothing computed — never a guess
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("policy", [
    {},                       # no unit at all
    {"days": 0},
    {"months": 0},
    {"years": 0},
    {"days": -30},            # negative: not a window
    {"years": -1},
], ids=["empty", "zero-days", "zero-months", "zero-years", "negative-days", "negative-years"])
def test_no_usable_unit_yields_no_date(policy):
    assert _until(date(2026, 8, 23), **policy) is None


def test_true_is_not_one_year():
    """`bool` is an `int` in Python, so `years=True` would otherwise read as one
    year — a compliance window nobody declared."""
    assert _until(date(2026, 8, 23), years=True) is None


# ---------------------------------------------------------------------------
# Precedence and ambiguity
# ---------------------------------------------------------------------------

def test_years_wins_over_the_smaller_units():
    """Only reachable by constructing a RetentionPolicy directly — the registry
    refuses an ambiguous one at startup. Pinned so the order is not accidental."""
    assert _until(date(2026, 8, 23), days=1, months=1, years=1) == date(2027, 8, 23)


@pytest.mark.parametrize("policy,ambiguous", [
    ({"days": 90}, False),
    ({"months": 3}, False),
    ({"years": 7}, False),
    ({}, False),
    ({"days": 90, "months": 3}, True),
    ({"days": 90, "years": 7}, True),
    ({"months": 3, "years": 7}, True),
    ({"days": 90, "months": 3, "years": 7}, True),
    ({"days": 0, "years": 7}, False),      # a zero is not a declaration
])
def test_has_ambiguous_unit(policy, ambiguous):
    assert has_ambiguous_unit(RetentionPolicy(**policy)) is ambiguous


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_to_iso_is_not_locale_dependent():
    assert to_iso(date(2033, 8, 23)) == "2033-08-23"
