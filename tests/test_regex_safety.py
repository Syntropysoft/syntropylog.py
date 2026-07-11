"""Static ReDoS rejection — mirror of SyntropyLog's regexSafety tests.

Deterministic on purpose: we never trigger real catastrophic backtracking (that is
engine-version-dependent and flaky). Every "dangerous" pattern below was MEASURED to hang
CPython/V8 (>3s on <=40 chars, 2026-07-10), except the documented residual.
"""

import pytest

from slpy._regex_safety import assert_safe_key_pattern, find_dangerous_construct
from slpy.masking import MaskingRule, MaskingStrategy


DANGEROUS = [
    "(a+)+$",          # classic nested quantifier — hangs CPython at 40 chars
    "([a-z]+)*$",
    "(a*)*$",
    r"(\w+)*",
    "(.*a){25}",       # counted repetition of an unbounded body
    "(a+){2,}",
    "((b|c)+d?)+",     # nesting one level deeper
]

SAFE = [
    "email",
    "credit_card|creditcard|card_number|cardnumber|payment_number",
    "ssn|social_security|security_number",
    "^user_(id|name)$",
    "pass(word)?",
    "(foo|bar)+",      # star-height 1: no inner quantifier
    "a{3}",
    "[a-z]+@[a-z]+",   # quantified classes, never nested
    r"\d+-\d+",
    "(a+)?",           # group repeated at most once — cannot amplify
]


@pytest.mark.parametrize("pattern", DANGEROUS)
def test_rejects_measured_explosive_patterns(pattern):
    assert find_dangerous_construct(pattern) is not None


@pytest.mark.parametrize("pattern", SAFE)
def test_accepts_patterns_real_rules_use(pattern):
    assert find_dangerous_construct(pattern) is None


def test_escapes_and_char_classes_are_not_false_positives():
    assert find_dangerous_construct("([*+]+)") is None
    assert find_dangerous_construct(r"(\+\d+)") is None


def test_documented_residual_overlapping_alternation_not_detected():
    # (a|a)*$ also hangs the engine, but detecting it needs NFA ambiguity analysis.
    # This test PINS the known limitation so a future improvement flips it consciously.
    assert find_dangerous_construct("(a|a)*$") is None


def test_assert_raises_clear_valueerror():
    with pytest.raises(ValueError, match="Unsafe masking key pattern"):
        assert_safe_key_pattern("(a+)+$")


def test_masking_rule_rejects_dangerous_pattern_at_construction():
    with pytest.raises(ValueError, match="ReDoS"):
        MaskingRule("(a+)+$", MaskingStrategy.PASSWORD)


def test_masking_rule_accepts_safe_custom_pattern():
    rule = MaskingRule("internal_secret", MaskingStrategy.PASSWORD)
    assert rule._compiled.search("my_internal_secret_key")


def test_default_engine_still_builds():
    from slpy.masking import MaskingEngine

    MaskingEngine(enable_default_rules=True)  # must not raise
