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
    assert result["password"] == "************"


def test_masks_token(engine):
    result = engine.process({"auth_token": "abc123xyz"})
    assert result["auth_token"] == "*" * 9


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
    assert result["user"]["token"] == "************"
    assert result["user"]["name"] == "Jane"  # not masked


def test_non_string_values_not_masked(engine):
    result = engine.process({"amount": 100, "active": True, "score": 9.5})
    assert result["amount"] == 100
    assert result["active"] is True
    assert result["score"] == 9.5


def test_custom_rule():
    engine = MaskingEngine(enable_default_rules=False, extra_rules=[
        MaskingRule(pattern=r"internal_code", strategy=MaskingStrategy.TOKEN, mask_char="#"),
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
