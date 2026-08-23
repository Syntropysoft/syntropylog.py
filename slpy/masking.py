"""
MaskingEngine for slpy.

Masking is BY FIELD NAME, never free text: a value is masked when its key
(or an ancestor key) matches a rule. Free-text strings, array elements and
the log message are never scanned for PII — log-data quality is the
caller's responsibility.

The engine is a pure recursive transform: rules are matched against each
dict key on the way down; once a key matches, everything beneath it is
masked (nested dicts, lists, and non-string scalars included — an int
under `password` is just as sensitive as a string).

If slpy-native (Rust addon) is installed, MaskingEngine automatically
delegates to NativeMaskingEngine — same semantics, better performance.
Disable with: SLPY_NATIVE_DISABLE=1
"""

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from ._regex_safety import assert_safe_key_pattern
from .mask_spec import MaskSpec, apply_mask

# ---------------------------------------------------------------------------
# Native addon — loaded once, used transparently
# ---------------------------------------------------------------------------
# The boundary is versioned. An addon built against an older contract exposes a
# different ENGINE_API (or none at all), and the import below fails — which is
# the point: slpy drops to the Python engine rather than run an engine whose
# semantics it cannot vouch for. Two engines that disagree is the bug family
# this whole parity apparatus exists to prevent.
_REQUIRED_ENGINE_API = 2

_native: Any = None
if os.environ.get("SLPY_NATIVE_DISABLE", "").strip() not in ("1", "true", "yes"):
    try:
        from slpy_native import ENGINE_API as _NATIVE_API
        from slpy_native import NativeMaskingEngine as _NativeMaskingEngine
        if _NATIVE_API == _REQUIRED_ENGINE_API:
            _native = _NativeMaskingEngine
    except ImportError:
        pass


class MaskingStrategy(Enum):
    CREDIT_CARD = "credit_card"
    SSN = "ssn"
    EMAIL = "email"
    PHONE = "phone"
    PASSWORD = "password"
    TOKEN = "token"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Strategies as data — the canonical mapping, and the only one in the project
# ---------------------------------------------------------------------------

def strategy_to_spec(
    strategy: MaskingStrategy,
    mask_char: str = "*",
    preserve_length: bool = True,
) -> MaskSpec:
    """
    Expand a built-in strategy into the :class:`MaskSpec` both engines interpret.
    Byte-for-byte the family mapping (``strategyToSpec`` in the Node reference),
    which is why a card masked by slpy now reads the same as one masked by
    SyntropyLog, sl4n or the JVM port.

    Identifiers (email / phone / card / ssn) keep a format-preserving partial —
    the last 4 of an identifier is not the secret and it is what makes a log
    debuggable. Credentials are redacted whole: a length-preserving password
    mask publishes the length.

    This mapping lives here and nowhere else. The Rust engine receives the
    resolved spec and never learns what a strategy is, so the two cannot drift.
    """
    if strategy is MaskingStrategy.EMAIL:
        return MaskSpec(
            unmask_start=1, keep_after="@", mask_char=mask_char, preserve_length=preserve_length
        )
    if strategy in (MaskingStrategy.CREDIT_CARD, MaskingStrategy.SSN, MaskingStrategy.PHONE):
        return MaskSpec(
            scope="digits", unmask_end=4, mask_char=mask_char, preserve_length=preserve_length
        )
    if strategy in (MaskingStrategy.PASSWORD, MaskingStrategy.TOKEN):
        return MaskSpec(redact=True)
    # CUSTOM without a callable, and anything unforeseen: mask every character.
    return MaskSpec(mask_char=mask_char, preserve_length=preserve_length)


