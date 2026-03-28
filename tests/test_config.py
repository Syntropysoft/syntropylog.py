"""Tests for ConfigManager."""

import pytest
from slpy.config import ConfigManager


def test_defaults():
    cfg = ConfigManager({})
    assert cfg.logger.level == "info"
    assert cfg.logger.transports == []
    assert cfg.masking.enable_default_rules is True
    assert cfg.context.correlation_id_header == "X-Correlation-ID"


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
