"""
Retention policies for slpy — compliance metadata as data.

Declare named policies once at init(); tag logs with with_retention(name).
Every tagged entry is stamped with `retention` / `retention_class` /
`retention_days` so a downstream store can route and expire it by policy.
slpy attaches the metadata — storage/expiry is the transport's job.

    await slpy.init({
        'retention_policies': {
            'SOX_AUDIT_TRAIL': {'days': 2555, 'class': 'SOX'},
            'GDPR_ACCESS':     {'days': 90,   'class': 'GDPR'},
        },
    })

    audit = slpy.get_logger('payments').with_retention('SOX_AUDIT_TRAIL')
    audit.audit('Manager override', user_id='u-1')
    # → retention: 'SOX_AUDIT_TRAIL'  retention_class: 'SOX'  retention_days: 2555
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union


@dataclass(frozen=True)
class RetentionPolicy:
    """A named retention policy: how long, and under which compliance class."""

    days: int = 0
    klass: str = ""


def _to_policy(raw: Union["RetentionPolicy", Dict[str, Any]]) -> RetentionPolicy:
    if isinstance(raw, RetentionPolicy):
        return raw
    return RetentionPolicy(days=int(raw.get("days", 0)), klass=str(raw.get("class", "")))


class RetentionRegistry:
    """Resolves policy names (case-insensitive) to RetentionPolicy metadata."""

    def __init__(self, policies: Dict[str, RetentionPolicy]) -> None:
        self._policies = policies

    @classmethod
    def create(cls, raw: Optional[Dict[str, Any]]) -> "RetentionRegistry":
        """Build from config. None/empty → an empty registry."""
        if not raw:
            return cls({})
        return cls({str(name).lower(): _to_policy(policy) for name, policy in raw.items()})

    def resolve(self, name: str) -> Optional[RetentionPolicy]:
        return self._policies.get(name.lower())

    def stamp(self, name_or_policy: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """The fields a tagged entry carries. Pure.

        - Registered name → name + class + days.
        - Unregistered name → the name alone still travels (better an
          unresolved tag downstream than silently dropping compliance intent).
        - Inline dict {'days': ..., 'class': ...} → anonymous policy fields.
        """
        if isinstance(name_or_policy, dict):
            policy = _to_policy(name_or_policy)
            return {"retention_class": policy.klass, "retention_days": policy.days}
        policy = self.resolve(name_or_policy)
        if policy is None:
            return {"retention": name_or_policy}
        return {
            "retention": name_or_policy,
            "retention_class": policy.klass,
            "retention_days": policy.days,
        }
