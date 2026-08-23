"""
Two data-driven fixtures, both asserted against BOTH engines (the Rust half runs
only when slpy-native is installed).

`mask-parity-cases.json` is the FAMILY fixture — byte-identical to the copies in
SyntropyLog and syntropylog-java — and pins the masking primitive itself:
value + spec → output. It is the contract that makes a card masked by slpy read
the same as one masked by the Node, .NET or JVM sibling.

`PARITY_CASES` is slpy's own and pins the TREE WALK the shared fixture does not
cover: nesting, lists, non-string scalars, inherited rules, the depth budget.

Together they are the regression lock against the bug family that hit
SyntropyLog (Node) #2: two masking engines drifting apart until one leaks PII.
"""

import json
import pathlib
import re

import pytest

import slpy.masking as masking_module
from slpy.masking import MaskingEngine, MaskingRule, MaskingStrategy, MASK_KEYS, mask_pattern
from slpy.mask_spec import MaskSpec, apply_mask

# ---------------------------------------------------------------------------
# The fixture — data, not code. Each case: (name, input, expected).
# ---------------------------------------------------------------------------
PARITY_CASES = [
    (
        "string password fully masked",
        {"password": "hunter2"},
        {"password": "[REDACTED]"},
    ),
    (
        "email keeps first/last of user",
        {"email": "john@example.com"},
        {"email": "j***@example.com"},
    ),
    (
        "card keeps last 4 digits",
        {"card_number": "4111-1111-1111-1234"},
        {"card_number": "****-****-****-1234"},
    ),
    (
        "NON-STRING under sensitive key is masked (int password)",
        {"password": 12345},
        {"password": "[REDACTED]"},
    ),
    (
        "int card number keeps last 4",
        {"card_number": 4111111111111234},
        {"card_number": "************1234"},
    ),
    (
        "NESTED dict under sensitive key is masked wholesale",
        {"password": {"hash": "abc123", "salt": "xyz"}},
        {"password": {"hash": "[REDACTED]", "salt": "[REDACTED]"}},
    ),
    (
        "list under sensitive key is masked element-wise",
        {"token": ["tok-1", "tok-2"]},
        {"token": ["[REDACTED]", "[REDACTED]"]},
    ),
    (
        "lists are PRESERVED as lists (no dict corruption)",
        {"items": [1, 2, 3]},
        {"items": [1, 2, 3]},
    ),
    (
        "deeper matching key overrides inherited rule",
        {"order": {"user": {"token": "abc123", "id": "USR-1"}}},
        {"order": {"user": {"token": "[REDACTED]", "id": "USR-1"}}},
    ),
    (
        "None under sensitive key passes through",
        {"password": None},
        {"password": None},
    ),
    (
        "BARE aliases are covered (credit_card / ssn / phone without suffix)",
        {"credit_card": "4111-1111-1111-1234", "ssn": "123-45-6789", "phone": "+1 (555) 123-4567"},
        {"credit_card": "****-****-****-1234", "ssn": "***-**-6789", "phone": "+* (***) ***-4567"},
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
            "email": "r***@x.com",
            "meta": {"secret": "[REDACTED]", "safe": "visible"},
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
    expected = {"ssn": "***-**-6789"}

    python = MaskingEngine(enable_default_rules=False, extra_rules=[rule])
    python._native = None
    assert python.process(data) == expected

    if masking_module._native is None:
        pytest.skip("slpy-native not installed")
    native = MaskingEngine(enable_default_rules=False, extra_rules=[rule])
    assert native.is_native
    assert native.process(data) == expected


# ---------------------------------------------------------------------------
# The FAMILY fixture — the masking primitive itself, one contract for every port
# ---------------------------------------------------------------------------
# Same file, byte for byte, as SyntropyLog/syntropylog-native/tests/ and
# syntropylog-java/.../test/resources/. Do not edit it here: it is edited in the
# family and copied. Its JSON keys are camelCase because that is the shape that
# crosses the boundary in the Node reference.

_SHARED_FIXTURE = pathlib.Path(__file__).parent / "mask-parity-cases.json"


def _to_spec(raw: dict) -> MaskSpec:
    """camelCase (the family's wire shape) → the Python dataclass field names."""
    return MaskSpec(**{re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower(): v for k, v in raw.items()})


SHARED_CASES = [
    pytest.param(c["value"], _to_spec(c["spec"]), c["expected"], id=f"{c['value']}|{c['expected']}")
    for c in json.loads(_SHARED_FIXTURE.read_text())
]


@pytest.mark.parametrize("value,spec,expected", SHARED_CASES)
def test_shared_fixture_pure_primitive(value, spec, expected):
    """apply_mask on its own — no rules, no tree, no engine."""
    assert apply_mask(value, spec) == expected


@pytest.mark.parametrize("value,spec,expected", SHARED_CASES)
def test_shared_fixture_python_engine(value, spec, expected):
    """The same contract reached through a rule and the tree walk."""
    engine = MaskingEngine(
        enable_default_rules=False,
        extra_rules=[MaskingRule("^v$", MaskingStrategy.CUSTOM, spec=spec)],
    )
    engine._native = None
    assert engine.process({"v": value}) == {"v": expected}


@pytest.mark.parametrize("value,spec,expected", SHARED_CASES)
def test_shared_fixture_native_engine(value, spec, expected):
    """The same contract after the spec crosses into Rust as data."""
    if masking_module._native is None:
        pytest.skip("slpy-native not installed")
    engine = MaskingEngine(
        enable_default_rules=False,
        extra_rules=[MaskingRule("^v$", MaskingStrategy.CUSTOM, spec=spec)],
    )
    assert engine.is_native
    assert engine.process({"v": value}) == {"v": expected}


# ---------------------------------------------------------------------------
# The trap the shared fixture cannot catch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "\u0661\u0662\u0663-\u0664\u0665-\u0666\u0667\u0668\u0669",  # Arabic-Indic digits
        "\uff11\uff12\uff13-\uff14\uff15-\uff16\uff17\uff18\uff19",  # fullwidth digits
        "\u00b2\u00b3\u00b9",                                              # superscripts
    ],
    ids=["arabic-indic", "fullwidth", "superscript"],
)
def test_non_ascii_digits_do_not_diverge(value):
    """`str.isdigit()` is true for these and `is_ascii_digit()` is not.

    Every case in the shared fixture is ASCII, so a `mask_digits` written with the
    Python builtin would pass all 17 and still disagree with Rust here — the exact
    silent drift the fixture exists to prevent. Both engines must treat a
    non-ASCII digit as a separator: not a digit, so never masked, never counted.
    """
    spec = MaskSpec(scope="digits", unmask_end=4)
    rule = MaskingRule("^v$", MaskingStrategy.CUSTOM, spec=spec)

    python = MaskingEngine(enable_default_rules=False, extra_rules=[rule])
    python._native = None
    assert python.process({"v": value}) == {"v": value}, "non-ASCII digits are not digits"

    if masking_module._native is None:
        pytest.skip("slpy-native not installed")
    native = MaskingEngine(enable_default_rules=False, extra_rules=[rule])
    assert native.is_native
    assert native.process({"v": value}) == python.process({"v": value})
