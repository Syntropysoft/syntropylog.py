"""
Shared parity fixture: the Python and Rust engines must produce EXACTLY the
same output for the same input. One data-driven case list, asserted against
both engines (the Rust half runs only when slpy-native is installed).

This is the regression lock against the bug family that hit SyntropyLog
(Node) #2: two masking engines drifting apart until one leaks PII.
"""

import pytest

import slpy.masking as masking_module
from slpy.masking import MaskingEngine, MaskingRule, MaskingStrategy, MASK_KEYS, mask_pattern

# ---------------------------------------------------------------------------
# The fixture — data, not code. Each case: (name, input, expected).
# ---------------------------------------------------------------------------
PARITY_CASES = [
    (
        "string password fully masked",
        {"password": "hunter2"},
        {"password": "*******"},
    ),
    (
        "email keeps first/last of user",
        {"email": "john@example.com"},
        {"email": "j**n@example.com"},
    ),
    (
        "card keeps last 4 digits",
        {"card_number": "4111-1111-1111-1234"},
        {"card_number": "************1234"},
    ),
    (
        "NON-STRING under sensitive key is masked (int password)",
        {"password": 12345},
        {"password": "*****"},
    ),
    (
        "int card number keeps last 4",
        {"card_number": 4111111111111234},
        {"card_number": "************1234"},
    ),
    (
        "NESTED dict under sensitive key is masked wholesale",
        {"password": {"hash": "abc123", "salt": "xyz"}},
        {"password": {"hash": "******", "salt": "***"}},
    ),
    (
        "list under sensitive key is masked element-wise",
        {"token": ["tok-1", "tok-2"]},
        {"token": ["*****", "*****"]},
    ),
    (
        "lists are PRESERVED as lists (no dict corruption)",
        {"items": [1, 2, 3]},
        {"items": [1, 2, 3]},
    ),
    (
        "deeper matching key overrides inherited rule",
        {"order": {"user": {"token": "abc123", "id": "USR-1"}}},
        {"order": {"user": {"token": "******", "id": "USR-1"}}},
    ),
    (
        "None under sensitive key passes through",
        {"password": None},
        {"password": None},
    ),
    (
        "non-sensitive fields untouched",
        {"amount": 299.9, "name": "John Doe", "ok": True},
        {"amount": 299.9, "name": "John Doe", "ok": True},
    ),
    (
        "mixed entry — full log-entry shape",
        {
            "level": "info",
            "message": "Card charged",
            "service": "payments",
            "email": "real@x.com",
            "meta": {"secret": "s3cr3t", "safe": "visible"},
        },
        {
            "level": "info",
            "message": "Card charged",
            "service": "payments",
            "email": "r**l@x.com",
            "meta": {"secret": "******", "safe": "visible"},
        },
    ),
]


def _python_engine() -> MaskingEngine:
    engine = MaskingEngine(enable_default_rules=True)
    engine._native = None  # force the pure-Python path
    return engine


def _native_engine():
    if masking_module._native is None:
        return None
    engine = MaskingEngine(enable_default_rules=True)
    return engine if engine.is_native else None


@pytest.mark.parametrize("name,data,expected", PARITY_CASES, ids=[c[0] for c in PARITY_CASES])
def test_python_engine_semantics(name, data, expected):
    assert _python_engine().process(data) == expected


@pytest.mark.parametrize("name,data,expected", PARITY_CASES, ids=[c[0] for c in PARITY_CASES])
def test_native_engine_matches_python(name, data, expected):
    native = _native_engine()
    if native is None:
        pytest.skip("slpy-native not installed")
    assert native.process(data) == expected


def test_custom_rule_applies_in_both_engines():
    rule = MaskingRule(mask_pattern(*MASK_KEYS["ssn"]), MaskingStrategy.SSN)
    data = {"ssn": "123-45-6789"}
    expected = {"ssn": "*****6789"}

    python = MaskingEngine(enable_default_rules=False, extra_rules=[rule])
    python._native = None
    assert python.process(data) == expected

    if masking_module._native is None:
        pytest.skip("slpy-native not installed")
    native = MaskingEngine(enable_default_rules=False, extra_rules=[rule])
    assert native.is_native
    assert native.process(data) == expected
