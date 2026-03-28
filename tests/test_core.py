"""Tests for SyntropyLog core — lifecycle, get_logger, context, set_level."""

import pytest
from slpy.core import SyntropyLog
from slpy.transport import Transport
from typing import Any, Dict, List


class CaptureTransport(Transport):
    def __init__(self):
        self.entries: List[Dict[str, Any]] = []

    def log(self, entry: Dict[str, Any]) -> None:
        self.entries.append(entry)


@pytest.fixture
async def sl():
    instance = SyntropyLog()
    yield instance
    if instance.is_initialized:
        await instance.shutdown()


# ------------------------------------------------------------------
# Lifecycle
# ------------------------------------------------------------------

async def test_init_and_shutdown(sl):
    await sl.init({})
    assert sl.is_initialized is True
    await sl.shutdown()
    assert sl.is_initialized is False


async def test_double_init_raises(sl):
    await sl.init({})
    with pytest.raises(RuntimeError, match="already initialized"):
        await sl.init({})


async def test_get_logger_before_init_raises(sl):
    with pytest.raises(RuntimeError, match="not initialized"):
        sl.get_logger("svc")


async def test_shutdown_is_idempotent(sl):
    await sl.init({})
    await sl.shutdown()
    await sl.shutdown()  # second call should not raise


# ------------------------------------------------------------------
# get_logger — named logger cache
# ------------------------------------------------------------------

async def test_get_logger_returns_same_instance(sl):
    await sl.init({})
    a = sl.get_logger("svc")
    b = sl.get_logger("svc")
    assert a is b


async def test_different_names_return_different_instances(sl):
    await sl.init({})
    a = sl.get_logger("svc-a")
    b = sl.get_logger("svc-b")
    assert a is not b


# ------------------------------------------------------------------
# Default transport
# ------------------------------------------------------------------

async def test_default_transport_is_console(sl):
    await sl.init({})
    assert len(sl._transports) == 1
    from slpy.transport import ConsoleTransport
    assert isinstance(sl._transports[0], ConsoleTransport)


async def test_custom_transport_used(sl):
    t = CaptureTransport()
    await sl.init({"logger": {"transports": [t]}})
    sl.get_logger("svc").info("Test")
    assert len(t.entries) == 1


# ------------------------------------------------------------------
# context()
# ------------------------------------------------------------------

async def test_context_propagates(sl):
    t = CaptureTransport()
    await sl.init({"logger": {"transports": [t]}})
    logger = sl.get_logger("svc")

    async with sl.context(request_id="req-1"):
        logger.info("Inside")

    assert t.entries[-1]["request_id"] == "req-1"
    logger.info("Outside")
    assert "request_id" not in t.entries[-1]


async def test_context_before_init_raises(sl):
    with pytest.raises(RuntimeError, match="not initialized"):
        async with sl.context(x="y"):
            pass


# ------------------------------------------------------------------
# set_level()
# ------------------------------------------------------------------

async def test_set_level_affects_existing_loggers(sl):
    t = CaptureTransport()
    await sl.init({"logger": {"level": "info", "transports": [t]}})
    logger = sl.get_logger("svc")

    logger.debug("hidden")
    assert len(t.entries) == 0

    sl.set_level("debug")
    logger.debug("now visible")
    assert len(t.entries) == 1


# ------------------------------------------------------------------
# get_correlation_id()
# ------------------------------------------------------------------

async def test_get_correlation_id_returns_none_when_not_set(sl):
    await sl.init({"logger": {"level": "info"}})
    assert sl.get_correlation_id() is None


async def test_get_correlation_id_returns_value_from_context(sl):
    await sl.init({"logger": {"level": "info"}})
    async with sl.context(correlation_id="req-abc-123"):
        assert sl.get_correlation_id() == "req-abc-123"


async def test_get_correlation_id_clears_after_scope(sl):
    await sl.init({"logger": {"level": "info"}})
    async with sl.context(correlation_id="req-abc-123"):
        pass
    assert sl.get_correlation_id() is None


# ------------------------------------------------------------------
# get_correlation_id_header_name()
# ------------------------------------------------------------------

async def test_get_propagation_header_name_default(sl):
    await sl.init({"logger": {"level": "info"}})
    assert sl.get_propagation_header_name("correlation_id") == "X-Correlation-ID"
    assert sl.get_propagation_header_name("trace_id") == "X-Trace-ID"
    assert sl.get_propagation_header_name("session_id") == "X-Session-ID"
    assert sl.get_propagation_header_name("transaction_id") == "X-Transaction-ID"


async def test_get_propagation_headers_empty_when_no_context(sl):
    await sl.init({"logger": {"level": "info"}})
    assert sl.get_propagation_headers() == {}


async def test_get_propagation_headers_returns_active_fields(sl):
    await sl.init({"logger": {"level": "info"}})
    async with sl.context(correlation_id="abc-123", trace_id="xyz-789"):
        headers = sl.get_propagation_headers()
        assert headers["X-Correlation-ID"] == "abc-123"
        assert headers["X-Trace-ID"] == "xyz-789"
        assert "X-Session-ID" not in headers  # not in context


async def test_get_propagation_headers_custom_header_names(sl):
    await sl.init({
        "logger": {"level": "info"},
        "context": {
            "propagation": {
                "correlation_id": "X-Request-ID",
                "trace_id":       "X-B3-TraceId",
            }
        }
    })
    async with sl.context(correlation_id="abc-123", trace_id="xyz-789"):
        headers = sl.get_propagation_headers()
        assert headers["X-Request-ID"] == "abc-123"
        assert headers["X-B3-TraceId"] == "xyz-789"
