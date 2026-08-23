"""Tests for MaskingEngine."""

import pytest
from slpy.masking import MaskingEngine, MaskingRule, MaskingStrategy


@pytest.fixture
def engine():
    return MaskingEngine(enable_default_rules=True)


def test_masks_email(engine):
    result = engine.process({"email": "john.doe@example.com"})
    assert "@example.com" in result["email"]
    assert "john.doe" not in result["email"]


def test_masks_password(engine):
    result = engine.process({"password": "super-secret"})
    assert result["password"] == "[REDACTED]"


def test_masks_token(engine):
    result = engine.process({"auth_token": "abc123xyz"})
    assert result["auth_token"] == "[REDACTED]"


def test_masks_credit_card(engine):
    result = engine.process({"credit_card_number": "4111111111111234"})
    assert result["credit_card_number"].endswith("1234")
    assert "4111" not in result["credit_card_number"]


def test_does_not_mask_safe_fields(engine):
    result = engine.process({"user_id": "USR-42", "amount": 299.90, "status": "ok"})
    assert result["user_id"] == "USR-42"
    assert result["amount"] == 299.90
    assert result["status"] == "ok"


def test_masks_nested_object(engine):
    data = {
        "user": {
            "email": "jane@example.com",
            "token": "secret-token",
            "name": "Jane",
        }
    }
    result = engine.process(data)
    assert "@example.com" in result["user"]["email"]
    assert "jane" not in result["user"]["email"]
    assert result["user"]["token"] == "[REDACTED]"
    assert result["user"]["name"] == "Jane"  # not masked


def test_non_string_values_not_masked(engine):
    result = engine.process({"amount": 100, "active": True, "score": 9.5})
    assert result["amount"] == 100
    assert result["active"] is True
    assert result["score"] == 9.5


def test_custom_rule():
    engine = MaskingEngine(enable_default_rules=False, extra_rules=[
        MaskingRule(pattern=r"internal_code", strategy=MaskingStrategy.CUSTOM, mask_char="#"),
    ])
    result = engine.process({"internal_code": "XYZ123", "name": "visible"})
    assert result["internal_code"] == "######"
    assert result["name"] == "visible"


def test_custom_mask_function():
    def redact(value: str) -> str:
        return "[REDACTED]"

    engine = MaskingEngine(enable_default_rules=False, extra_rules=[
        MaskingRule(pattern=r"secret", strategy=MaskingStrategy.CUSTOM, custom_mask=redact),
    ])
    result = engine.process({"secret_key": "my-value"})
    assert result["secret_key"] == "[REDACTED]"


def test_returns_original_on_non_dict(engine):
    assert engine.process("plain string") == "plain string"
    assert engine.process(42) == 42
    assert engine.process(None) is None


def test_no_default_rules():
    engine = MaskingEngine(enable_default_rules=False)
    result = engine.process({"password": "visible", "email": "visible@example.com"})
    assert result["password"] == "visible"
    assert result["email"] == "visible@example.com"


# ---------------------------------------------------------------------------
# Decision cache (perf fix, 2026-07-11 — semantics must be identical).
# The cache lives in the PYTHON engine; force that path (the Rust twin has its
# own hot path and never consults it).
# ---------------------------------------------------------------------------

@pytest.fixture
def py_engine():
    e = MaskingEngine(enable_default_rules=True)
    e._native = None  # force the Python fallback the cache belongs to
    return e


def test_cache_repeat_calls_mask_identically(py_engine):
    # The RULE is cached per key name — never the value.
    assert py_engine.process({"email": "john@example.com"})["email"] == "j***@example.com"
    assert py_engine.process({"email": "anna@example.com"})["email"] == "a***@example.com"
    assert py_engine.process({"name": "John"})["name"] == "John"
    assert py_engine.process({"name": "Anna"})["name"] == "Anna"
    assert py_engine.decision_cache_size == 2  # email + name, one entry per key NAME


def test_cache_covers_nested_keys(py_engine):
    # slpy masks nested keys — the walk consults the cache at every depth.
    result = py_engine.process({"user": {"email": "john@example.com", "name": "John"}})
    assert result["user"]["email"] == "j***@example.com"
    assert result["user"]["name"] == "John"
    assert py_engine.decision_cache_size == 3  # user + email + name


def test_cache_is_bounded(py_engine):
    from slpy.masking import _DECISION_CACHE_MAX

    for i in range(_DECISION_CACHE_MAX + 50):
        py_engine.process({f"field_{i}": "v"})
    assert py_engine.decision_cache_size == _DECISION_CACHE_MAX
    # A brand-new sensitive key AFTER the cap still masks (pays the scan, uncached).
    result = py_engine.process({"brand_new_password_key": "hunter2"})
    assert result["brand_new_password_key"] == "[REDACTED]"
    assert py_engine.decision_cache_size == _DECISION_CACHE_MAX


def test_cache_invalidated_by_add_rule(py_engine):
    # First pass: 'cuit' matches no rule → cached as "no rule", value untouched.
    assert py_engine.process({"cuit": "20-12345678-9"})["cuit"] == "20-12345678-9"
    py_engine.add_rule(
        MaskingRule(pattern=r"cuit", strategy=MaskingStrategy.CUSTOM, mask_char="#")
    )
    py_engine._native = None  # add_rule may rebuild native wiring; stay on Python
    # Same key after add_rule: the stale "no rule" decision must NOT survive.
    assert py_engine.process({"cuit": "20-12345678-9"})["cuit"] == "#" * len("20-12345678-9")


def test_cache_keyed_on_truncated_name(py_engine):
    from slpy.masking import _MAX_KEY_LEN

    # Two over-long keys sharing the first 256 chars are one decision — the same
    # truncated name the scan itself uses, so this is deterministic by construction.
    base = "a" * _MAX_KEY_LEN
    py_engine.process({base + "_one": "v1"})
    py_engine.process({base + "_two": "v2"})
    assert py_engine.decision_cache_size == 1


def test_mask_char_is_ignored_for_credential_strategies():
    """PASSWORD and TOKEN redact whole, and a custom mask_char does not change that.

    Deliberate, and it follows the family: a length-preserving credential mask
    publishes the length of the secret. `#####` says the password has five
    characters; `[REDACTED]` says nothing. mask_char still governs every
    identifier strategy (email, card, ssn, phone) and CUSTOM.
    """
    engine = MaskingEngine(enable_default_rules=False, extra_rules=[
        MaskingRule(pattern=r"api_key", strategy=MaskingStrategy.TOKEN, mask_char="#"),
        MaskingRule(pattern=r"contact", strategy=MaskingStrategy.EMAIL, mask_char="#"),
    ])
    result = engine.process({"api_key": "k-123", "contact": "john@example.com"})
    assert result["api_key"] == "[REDACTED]"
    assert result["contact"] == "j###@example.com"
