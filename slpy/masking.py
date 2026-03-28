"""
MaskingEngine for slpy.

Masks sensitive fields in log entries using a flatten → mask → unflatten strategy.
Regex patterns are compiled once at rule creation time.

If slpy-native (Rust addon) is installed, MaskingEngine automatically delegates
to NativeMaskingEngine for significantly better performance.
Disable with: SLPY_NATIVE_DISABLE=1
"""

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

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


_DEFAULT_RULES: List[MaskingRule] = [
    MaskingRule(r"(?:credit|card|cc|payment).*?(?:number|num|id)", MaskingStrategy.CREDIT_CARD),
    MaskingRule(r"(?:ssn|social|security).*?(?:number|num)", MaskingStrategy.SSN),
    MaskingRule(r"(?:email|mail|e-mail)", MaskingStrategy.EMAIL),
    MaskingRule(r"(?:phone|tel|mobile|cell).*?(?:number|num)", MaskingStrategy.PHONE),
    MaskingRule(r"(?:password|pass|pwd|secret)", MaskingStrategy.PASSWORD),
    MaskingRule(r"(?:token|key|auth|jwt|bearer)", MaskingStrategy.TOKEN),
]


class MaskingEngine:
    """
    Masks sensitive data in any dict/list structure.
    Rules are evaluated in order; first match wins.

    If slpy-native is installed, processing is delegated to the Rust engine
    automatically. The Python engine is used as fallback.
    """

    def __init__(
        self,
        enable_default_rules: bool = True,
        extra_rules: Optional[List[MaskingRule]] = None,
    ) -> None:
        self._rules: List[MaskingRule] = []
        if enable_default_rules:
            self._rules.extend(_DEFAULT_RULES)
        if extra_rules:
            self._rules.extend(extra_rules)

        # Build native engine if available — same rules, Rust performance.
        # Falls back to Python if any rule uses a custom_mask callable
        # (Python functions cannot be called from Rust).
        self._native = None
        has_custom = any(r.custom_mask is not None for r in (extra_rules or []))
        if _native is not None and not has_custom:
            self._native = _native(enable_default_rules=enable_default_rules)
            if extra_rules:
                for rule in extra_rules:
                    self._native.add_rule(
                        rule.pattern,
                        rule.strategy.value,
                        rule.mask_char,
                    )

    @property
    def is_native(self) -> bool:
        """True if the Rust addon is active."""
        return self._native is not None

    def add_rule(self, rule: MaskingRule) -> None:
        self._rules.append(rule)

    def process(self, data: Any) -> Any:
        """Mask sensitive fields. Returns the same structure with values masked."""
        if not isinstance(data, (dict, list)):
            return data
        if self._native is not None:
            try:
                return self._native.process(data)
            except Exception:
                pass  # Fall through to Python engine
        try:
            flat = self._flatten(data)
            masked = self._apply_rules(flat)
            return self._unflatten(masked)
        except Exception:
            return data  # Silent observer

    # ------------------------------------------------------------------
    # Flatten / unflatten
    # ------------------------------------------------------------------

    def _flatten(self, obj: Any, prefix: str = "") -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{prefix}.{k}" if prefix else k
                result.update(self._flatten(v, key))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                key = f"{prefix}.{i}" if prefix else str(i)
                result.update(self._flatten(v, key))
        else:
            result[prefix] = obj
        return result

    def _unflatten(self, flat: Dict[str, Any]) -> Any:
        result: Dict[str, Any] = {}
        for dotted_key, value in flat.items():
            parts = dotted_key.split(".")
            node = result
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        return result

    # ------------------------------------------------------------------
    # Rule application
    # ------------------------------------------------------------------

    def _apply_rules(self, flat: Dict[str, Any]) -> Dict[str, Any]:
        masked = flat.copy()
        for key, value in flat.items():
            if not isinstance(value, str):
                continue
            leaf = key.split(".")[-1]  # match against the leaf key name
            for rule in self._rules:
                if rule._compiled.search(leaf):
                    masked[key] = self._apply_strategy(value, rule)
                    break
        return masked

    def _apply_strategy(self, value: str, rule: MaskingRule) -> str:
        if rule.strategy == MaskingStrategy.CUSTOM and rule.custom_mask:
            return rule.custom_mask(value)
        if rule.strategy == MaskingStrategy.CREDIT_CARD:
            return self._mask_credit_card(value, rule)
        if rule.strategy == MaskingStrategy.SSN:
            return self._mask_ssn(value, rule)
        if rule.strategy == MaskingStrategy.EMAIL:
            return self._mask_email(value, rule)
        if rule.strategy == MaskingStrategy.PHONE:
            return self._mask_phone(value, rule)
        if rule.strategy in (MaskingStrategy.PASSWORD, MaskingStrategy.TOKEN):
            return rule.mask_char * len(value)
        return rule.mask_char * len(value)

    def _mask_credit_card(self, value: str, rule: MaskingRule) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 4:
            return rule.mask_char * (len(digits) - 4) + digits[-4:]
        return rule.mask_char * len(value)

    def _mask_ssn(self, value: str, rule: MaskingRule) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 4:
            return rule.mask_char * (len(digits) - 4) + digits[-4:]
        return rule.mask_char * len(value)

    def _mask_email(self, value: str, rule: MaskingRule) -> str:
        if "@" in value:
            username, domain = value.split("@", 1)
            if len(username) > 2:
                masked = username[0] + rule.mask_char * (len(username) - 2) + username[-1]
            else:
                masked = rule.mask_char * len(username)
            return f"{masked}@{domain}"
        return rule.mask_char * len(value)

    def _mask_phone(self, value: str, rule: MaskingRule) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 4:
            return rule.mask_char * (len(digits) - 4) + digits[-4:]
        return rule.mask_char * len(value)
