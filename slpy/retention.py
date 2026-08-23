"""
Retention policies for slpy — compliance metadata as data.

Declare named policies once at init(); tag logs with with_retention(name).
Every tagged entry is stamped with `retention` / `retention_class` and, when the
policy declares a period, `retention_until` — the date the mandatory window ends,
materialized at write time so a downstream sweep is a range scan rather than a
policy interpretation. slpy attaches the metadata — storage and expiry are the
transport's job, and `retention_until` is not an expiry: reaching it ends the
obligation, it does not authorize deletion.

    await slpy.init({
        'retention_policies': {
            'SOX_AUDIT_TRAIL': {'years': 7, 'class': 'SOX'},
            'GDPR_ACCESS':     {'days': 90, 'class': 'GDPR'},
        },
    })

    audit = slpy.get_logger('payments').with_retention('SOX_AUDIT_TRAIL')
    audit.audit('Manager override', user_id='u-1')
    # → retention: 'SOX_AUDIT_TRAIL'  retention_class: 'SOX'  retention_until: '2033-08-23'

Prefer the calendar unit. `days` is exact but drifts: 2555 is 7 × 365, misses two
leap days, and ends two days before seven actual years.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from . import retention_window


class RetentionConfigurationError(ValueError):
    """
    A retention policy that cannot be interpreted. Raised while the registry is
    built — at startup, never from the logging path — because an ambiguous
    compliance window has no safe default: picking one silently would mean
    records swept on a date nobody chose. Failing to start is loud, immediate and
    fixable; the alternative is discovered at audit time.
    """


class RetentionPolicyNotFoundError(KeyError):
    """
    `with_retention(name)` was given a name that is not registered.

    Raised where the logger is BUILT, never from a log call: slpy's promise is
    that logging cannot throw, and this does not touch it. The caller is deciding
    how long to keep a record — a typo that travels silently is a record with no
    retention, discovered at audit time rather than at deploy time.
    """

    def __init__(self, name: str, available: Tuple[str, ...]) -> None:
        self.policy = name
        self.available = available
        hint = (
            "Registered policies: [{}].".format(", ".join(available))
            if available
            else "No retention policies are registered. Set 'retention_policies' in "
                 "init(), or pass an inline dict instead of a name."
        )
        super().__init__("Retention policy '{}' is not registered. {}".format(name, hint))

    def __str__(self) -> str:
        # KeyError's __str__ wraps the message in quotes; the message is already a sentence.
        return self.args[0]


@dataclass(frozen=True)
class RetentionPolicy:
    """
    A named retention policy: how long, and under which compliance class.

    Declare exactly ONE unit. `years` and `months` are calendar periods and
    round long (see `retention_window`); `days` is exact but drifts against a
    calendar window. Declaring more than one is refused when the registry is built.
    """

    days: int = 0
    months: int = 0
    years: int = 0
    klass: str = ""


def _to_policy(raw: Union[RetentionPolicy, Dict[str, Any]]) -> RetentionPolicy:
    if isinstance(raw, RetentionPolicy):
        return raw
    return RetentionPolicy(
        days=int(raw.get("days", 0)),
        months=int(raw.get("months", 0)),
        years=int(raw.get("years", 0)),
        klass=str(raw.get("class", "")),
    )


class RetentionRegistry:
    """
    Resolves policy names to `RetentionPolicy` metadata.

    Lookup is case-insensitive for convenience, but the name that travels on the
    entry is always the spelling the policy was REGISTERED with. Everything
    downstream — Loki label matchers, index filters, a sweep's `WHERE` clause —
    matches an exact low-cardinality string, so one policy must not be able to
    appear under two labels depending on how a caller typed it.

    The registry is frozen. A compliance registry that could change after
    construction would let a window be redefined for records already written
    under the old one.
    """

    def __init__(self, policies: Dict[str, RetentionPolicy]) -> None:
        # Two frozen maps over a COPY: lookups by lowercase name, and the
        # canonical spelling each name was registered with.
        normalized: Dict[str, RetentionPolicy] = {}
        canonical: Dict[str, str] = {}
        for name, policy in policies.items():
            key = str(name).lower()
            normalized[key] = policy
            canonical[key] = str(name)
        self._policies = MappingProxyType(normalized)
        self._canonical = MappingProxyType(canonical)

    @classmethod
    def create(cls, raw: Optional[Dict[str, Any]]) -> "RetentionRegistry":
        """
        Build from config. None/empty → an empty registry.

        Raises `RetentionConfigurationError` if a policy declares more than one
        unit. This runs while the services are built — at startup, not on the
        logging path.
        """
        if not raw:
            return cls({})

        policies: Dict[str, RetentionPolicy] = {}
        for name, value in raw.items():
            policy = _to_policy(value)
            if retention_window.has_ambiguous_unit(policy):
                raise RetentionConfigurationError(
                    "Retention policy '{}' declares more than one unit "
                    "(days={}, months={}, years={}). Declare exactly one.".format(
                        name, policy.days, policy.months, policy.years
                    )
                )
            policies[str(name)] = policy
        return cls(policies)

    @property
    def policies(self) -> Mapping[str, RetentionPolicy]:
        """Every registered policy, keyed by its canonical name. Read-only —
        the return type says so: a `Mapping` has no mutators, and what comes
        back is a `MappingProxyType` that refuses them at runtime too."""
        return MappingProxyType(
            {self._canonical.get(key, key): value for key, value in self._policies.items()}
        )

    def resolve(self, name: str) -> Optional[RetentionPolicy]:
        """The policy, or None. For callers where a miss is a branch, not a bug.

        Unchanged on purpose. sl4n spells the loud form `Resolve` and the quiet
        one `TryResolve`; slpy already shipped `resolve` as the quiet one, and
        making the same name throw would be the worst kind of break — same call,
        same signature, different failure mode. The loud form is `require`.
        """
        return self._policies.get(name.lower())

    def require(self, name: str) -> RetentionPolicy:
        """
        The policy, or `RetentionPolicyNotFoundError` carrying the sorted list of
        registered names. The form for a caller deciding how long to keep a
        record: a None there persists it with no retention at all.
        """
        policy = self._policies.get(name.lower())
        if policy is None:
            raise RetentionPolicyNotFoundError(name, tuple(sorted(self.policies)))
        return policy

    def canonical_name(self, name: str) -> str:
        """The spelling `name` was registered with. Raises if it is not registered."""
        self.require(name)
        return self._canonical.get(name.lower(), name)

    def until(self, name: str, at: datetime) -> Optional[date]:
        """
        The date `name`'s window ends, counted from `at` in UTC — the same answer,
        from the same registry and the same arithmetic, that the logger stamps as
        `retention_until`. For a write path outside the logger that persists
        retention in its own column. Raises if the name is not registered.
        """
        return retention_window.until(utc_date(at), self.require(name))

    def stamp(self, name_or_policy: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        The static fields a tagged entry carries. Pure. `retention_until` is NOT
        here: it depends on when the entry is written, so the logger computes it
        per entry rather than freezing it into the bindings.

        - Registered name → canonical name + class (+ days, when declared in days).
        - Inline dict → the anonymous policy's fields, with no name to route on.
        - Unregistered name → `RetentionPolicyNotFoundError`.
        """
        if isinstance(name_or_policy, dict):
            policy = _to_policy(name_or_policy)
            return _policy_fields(policy)

        policy = self.require(name_or_policy)
        return dict(
            retention=self.canonical_name(name_or_policy), **_policy_fields(policy)
        )


def utc_date(at: datetime) -> date:
    """The UTC calendar date of `at`. An aware datetime is converted first: a
    record written at 21:00 in UTC-5 belongs to the NEXT UTC day, and the window
    has to be anchored the same way the logger stamps it or the two answers
    disagree by a day. A naive datetime is taken as given — guessing a zone for
    it would be worse than honouring what the caller passed.
    """
    if at.tzinfo is None:
        return at.date()
    return at.astimezone(timezone.utc).date()


def _policy_fields(policy: RetentionPolicy) -> Dict[str, Any]:
    """Class and, only when the policy is declared in days, the day count. A
    policy declared in years has no day count and slpy will not invent one — the
    materialized `retention_until` is what such a policy travels with."""
    fields: Dict[str, Any] = {"retention_class": policy.klass}
    if policy.days > 0:
        fields["retention_days"] = policy.days
    return fields
