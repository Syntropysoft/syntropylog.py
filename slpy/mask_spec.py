"""
The single declarative masking primitive.

A masking strategy is DATA, not code: a :class:`MaskSpec` describes how to mask a
string and :func:`apply_mask` interprets it. This module is a transliteration of
the family's canonical pair — ``src/masking/maskSpec.ts`` in SyntropyLog (Node)
and ``apply_mask`` in its Rust addon — so adding a strategy is a new spec, never
a new function in four languages.

The shared fixture ``tests/mask-parity-cases.json`` (byte-identical to the copies
in SyntropyLog and syntropylog-java) is asserted against BOTH slpy engines.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

# Replacement for fully redacted values. Must equal REDACTED in the Rust engine.
REDACTED = "[REDACTED]"

# Cap for the masked run when preserve_length is False, so the output does not
# publish the original length. Mirrors MASK_DEFAULT_CAP_LENGTH in the siblings.
MASK_DEFAULT_CAP_LENGTH = 8


@dataclass(frozen=True)
class MaskSpec:
    """
    A masking instruction expressed as data. Built-in strategies (email, card, …)
    are presets that expand to one of these — see :func:`strategy_to_spec`.
    """

    #: Replace the whole value with :data:`REDACTED` (credentials). Wins over everything else.
    redact: bool = False
    #: Keep the first N units (characters, or digits when ``scope='digits'``).
    unmask_start: int = 0
    #: Keep the last N units.
    unmask_end: int = 0
    #: ``'digits'`` masks only digit characters, keeping separators; otherwise all characters.
    scope: Optional[str] = None
    #: Keep everything from the first occurrence of this delimiter onward (an email domain).
    keep_after: Optional[str] = None
    #: Mask character.
    mask_char: str = "*"
    #: Preserve the original length; when False the masked run is capped.
    preserve_length: bool = True


def _is_ascii_digit(char: str) -> bool:
    """ASCII digits only.

    NOT ``str.isdigit()``: that is also true for ``'²'``, ``'٣'`` and every other
    Unicode digit, while the Rust twin uses ``is_ascii_digit()`` and the TypeScript
    one compares against ``'0'``/``'9'``. Using the Python builtin here would make
    the engines disagree on any non-ASCII digit — and every case in the shared
    fixture is ASCII, so the fixture would not catch it.
    """
    return "0" <= char <= "9"


def _mask_chars(
    value: str, start: int, end: int, mask_char: str, preserve_length: bool
) -> str:
    """Mask every character of `value` except the first `start` and the last `end`."""
    length = len(value)
    keep_start = min(start, length)
    keep_end = min(end, length - keep_start)
    masked_count = length - keep_start - keep_end
    body_len = masked_count if preserve_length else min(masked_count, MASK_DEFAULT_CAP_LENGTH)
    prefix = value[:keep_start]
    suffix = value[length - keep_end:] if keep_end else ""
    return prefix + mask_char * body_len + suffix


def _mask_digits(value: str, start: int, end: int, mask_char: str) -> str:
    """
    Mask only the digits of `value` except the first `start` and last `end` digits,
    keeping every non-digit character (separators, '+', spaces) in place. Always
    length-preserving: the format is what makes a masked identifier debuggable.
    """
    digit_positions = [i for i, char in enumerate(value) if _is_ascii_digit(char)]
    total = len(digit_positions)
    keep_start = min(start, total)
    keep_end = min(end, total - keep_start)
    masked = set(digit_positions[keep_start:total - keep_end])
    return "".join(mask_char if i in masked else char for i, char in enumerate(value))


def _split_kept_tail(value: str, delim: Optional[str]) -> Tuple[str, str]:
    """Split `value` into the head to mask and the verbatim tail kept from `delim` on."""
    if not delim:
        return value, ""
    index = value.find(delim)
    if index < 0:
        return value, ""
    return value[:index], value[index:]


def apply_mask(value: str, spec: MaskSpec) -> str:
    """
    Apply a declarative mask spec to a string. Pure; guard clauses.

    MUST stay byte-for-byte equivalent to ``apply_mask`` in the Rust engine and to
    ``applyMask`` in the Node reference — the shared fixture is what proves it.
    """
    if spec.redact:
        return REDACTED

    head, tail = _split_kept_tail(value, spec.keep_after)

    if spec.scope == "digits":
        masked = _mask_digits(head, spec.unmask_start, spec.unmask_end, spec.mask_char)
    else:
        masked = _mask_chars(
            head, spec.unmask_start, spec.unmask_end, spec.mask_char, spec.preserve_length
        )

    return masked + tail