@dataclass
class MaskingRule:
    """
    A key pattern plus what to do with the values under it.

    `strategy` is the shorthand; `spec` is the same thing said directly, and it
    wins when both are given. A `spec` crosses to the Rust engine — a
    `custom_mask` callable cannot, and forces the Python engine for that rule.
    """

    pattern: str
    strategy: MaskingStrategy
    custom_mask: Optional[Callable[[str], str]] = None
    preserve_length: bool = True
    mask_char: str = "*"
    spec: Optional[MaskSpec] = None

    def __post_init__(self) -> None:
        # ReDoS defense happens HERE, at rule construction — not on the log hot path.
        # CPython's `re` cannot be interrupted mid-match (no timeout exists), so an
        # explosive pattern is rejected before it can ever run; the 256-char key cap
        # alone does NOT bound a nested quantifier (measured: (a+)+$ hangs at 40 chars).
        # Default rules are known-safe alternations and pass trivially.
        assert_safe_key_pattern(self.pattern)
        self._compiled = re.compile(self.pattern, re.IGNORECASE)
        # Resolved once, at construction: the single thing both engines interpret.
        self._spec = self.spec or strategy_to_spec(
            self.strategy, self.mask_char, self.preserve_length
        )


# ---------------------------------------------------------------------------
# Sensitive key aliases — the slpy equivalent of SyntropyLog's maskEnum and
# sl4n's MaskKeys. Reference these instead of string literals in custom rules
# (keeps patterns out of secret scanners such as Sonar S2068).
#
#     MaskingRule(mask_pattern(*MASK_KEYS['token']), MaskingStrategy.TOKEN)
# ---------------------------------------------------------------------------
MASK_KEYS: Dict[str, Tuple[str, ...]] = {
    "email":    ("email", "mail"),
    "password": ("password", "pass", "pwd", "secret"),
    "token":    ("token", "key", "auth", "jwt", "bearer"),
    "card":     ("credit_card", "creditcard", "card_number", "cardnumber"),
    "ssn":      ("ssn", "social_security"),
    "phone":    ("phone", "mobile", "tel"),
}
MASK_KEYS["all"] = tuple(k for group in (
    MASK_KEYS["email"], MASK_KEYS["password"], MASK_KEYS["token"],
    MASK_KEYS["card"], MASK_KEYS["ssn"], MASK_KEYS["phone"],
) for k in group)


def mask_pattern(*keys: str) -> str:
    """Anchored alternation (``^(a|b|c)$``) ready to use as a MaskingRule pattern."""
    return f"^({'|'.join(keys)})$"


# Loose suffix patterns catch derived names (creditCardNumber, ssn_number);
# the anchored alternates catch the bare aliases (credit_card, ssn, phone) —
# same coverage as sl4n's MaskingPatterns plus the derived forms.
_DEFAULT_RULES: List[MaskingRule] = [
    MaskingRule(r"(?:credit|card|cc|payment).*?(?:number|num|id)|^(?:credit_?card|card_?number)$", MaskingStrategy.CREDIT_CARD),
    MaskingRule(r"(?:ssn|social|security).*?(?:number|num)|^(?:ssn|social_?security)$", MaskingStrategy.SSN),
    MaskingRule(r"(?:email|mail|e-mail)", MaskingStrategy.EMAIL),
    MaskingRule(r"(?:phone|tel|mobile|cell).*?(?:number|num)|^(?:phone|mobile|tel|cell)$", MaskingStrategy.PHONE),
    MaskingRule(r"(?:password|pass|pwd|secret)", MaskingStrategy.PASSWORD),
    MaskingRule(r"(?:token|key|auth|jwt|bearer)", MaskingStrategy.TOKEN),
]

# ReDoS guard: rules only ever run against field NAMES (never values), and the
# name itself is capped — bounded input means bounded regex evaluation.
_MAX_KEY_LEN = 256

# Cap for the per-key-name decision cache. Bounded so attacker-controlled key
# names (a hostile payload generating unique keys per log) cannot grow memory:
# past the cap, new keys still mask correctly — they just pay the scan, uncached.
_DECISION_CACHE_MAX = 4096

