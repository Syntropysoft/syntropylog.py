"""Tests for Logger — child(), with_meta(), level filtering, audit."""

import pytest
from slpy.logger import Logger
from slpy.transport import Transport
from slpy.masking import MaskingEngine
from slpy.context import ContextManager
from typing import Any, Dict, List


class CaptureTransport(Transport):
    """Transport that captures entries for assertion."""

    def __init__(self):
        self.entries: List[Dict[str, Any]] = []

    def log(self, entry: Dict[str, Any]) -> None:
        self.entries.append(entry)

    def last(self) -> Dict[str, Any]:
        return self.entries[-1]

    def clear(self) -> None:
        self.entries.clear()


@pytest.fixture
def transport():
    return CaptureTransport()


@pytest.fixture
def logger(transport):
    return Logger(
        name="test-service",
        level="info",
        transports=[transport],
        masking=MaskingEngine(enable_default_rules=True),
        context_mgr=ContextManager(),
    )


# ------------------------------------------------------------------
# Basic logging
# ------------------------------------------------------------------

def test_info_emits(logger, transport):
    logger.info("Hello")
    assert len(transport.entries) == 1
    entry = transport.last()
    assert entry["level"] == "info"
    assert entry["message"] == "Hello"
    assert entry["service"] == "test-service"


def test_debug_filtered_at_info_level(logger, transport):
    logger.debug("Should not appear")
    assert len(transport.entries) == 0


def test_warn_emits(logger, transport):
    logger.warn("Something odd", code=42)
    entry = transport.last()
    assert entry["level"] == "warn"
    assert entry["code"] == 42


def test_error_emits(logger, transport):
    logger.error("Failure", reason="timeout")
    assert transport.last()["level"] == "error"


# ------------------------------------------------------------------
# audit bypasses level filter
# ------------------------------------------------------------------

def test_audit_emits_regardless_of_level(transport):
    restricted = Logger(
        name="svc", level="error",
        transports=[transport],
        masking=None, context_mgr=None,
    )
    restricted.info("hidden")
    assert len(transport.entries) == 0
    restricted.audit("must appear")
    assert len(transport.entries) == 1
    assert transport.last()["level"] == "audit"


# ------------------------------------------------------------------
# child()
# ------------------------------------------------------------------

def test_child_carries_bindings(logger, transport):
    child = logger.child(order_id="ORD-1", user_id="USR-2")
    child.info("Processing")
    entry = transport.last()
    assert entry["order_id"] == "ORD-1"
    assert entry["user_id"] == "USR-2"


def test_child_does_not_mutate_parent(logger, transport):
    child = logger.child(extra="value")
    logger.info("Parent log")
    assert "extra" not in transport.last()


def test_nested_child_merges_bindings(logger, transport):
    child = logger.child(order_id="ORD-1").child(step="payment")
    child.info("Charging")
    entry = transport.last()
    assert entry["order_id"] == "ORD-1"
    assert entry["step"] == "payment"


def test_child_kwargs_override_parent(logger, transport):
    child = logger.child(env="prod")
    grandchild = child.child(env="staging")  # override
    grandchild.info("Deploy")
    assert transport.last()["env"] == "staging"


# ------------------------------------------------------------------
# with_meta()
# ------------------------------------------------------------------

def test_with_meta_attaches_payload(logger, transport):
    ml = logger.with_meta({"ttl": 90, "regulation": "GDPR"})
    ml.info("Exported")
    entry = transport.last()
    assert entry["meta"]["ttl"] == 90
    assert entry["meta"]["regulation"] == "GDPR"


def test_with_meta_combined_with_child(logger, transport):
    ml = logger.with_meta({"dest": "audit"}).child(user_id="USR-1")
    ml.audit("Action")
    entry = transport.last()
    assert entry["meta"]["dest"] == "audit"
    assert entry["user_id"] == "USR-1"


# ------------------------------------------------------------------
# Masking integration
# ------------------------------------------------------------------

def test_logger_masks_sensitive_kwargs(logger, transport):
    logger.info("Login", email="john@example.com", password="secret123")
    entry = transport.last()
    assert "john@example.com" not in entry["email"]
    assert entry["password"] == "*" * len("secret123")


# ------------------------------------------------------------------
# Context integration
# ------------------------------------------------------------------

async def test_logger_picks_up_context(transport):
    ctx = ContextManager()
    log = Logger(
        name="svc", level="info",
        transports=[transport],
        masking=None,
        context_mgr=ctx,
    )
    async with ctx.scope(request_id="req-abc"):
        log.info("Within scope")
    assert transport.last()["request_id"] == "req-abc"

    log.info("Outside scope")
    assert "request_id" not in transport.entries[-1]
