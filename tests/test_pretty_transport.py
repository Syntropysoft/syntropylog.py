"""Tests for PrettyConsoleTransport."""

import json
import pytest
from slpy.transport import PrettyConsoleTransport, ConsoleTransport


def make_entry(**kwargs):
    base = {
        "level": "info",
        "message": "Test message",
        "timestamp": 1711533600000,  # 2024-03-27 12:00:00.000 UTC
        "service": "test-service",
    }
    base.update(kwargs)
    return base


# ------------------------------------------------------------------
# TTY detection
# ------------------------------------------------------------------

def test_no_colors_when_not_tty():
    t = PrettyConsoleTransport(colors=False)
    assert t._colors is False


def test_colors_forced_on():
    t = PrettyConsoleTransport(colors=True)
    assert t._colors is True


# ------------------------------------------------------------------
# Format output (colors=True)
# ------------------------------------------------------------------

def test_format_contains_level(capsys):
    t = PrettyConsoleTransport(colors=True)
    t.log(make_entry(level="info"))
    out = capsys.readouterr().out
    assert "INFO" in out


def test_format_contains_message(capsys):
    t = PrettyConsoleTransport(colors=True)
    t.log(make_entry(message="Hello world"))
    out = capsys.readouterr().out
    assert "Hello world" in out


def test_format_contains_service(capsys):
    t = PrettyConsoleTransport(colors=True)
    t.log(make_entry(service="payment-service"))
    out = capsys.readouterr().out
    assert "payment-service" in out


def test_format_contains_extra_fields(capsys):
    t = PrettyConsoleTransport(colors=True)
    t.log(make_entry(order_id="ORD-001", amount=299.90))
    out = capsys.readouterr().out
    assert "order_id=ORD-001" in out
    assert "amount=299.9" in out


def test_core_fields_not_in_tail(capsys):
    t = PrettyConsoleTransport(colors=True)
    t.log(make_entry())
    out = capsys.readouterr().out
    # level and service should not appear as key=value pairs
    assert "level=info" not in out
    assert "service=test-service" not in out


def test_all_levels_render(capsys):
    t = PrettyConsoleTransport(colors=True)
    for level in ("debug", "info", "warn", "error", "audit"):
        t.log(make_entry(level=level))
        out = capsys.readouterr().out
        assert level.upper()[:5] in out.upper()


def test_dict_value_serialized_as_json(capsys):
    t = PrettyConsoleTransport(colors=True)
    t.log(make_entry(meta={"ttl": 90, "dest": "audit"}))
    out = capsys.readouterr().out
    assert "meta=" in out
    assert "ttl" in out


# ------------------------------------------------------------------
# Fallback to JSON when colors=False
# ------------------------------------------------------------------

def test_fallback_to_json_when_no_colors(capsys):
    t = PrettyConsoleTransport(colors=False)
    entry = make_entry(order_id="ORD-001")
    t.log(entry)
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    assert parsed["order_id"] == "ORD-001"
    assert parsed["level"] == "info"


def test_fallback_is_valid_json_for_all_levels(capsys):
    t = PrettyConsoleTransport(colors=False)
    for level in ("debug", "info", "warn", "error", "audit"):
        t.log(make_entry(level=level))
        out = capsys.readouterr().out.strip()
        parsed = json.loads(out)
        assert parsed["level"] == level


# ------------------------------------------------------------------
# Silent observer
# ------------------------------------------------------------------

def test_does_not_raise_on_bad_entry(capsys):
    t = PrettyConsoleTransport(colors=True)
    t.log({})  # missing all fields — should not raise
    t.log({"level": None, "message": None})