# Cache-miss sentinel: a cached decision can legitimately be None ("no rule").
_MISS = object()

# Replacement for a container that still hides under a sensitive key when the
# depth budget runs out — fixed width so nothing about the value leaks.
_EXHAUSTED_MASK_LEN = 6

def _push_rule(engine: Any, rule: MaskingRule) -> None:
    """Hand one rule to the Rust engine as pattern + resolved spec. Pure plumbing:
    it reads the rule and calls the boundary, and decides nothing."""
    spec = rule._spec
    engine.add_rule(
        rule.pattern,
        redact=spec.redact,
        unmask_start=spec.unmask_start,
        unmask_end=spec.unmask_end,
        scope=spec.scope,
        keep_after=spec.keep_after,
        mask_char=spec.mask_char,
        preserve_length=spec.preserve_length,
    )


def _apply_strategy(value: str, rule: MaskingRule) -> str:
    if rule.strategy is MaskingStrategy.CUSTOM and rule.custom_mask is not None:
        return rule.custom_mask(value)
    return apply_mask(value, rule._spec)


# ---------------------------------------------------------------------------
# Tree walk — pure functions
# ---------------------------------------------------------------------------

def _scan_rules(name: str, rules: List[MaskingRule]) -> Optional[MaskingRule]:
    """The uncached scan: every rule, in order. Pure — depends only on name + rules."""
    for rule in rules:
        if rule._compiled.search(name):
            return rule
    return None


def _find_rule(
    key: Any,
    rules: List[MaskingRule],
    cache: Dict[str, Optional[MaskingRule]],
) -> Optional[MaskingRule]:
    """First rule whose pattern matches the field name (first match wins), served
    from the bounded decision cache when the key name has been seen before.

    Field NAMES repeat across log entries while values change, and the scan runs
    every rule regex per key — so caching the decision (rule-or-None, never the
    value) removes the whole scan from the hot path. Family fix (found by the
    Java port's JMH suite). The cache is keyed on the truncated name — the same
    name the decision is computed from — so it is deterministic by construction,
    and slpy's nested keys are covered because the walk calls this per key at
    every depth. The caller owns the cache (explicit parameter, no module state)
    and must invalidate it when the rule set changes."""
    name = str(key)[:_MAX_KEY_LEN]
    hit = cache.get(name, _MISS)
    if hit is not _MISS:
        return hit  # type: ignore[return-value]  # None here means cached "no rule"
    found = _scan_rules(name, rules)
    if len(cache) < _DECISION_CACHE_MAX:
        cache[name] = found
    return found


def _mask_leaf(value: Any, rule: MaskingRule) -> Any:
    """Mask a scalar. Non-strings are stringified first — an int credit-card
    number keeps its last 4 digits, an int password is fully masked. None
    carries no information and passes through."""
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return _apply_strategy(text, rule)


def _mask_tree(
    value: Any,
    rules: List[MaskingRule],
    active: Optional[MaskingRule],
    depth: int,
    cache: Dict[str, Optional[MaskingRule]],
) -> Any:
    """Recursively mask a structure. `active` is the rule inherited from the
    closest matching ancestor key — everything beneath a sensitive key is
    masked. A deeper key matching its own rule overrides the inherited one."""
    if depth <= 0:
        if active is None:
            return value
        return active.mask_char * _EXHAUSTED_MASK_LEN
    if isinstance(value, dict):
        return {
            k: _mask_tree(v, rules, _find_rule(k, rules, cache) or active, depth - 1, cache)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_mask_tree(v, rules, active, depth - 1, cache) for v in value]
    if active is None:
        return value
    return _mask_leaf(value, active)


_SAFE_KEYS = ("level", "timestamp", "message", "service")


def _safe_payload(data: Any) -> Dict[str, Any]:
    """What survives a masking failure: only structurally-safe core fields.
    The raw metadata never leaks past a failed masking pass."""
    base = {k: data[k] for k in _SAFE_KEYS if k in data} if isinstance(data, dict) else {}
    return {**base, "_masking_failed": True}


