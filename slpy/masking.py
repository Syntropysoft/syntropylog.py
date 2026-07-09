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

# ---------------------------------------------------------------------------
# Native addon — loaded once, used transparently
# ---------------------------------------------------------------------------
_native: Any = None
if os.environ.get("SLPY_NATIVE_DISABLE", "").strip() not in ("1", "true", "yes"):
    try:
        from slpy_native import NativeMaskingEngine as _NativeMaskingEngine
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


@dataclass
class MaskingRule:
    pattern: str
    strategy: MaskingStrategy
    custom_mask: Optional[Callable[[str], str]] = None
    preserve_length: bool = True
    mask_char: str = "*"

    def __post_init__(self) -> None:
        self._compiled = re.compile(self.pattern, re.IGNORECASE)


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

# Replacement for a container that still hides under a sensitive key when the
# depth budget runs out — fixed width so nothing about the value leaks.
_EXHAUSTED_MASK_LEN = 6

_DIGITS_RE = re.compile(r"\D")


# ---------------------------------------------------------------------------
# Strategy maskers — pure functions, dispatched by table
# ---------------------------------------------------------------------------

def _mask_all(value: str, mask_char: str) -> str:
    return mask_char * len(value)


def _mask_keep_last4(value: str, mask_char: str) -> str:
    digits = _DIGITS_RE.sub("", value)
    if len(digits) < 4:
        return _mask_all(value, mask_char)
    return mask_char * (len(digits) - 4) + digits[-4:]


def _mask_email_value(value: str, mask_char: str) -> str:
    if "@" not in value:
        return _mask_all(value, mask_char)
    username, domain = value.split("@", 1)
    if len(username) <= 2:
        return f"{mask_char * len(username)}@{domain}"
    return f"{username[0]}{mask_char * (len(username) - 2)}{username[-1]}@{domain}"


_MASKERS: Dict[MaskingStrategy, Callable[[str, str], str]] = {
    MaskingStrategy.CREDIT_CARD: _mask_keep_last4,
    MaskingStrategy.SSN:         _mask_keep_last4,
    MaskingStrategy.PHONE:       _mask_keep_last4,
    MaskingStrategy.EMAIL:       _mask_email_value,
    MaskingStrategy.PASSWORD:    _mask_all,
    MaskingStrategy.TOKEN:       _mask_all,
}


def _apply_strategy(value: str, rule: MaskingRule) -> str:
    if rule.strategy is MaskingStrategy.CUSTOM and rule.custom_mask is not None:
        return rule.custom_mask(value)
    masker = _MASKERS.get(rule.strategy, _mask_all)
    return masker(value, rule.mask_char)


# ---------------------------------------------------------------------------
# Tree walk — pure functions
# ---------------------------------------------------------------------------

def _find_rule(key: Any, rules: List[MaskingRule]) -> Optional[MaskingRule]:
    """First rule whose pattern matches the field name, or None."""
    name = str(key)[:_MAX_KEY_LEN]
    for rule in rules:
        if rule._compiled.search(name):
            return rule
    return None


def _mask_leaf(value: Any, rule: MaskingRule) -> Any:
    """Mask a scalar. Non-strings are stringified first — an int credit-card
    number keeps its last 4 digits, an int password is fully masked. None
    carries no information and passes through."""
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return _apply_strategy(text, rule)


def _mask_tree(value: Any, rules: List[MaskingRule], active: Optional[MaskingRule], depth: int) -> Any:
    """Recursively mask a structure. `active` is the rule inherited from the
    closest matching ancestor key — everything beneath a sensitive key is
    masked. A deeper key matching its own rule overrides the inherited one."""
    if depth <= 0:
        if active is None:
            return value
        return active.mask_char * _EXHAUSTED_MASK_LEN
    if isinstance(value, dict):
        return {
            k: _mask_tree(v, rules, _find_rule(k, rules) or active, depth - 1)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_mask_tree(v, rules, active, depth - 1) for v in value]
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

        self._native = self._build_native(enable_default_rules, extra_rules or [], max_depth)

    @property
    def is_native(self) -> bool:
        """True if the Rust addon is active."""
        return self._native is not None

    def add_rule(self, rule: MaskingRule) -> None:
        """Append a rule at runtime — applied by both engines."""
        self._rules.append(rule)
        if self._native is None:
            return
        if rule.custom_mask is not None:
            self._native = None  # callables can't cross to Rust — stay in parity
            return
        try:
            self._native.add_rule(rule.pattern, rule.strategy.value, rule.mask_char)
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
            return _mask_tree(data, self._rules, None, self._max_depth)
        except Exception as exc:
            self._report(exc)
            return _safe_payload(data)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_native(
        self,
        enable_default_rules: bool,
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
            engine = _native(enable_default_rules=enable_default_rules, max_depth=max_depth)
            for rule in extra_rules:
                engine.add_rule(rule.pattern, rule.strategy.value, rule.mask_char)
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
