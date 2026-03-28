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
