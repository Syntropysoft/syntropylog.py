"""Static ReDoS rejection for masking key patterns — mirror of SyntropyLog's regexSafety.ts.

CPython's ``re`` module is a backtracking engine with no timeout API, and the key-length
cap alone is insufficient (measured 2026-07-10: ``(a+)+$`` hangs CPython at 40 chars, far
below the 256 cap). The right tool is refusing the explosive pattern BEFORE it ever runs —
deterministically, at rule-construction time.

Detected (the dominant ReDoS classes):
  * star-height > 1 — an unbounded quantifier over a group whose body already contains an
    unbounded quantifier: ``(a+)+``, ``([a-z]+)*``, ``(\\w+)*$``
  * counted repetition of such a group — ``(.*a){25}``, ``(a+){2,}``

Honest residual: overlapping alternation under a quantifier (``(a|a)*$``) also hangs the
engine and is NOT detected here (it needs NFA ambiguity analysis). If slpy-native is
installed, rule matching runs in Rust's linear-time ``regex`` crate, where ReDoS cannot
exist — the declarative path is the full elimination.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

_BOUNDED_RE = re.compile(r"\{(\d+)(?:,(\d*))?\}")


def _read_quantifier(src: str, i: int) -> Optional[Tuple[bool, float, int]]:
    """Return (unbounded, max, end) for a quantifier at ``i``, or None."""
    if i >= len(src):
        return None
    c = src[i]
    if c in "*+":
        return True, float("inf"), _skip_lazy(src, i + 1)
    if c == "?":
        return False, 1.0, _skip_lazy(src, i + 1)
    if c == "{":
        m = _BOUNDED_RE.match(src, i)
        if not m:
            return None  # literal '{'
        lo = int(m.group(1))
        if m.group(2) == "":  # {n,}
            return True, float("inf"), _skip_lazy(src, m.end())
        hi = lo if m.group(2) is None else int(m.group(2))
        return False, float(hi), _skip_lazy(src, m.end())
    return None


def _skip_lazy(src: str, i: int) -> int:
    return i + 1 if i < len(src) and src[i] == "?" else i


def _skip_char_class(src: str, i: int) -> int:
    i += 1  # past '['
    if i < len(src) and src[i] == "^":
        i += 1
    if i < len(src) and src[i] == "]":
        i += 1  # leading ']' is a literal
    while i < len(src) and src[i] != "]":
        if src[i] == "\\":
            i += 1
        i += 1
    return i + 1  # past ']'


def find_dangerous_construct(source: str) -> Optional[str]:
    """Scan a regex source for super-linear constructs.

    Returns a human-readable description of the dangerous construct, or None. Conservative
    by design: it may reject an exotic-but-safe pattern; it must never accept an explosive
    one it can model.
    """
    stack: List[bool] = [False]  # per-frame: body contains an unbounded quantifier
    i = 0
    n = len(source)

    while i < n:
        c = source[i]

        if c == "\\":
            i += 2
            q = _read_quantifier(source, i)
            if q:
                if q[0]:
                    stack[-1] = True
                i = q[2]
            continue

        if c == "[":
            i = _skip_char_class(source, i)
            q = _read_quantifier(source, i)
            if q:
                if q[0]:
                    stack[-1] = True
                i = q[2]
            continue

        if c == "(":
            stack.append(False)
            i += 1
            continue

        if c == ")":
            closed = stack.pop() if len(stack) > 1 else False
            i += 1
            q = _read_quantifier(source, i)
            if q:
                unbounded, q_max, end = q
                # Repeating (unbounded, or bounded more than once) a group that can
                # already consume unbounded input = the classic blow-up.
                if closed and (unbounded or q_max > 1):
                    return (
                        f"quantified group ending at index {i - 1} repeats a body that "
                        f'already contains an unbounded quantifier (star-height > 1, e.g. "(a+)+")'
                    )
                if unbounded or closed:
                    stack[-1] = True
                i = end
            elif closed:
                stack[-1] = True
            continue

        # Ordinary atom ('.', literal, '|', anchors…)
        i += 1
        q = _read_quantifier(source, i)
        if q:
            if q[0]:
                stack[-1] = True
            i = q[2]

    return None


def assert_safe_key_pattern(pattern: str) -> None:
    """Raise ``ValueError`` if ``pattern`` can blow up the backtracking engine.

    Called once per rule at construction (init time) — never on the log hot path.
    """
    danger = find_dangerous_construct(pattern)
    if danger:
        raise ValueError(
            f"[slpy] Unsafe masking key pattern {pattern!r}: {danger}. CPython cannot "
            f"interrupt a running regex, so this pattern could hang the process (ReDoS). "
            f"Rewrite it without nested quantifiers — with slpy-native installed, rule "
            f"matching runs in Rust's linear-time engine, which is immune."
        )
