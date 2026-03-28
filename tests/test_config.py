"""Tests for ConfigManager."""

import pytest
from slpy.config import ConfigManager


def test_defaults():
    cfg = ConfigManager({})
    assert cfg.logger.level == "info"
    assert cfg.logger.transports == []
    assert cfg.masking.enable_default_rules is True
    assert cfg.context.propagation["correlation_id"] == "X-Correlation-ID"
    assert cfg.context.propagation["trace_id"] == "X-Trace-ID"
    assert cfg.context.propagation["session_id"] == "X-Session-ID"
    assert cfg.context.propagation["transaction_id"] == "X-Transaction-ID"
    assert cfg.context.custom_headers == []


def test_custom_level():
    cfg = ConfigManager({"logger": {"level": "debug"}})
    assert cfg.logger.level == "debug"


def test_invalid_level_raises():
    cfg = ConfigManager({"logger": {"level": "verbose"}})
    with pytest.raises(ValueError, match="Invalid log level"):
        cfg.validate()


def test_masking_config():
    cfg = ConfigManager({
        "masking": {
            "enable_default_rules": False,
            "rules": [{"pattern": "secret", "strategy": "token"}],
        }
    })
    assert cfg.masking.enable_default_rules is False
    assert len(cfg.masking.rules) == 1


def test_env_override(monkeypatch):
    monkeypatch.setenv("SLPY_LOG_LEVEL", "error")
    cfg = ConfigManager({"logger": {"level": "info"}})
    assert cfg.logger.level == "error"


def test_custom_propagation_overrides_default():
    cfg = ConfigManager({
        "context": {
            "propagation": {
                "correlation_id": "X-Request-ID",
                "trace_id":       "X-B3-TraceId",
            }
        }
    })
    assert cfg.context.propagation["correlation_id"] == "X-Request-ID"
    assert cfg.context.propagation["trace_id"] == "X-B3-TraceId"
    # defaults not overridden remain
    assert cfg.context.propagation["session_id"] == "X-Session-ID"
    assert cfg.context.propagation["transaction_id"] == "X-Transaction-ID"


def test_custom_headers_config():
    cfg = ConfigManager({
        "context": {
            "custom_headers": ["X-Tenant-ID", "X-Feature-Flag"]
        }
    })
    assert "X-Tenant-ID" in cfg.context.custom_headers
    assert "X-Feature-Flag" in cfg.context.custom_headers
