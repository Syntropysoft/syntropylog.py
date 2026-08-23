"""
When a retention window ends. Pure arithmetic, no I/O, no state.

Materializing the date at write time is what turns a compliance sweep into an
indexable range scan (`WHERE retention_until < CURRENT_DATE`) instead of a policy
interpretation, and it means a record filed under an older revision of a policy
keeps the window that was in force when it was written.

**The rounding errs long, on purpose.** 31-Jan plus one month has no 31-Feb to
land on. Clamping backwards to 28-Feb — which is what most date libraries do,
including .NET's `AddMonths` — ends a window up to three days early, the exact
failure retention exists to prevent. slpy rolls forward to 3-Mar, matching the
Node reference and sl4n: a record kept a day too long costs storage, a record
swept a day too early costs an audit finding.
"""

import calendar
from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .retention import RetentionPolicy


def to_iso(value: date) -> str:
    """`YYYY-MM-DD`, always. Never the locale's idea of a date."""
    return value.isoformat()


def _is_whole_positive(value: object) -> bool:
    """A usable count is a whole number above zero. `bool` is an `int` in Python
    and `True` would otherwise read as 1 year, which nobody meant to declare."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _add_months_rolling_forward(at: date, months: int) -> date:
    """`at` plus N calendar months, rolling into the next month rather than
    clamping when the target month is too short."""
    total = at.month - 1 + months
    year = at.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    if at.day <= last_day:
        return date(year, month, at.day)
    return date(year, month, last_day) + timedelta(days=at.day - last_day)


def until(at: date, policy: "RetentionPolicy") -> Optional[date]:
    """
    The date `policy`'s window ends, counted from `at`.

    Exactly one unit is expected — a policy declaring more than one is rejected
    when the registry is built, not here. `None` when the policy declares no
    usable unit: there is nothing to compute and the framework does not invent a
    date for a compliance column.
    """
    if _is_whole_positive(policy.years):
        return _add_months_rolling_forward(at, policy.years * 12)
    if _is_whole_positive(policy.months):
        return _add_months_rolling_forward(at, policy.months)
    if _is_whole_positive(policy.days):
        return at + timedelta(days=policy.days)
    return None


# Public alias. Inside the package the function is `until` because it is always
# read as `retention_window.until(...)`; exported from `slpy` it needs to say what
# it computes, and `retention_until` is the name the Node sibling exports too.
retention_until = until


def has_ambiguous_unit(policy: "RetentionPolicy") -> bool:
    """True when the policy declares more than one unit — see `RetentionRegistry.create`."""
    declared = (
        _is_whole_positive(policy.days),
        _is_whole_positive(policy.months),
        _is_whole_positive(policy.years),
    )
    return sum(declared) > 1
