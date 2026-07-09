"""
Logging Matrix for slpy.

A declarative whitelist that decides WHICH CONTEXT FIELDS appear at each log
level. A context field not whitelisted for a level never reaches a transport.

The matrix governs only the auto-propagating context (slpy.context(...) /
ContextManager fields). Core fields (level, message, timestamp, service),
child() bindings and per-call kwargs are never filtered — if you don't want a
per-call field logged, don't pass it.

Config:

    await slpy.init({
        'logging_matrix': {
            'default': ['correlation_id'],
            'info':    ['correlation_id', 'user_id', 'operation'],
            'error':   ['*'],
        },
    })

Semantics (identical across SyntropyLog / sl4n / slpy):
- No matrix configured           → every context field passes (backward compatible).
- Level listed                   → only those fields pass.
- Level not listed               → the 'default' entry applies.
- Neither level nor 'default'    → ALL context is dropped for that level
                                   (strict whitelist — always define 'default').
- A list containing '*'          → every context field passes at that level.
"""

from typing import Dict, FrozenSet, List, Optional

DEFAULT_KEY = "default"
WILDCARD = "*"

_EMPTY: FrozenSet[str] = frozenset()


class LoggingMatrix:
    """
    Per-level whitelist of context fields. Build via LoggingMatrix.create().

    allowed_fields(level) returns:
        None            → every context field is allowed
        empty frozenset → drop all context fields
        frozenset       → only these fields are allowed
    """

    def __init__(self, by_level: Dict[str, FrozenSet[str]], configured: bool) -> None:
        self._by_level = by_level
        self._configured = configured

    @classmethod
    def create(cls, matrix: Optional[Dict[str, List[str]]]) -> "LoggingMatrix":
        """Build a matrix from config. None/empty → no filtering."""
        if not matrix:
            return cls({}, configured=False)
        by_level = {
            str(level).lower(): frozenset(fields or [])
            for level, fields in matrix.items()
        }
        return cls(by_level, configured=True)

    @property
    def is_configured(self) -> bool:
        return self._configured

    def allowed_fields(self, level: str) -> Optional[FrozenSet[str]]:
        if not self._configured:
            return None
        allowed = self._by_level.get(level.lower())
        if allowed is None:
            allowed = self._by_level.get(DEFAULT_KEY)
        if allowed is None:
            return _EMPTY          # configured, but no level & no default → drop all context
        if WILDCARD in allowed:
            return None            # '*' → allow every context field
        return allowed

    def filter_context(self, level: str, ctx: Dict) -> Dict:
        """Return the subset of ctx allowed at this level (same dict if all pass)."""
        allowed = self.allowed_fields(level)
        if allowed is None:
            return ctx
        if not allowed:
            return {}
        return {k: v for k, v in ctx.items() if k in allowed}


#: A matrix that lets every context field through at every level.
EMPTY_MATRIX = LoggingMatrix({}, configured=False)
