"""Tests for ConfigManager."""

import pytest
from slpy.config import ConfigManager


def test_defaults():
    cfg = ConfigManager({})
    assert cfg.logger.level == "info"
    assert cfg.logger.transports == []
    assert cfg.masking.enable_default_rules is True
    assert cfg.context.propagation == {}   # no built-in defaults — developer declares explicitly
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


def test_custom_propagation():
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
    assert "session_id" not in cfg.context.propagation


def test_custom_headers_config():
    cfg = ConfigManager({
        "context": {
            "custom_headers": ["X-Tenant-ID", "X-Feature-Flag"]
        }
    })
    assert "X-Tenant-ID" in cfg.context.custom_headers
    assert "X-Feature-Flag" in cfg.context.custom_headers
