"""Logging Matrix — per-level whitelist of context fields."""

import pytest

from slpy import slpy
from slpy.matrix import LoggingMatrix


class CaptureTransport:
    def __init__(self):
        self.entries = []

    def log(self, entry):
        self.entries.append(entry)


# ---------------------------------------------------------------------------
# Pure engine semantics
# ---------------------------------------------------------------------------

def test_unconfigured_matrix_allows_everything():
    matrix = LoggingMatrix.create(None)
    assert matrix.allowed_fields("info") is None
    assert not matrix.is_configured


def test_empty_dict_is_unconfigured():
    assert LoggingMatrix.create({}).allowed_fields("error") is None


def test_level_whitelist_is_returned():
    matrix = LoggingMatrix.create({"info": ["correlation_id", "user_id"]})
    assert matrix.allowed_fields("info") == frozenset({"correlation_id", "user_id"})


def test_level_names_match_case_insensitively():
    matrix = LoggingMatrix.create({"INFO": ["a"]})
    assert matrix.allowed_fields("info") == frozenset({"a"})


def test_unlisted_level_falls_back_to_default():
    matrix = LoggingMatrix.create({"default": ["correlation_id"], "error": ["*"]})
    assert matrix.allowed_fields("warn") == frozenset({"correlation_id"})


def test_unlisted_level_without_default_drops_all_context():
    matrix = LoggingMatrix.create({"error": ["*"]})
    assert matrix.allowed_fields("info") == frozenset()


def test_wildcard_allows_everything_at_that_level():
    matrix = LoggingMatrix.create({"error": ["*"]})
    assert matrix.allowed_fields("error") is None


def test_filter_context_is_pure_and_returns_subset():
    matrix = LoggingMatrix.create({"info": ["keep"]})
    ctx = {"keep": 1, "drop": 2}
    assert matrix.filter_context("info", ctx) == {"keep": 1}
    assert ctx == {"keep": 1, "drop": 2}  # input untouched


# ---------------------------------------------------------------------------
# End-to-end through the logger
# ---------------------------------------------------------------------------

@pytest.fixture
async def fresh_slpy():
    if slpy.is_initialized:
        await slpy.shutdown()
    yield slpy
    if slpy.is_initialized:
        await slpy.shutdown()


async def test_matrix_filters_context_per_level(fresh_slpy):
    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "logging_matrix": {
            "default": ["correlation_id"],
            "error": ["correlation_id", "tenant_id"],
        },
    })
    logger = fresh_slpy.get_logger("svc")

    async with fresh_slpy.context(correlation_id="req-1", tenant_id="acme"):
        logger.info("narrow")
        logger.error("wide")

    info, error = spy.entries
    assert info["correlation_id"] == "req-1"
    assert "tenant_id" not in info          # not whitelisted at info
    assert error["tenant_id"] == "acme"     # whitelisted at error


async def test_matrix_never_filters_bindings_or_kwargs(fresh_slpy):
    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "logging_matrix": {"default": []},   # drop ALL context
    })
    logger = fresh_slpy.get_logger("svc").child(order_id="o-1")

    async with fresh_slpy.context(request_id="req-9"):
        logger.info("msg", amount=10)

    entry = spy.entries[0]
    assert "request_id" not in entry         # context dropped
    assert entry["order_id"] == "o-1"        # binding survives
    assert entry["amount"] == 10             # per-call kwarg survives
    assert entry["service"] == "svc"         # core field survives


async def test_reconfigure_logging_matrix_applies_to_existing_loggers(fresh_slpy):
    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "logging_matrix": {"default": []},
    })
    logger = fresh_slpy.get_logger("svc")

    async with fresh_slpy.context(user_id="u-1"):
        logger.info("before")
        fresh_slpy.reconfigure_logging_matrix({"default": ["user_id"]})
        logger.info("after")

    before, after = spy.entries
    assert "user_id" not in before
    assert after["user_id"] == "u-1"


async def test_no_matrix_config_changes_nothing(fresh_slpy):
    spy = CaptureTransport()
    await fresh_slpy.init({"logger": {"level": "info", "transports": [spy]}})
    async with fresh_slpy.context(anything="goes"):
        fresh_slpy.get_logger("svc").info("msg")
    assert spy.entries[0]["anything"] == "goes"
