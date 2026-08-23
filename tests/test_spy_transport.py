"""SpyTransport — the testing toolkit."""

import pytest

from slpy import slpy
from slpy.testing import SpyTransport


@pytest.fixture
async def fresh_slpy():
    if slpy.is_initialized:
        await slpy.shutdown()
    yield slpy
    if slpy.is_initialized:
        await slpy.shutdown()


async def test_spy_captures_in_order_with_helpers(fresh_slpy):
    spy = SpyTransport()
    await fresh_slpy.init({"logger": {"level": "info", "transports": [spy]}})
    logger = fresh_slpy.get_logger("svc")

    logger.info("Card charged", order_id="o-1")
    logger.warn("Retrying")
    logger.error("Gave up", order_id="o-1")

    assert spy.count == 3
    assert spy.first_entry["message"] == "Card charged"
    assert spy.last_entry["level"] == "error"
    assert len(spy.at_level("warn")) == 1
    assert len(spy.with_field("order_id", "o-1")) == 2
    assert spy.any_message_contains("info", "charged")
    assert not spy.any_message_contains("error", "charged")

    spy.clear()
    assert spy.count == 0
    assert spy.first_entry is None


async def test_spy_snapshots_are_defensive_copies(fresh_slpy):
    spy = SpyTransport()
    await fresh_slpy.init({"logger": {"level": "info", "transports": [spy]}})
    fresh_slpy.get_logger("svc").info("original")

    spy.entries[0]["message"] = "tampered"
    assert spy.first_entry["message"] == "original"


async def test_spy_sees_masked_output(fresh_slpy):
    spy = SpyTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "masking": {"enable_default_rules": True},
    })
    fresh_slpy.get_logger("svc").info("login", password="hunter2")
    assert spy.first_entry["password"] == "[REDACTED]"