# ---------------------------------------------------------------------------
# Engine — thin orchestrator over the pure core
# ---------------------------------------------------------------------------

class MaskingEngine:
    """
    Masks sensitive data in any dict/list structure.
    Rules are evaluated in order; first match wins.

    If slpy-native is installed, processing is delegated to the Rust engine
    automatically. The Python engine is the always-available fallback.

    Failsafe: process() never raises. On failure it reports through
    `on_masking_error`, counts the failure (see slpy.get_stats()), and
    returns a safe payload — the raw metadata never leaks.
    """

    def __init__(
        self,
        enable_default_rules: bool = True,
        extra_rules: Optional[List[MaskingRule]] = None,
        max_depth: int = 10,
        on_masking_error: Optional[Callable[[BaseException], None]] = None,
    ) -> None:
        self._rules: List[MaskingRule] = []
        if enable_default_rules:
            self._rules.extend(_DEFAULT_RULES)
        if extra_rules:
            self._rules.extend(extra_rules)

        self._max_depth = max_depth
        self._on_error = on_masking_error
        self.failures = 0  # read by slpy.get_stats()
        # Per-key-name decision cache: truncated name → rule (or None for "no
        # rule"). Owned by the engine because the decision depends on its rule
        # set; invalidated whenever that set changes (add_rule). Bounded — see
        # _DECISION_CACHE_MAX.
        self._decision_cache: Dict[str, Optional[MaskingRule]] = {}

        self._native = self._build_native(extra_rules or [], max_depth)

    @property
    def is_native(self) -> bool:
        """True if the Rust addon is active."""
        return self._native is not None

    @property
    def decision_cache_size(self) -> int:
        """Entries currently held by the per-key-name decision cache."""
        return len(self._decision_cache)

    def add_rule(self, rule: MaskingRule) -> None:
        """Append a rule at runtime — applied by both engines."""
        self._rules.append(rule)
        # A new rule can only change the decision for names cached as "no rule"
        # (first-match-wins keeps existing matches valid), but clearing everything
        # is the simple, obviously-correct move — add_rule is config-time.
        self._decision_cache.clear()
        if self._native is None:
            return
        if rule.custom_mask is not None:
            self._native = None  # callables can't cross to Rust — stay in parity
            return
        try:
            _push_rule(self._native, rule)
        except Exception:
            self._native = None  # never let the engines diverge

    def process(self, data: Any) -> Any:
        """Mask sensitive fields. Returns the same structure with values masked."""
        if not isinstance(data, (dict, list)):
            return data
        if self._native is not None:
            try:
                return self._native.process(data)
            except Exception:
                pass  # fall through to the Python engine
        try:
            return _mask_tree(data, self._rules, None, self._max_depth, self._decision_cache)
        except Exception as exc:
            self._report(exc)
            return _safe_payload(data)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_native(
        self,
        extra_rules: List[MaskingRule],
        max_depth: int,
    ) -> Optional[Any]:
        """Build the Rust twin, or None. Custom-mask callables cannot cross to
        Rust, and an addon too old for the current API must not silently apply
        weaker semantics — any mismatch means: use the Python engine."""
        if _native is None:
            return None
        if any(r.custom_mask is not None for r in extra_rules):
            return None
        try:
            engine = _native(max_depth=max_depth)
            # EVERY rule is pushed, defaults included: the Rust engine holds no
            # table of its own, so the two engines cannot fall out of step over
            # which rules exist or in which order they match.
            for rule in self._rules:
                _push_rule(engine, rule)
            return engine
        except Exception:
            return None

    def _report(self, exc: BaseException) -> None:
        self.failures += 1
        if self._on_error is None:
            return
        try:
            self._on_error(exc)
        except Exception:
            pass  # the error hook must never take the pipeline down
