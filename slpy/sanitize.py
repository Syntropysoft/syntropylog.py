"""
Log-injection safety boundary for slpy.

Strips ANSI escape sequences and control characters from string values
before they reach a transport — a malicious `user_agent` can't fake a log
line, clear the operator's terminal, or smuggle escape codes into a viewer.

Pure functions only. The common (clean) path returns the same object it
received — nothing is allocated when there is nothing to remove.
"""

from typing import Any

_ESC = "\x1b"


def _is_control(ch: str) -> bool:
    return ch < " " or ch == "\x7f"


def _skip_ansi(value: str, esc_index: int) -> int:
    """Index of the last char of the escape sequence starting at esc_index."""
    i = esc_index + 1
    if i >= len(value) or value[i] != "[":
        return esc_index                     # lone ESC (or non-CSI) → drop just the ESC
    i += 1
    while i < len(value) and " " <= value[i] <= "?":
        i += 1                               # parameter/intermediate bytes
    if i < len(value) and "@" <= value[i] <= "~":
        return i                             # final byte — consume it
    return i - 1


def clean(value: str) -> str:
    """Strip control chars and ANSI sequences. Same reference when clean."""
    if not any(_is_control(ch) for ch in value):
        return value

    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == _ESC:
            i = _skip_ansi(value, i) + 1     # drop the whole escape sequence
            continue
        if not _is_control(ch):
            out.append(ch)
        i += 1
    return "".join(out)


def clean_tree(value: Any, depth: int = 10) -> Any:
    """Recursively sanitize every string in a structure. Same reference on
    the all-clean path. Depth-bounded like the masking walk."""
    if isinstance(value, str):
        return clean(value)
    if depth <= 0:
        return value
    if isinstance(value, dict):
        cleaned = {k: clean_tree(v, depth - 1) for k, v in value.items()}
        return value if all(cleaned[k] is value[k] for k in value) else cleaned
    if isinstance(value, list):
        items = [clean_tree(v, depth - 1) for v in value]
        return value if all(a is b for a, b in zip(items, value)) else items
    return value
