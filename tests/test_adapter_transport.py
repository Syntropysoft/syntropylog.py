"""Tests for AdapterTransport + UniversalAdapter."""

import asyncio
import pytest
from slpy.transport import AdapterTransport, UniversalAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_entry(**kwargs):
    base = {
        "level": "info",
        "message": "Test message",
        "timestamp": 1711533600000,
        "service": "test-service",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# UniversalAdapter — sync executor
# ---------------------------------------------------------------------------

def test_sync_executor_is_called():
    received = []
    adapter = UniversalAdapter(executor=lambda data: received.append(data))
    entry = make_entry(order_id="ORD-001")
    adapter.execute(entry)
    assert len(received) == 1
    assert received[0]["order_id"] == "ORD-001"


def test_sync_executor_receives_full_entry():
    received = []
    adapter = UniversalAdapter(executor=lambda data: received.append(data))
    adapter.execute(make_entry(amount=299.90))
    assert received[0]["level"] == "info"
    assert received[0]["amount"] == 299.90


# ---------------------------------------------------------------------------
# UniversalAdapter — async executor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_executor_is_called():
    received = []

    async def executor(data):
        received.append(data)

    adapter = UniversalAdapter(executor=executor)
    adapter.execute(make_entry())
    await asyncio.sleep(0.05)  # let the task complete
    assert len(received) == 1


@pytest.mark.asyncio
async def test_async_executor_fanout():
    dest_a, dest_b = [], []

    async def save_a(data): dest_a.append(data)
    async def save_b(data): dest_b.append(data)

    async def executor(data):
        await asyncio.gather(save_a(data), save_b(data))

    adapter = UniversalAdapter(executor=executor)
    adapter.execute(make_entry(request_id="req-1"))
    await asyncio.sleep(0.05)
    assert len(dest_a) == 1
    assert len(dest_b) == 1
    assert dest_a[0]["request_id"] == "req-1"


# ---------------------------------------------------------------------------
# AdapterTransport — basic delegation
# ---------------------------------------------------------------------------

def test_adapter_transport_calls_executor():
    received = []
    transport = AdapterTransport(
        name="test",
        adapter=UniversalAdapter(executor=lambda d: received.append(d)),
    )
    transport.log(make_entry(user_id="USR-1"))
    assert received[0]["user_id"] == "USR-1"


def test_adapter_transport_name():
    transport = AdapterTransport(
        name="my-transport",
        adapter=UniversalAdapter(executor=lambda d: None),
    )
    assert transport._name == "my-transport"


# ---------------------------------------------------------------------------
# AdapterTransport — formatter
# ---------------------------------------------------------------------------

def test_formatter_transforms_entry():
    received = []

    def formatter(entry):
        return {**entry, "extra": "added"}

    transport = AdapterTransport(
        name="test",
        adapter=UniversalAdapter(executor=lambda d: received.append(d)),
        formatter=formatter,
    )
    transport.log(make_entry())
    assert received[0]["extra"] == "added"


def test_formatter_can_rename_fields():
    received = []

    def formatter(entry):
        return {"msg": entry["message"], "lvl": entry["level"]}

    transport = AdapterTransport(
        name="test",
        adapter=UniversalAdapter(executor=lambda d: received.append(d)),
        formatter=formatter,
    )
    transport.log(make_entry(message="Hello"))
    assert received[0]["msg"] == "Hello"
    assert "message" not in received[0]


def test_no_formatter_passes_entry_unchanged():
    received = []
    transport = AdapterTransport(
        name="test",
        adapter=UniversalAdapter(executor=lambda d: received.append(d)),
    )
    entry = make_entry(order_id="ORD-001")
    transport.log(entry)
    assert received[0] is entry


# ---------------------------------------------------------------------------
# Silent observer
# ---------------------------------------------------------------------------

def test_executor_error_does_not_raise():
    def bad_executor(data):
        raise RuntimeError("db is down")

    transport = AdapterTransport(
        name="test",
        adapter=UniversalAdapter(executor=bad_executor),
    )
    transport.log(make_entry())  # must not raise


def test_formatter_error_does_not_raise():
    def bad_formatter(entry):
        raise ValueError("bad schema")

    transport = AdapterTransport(
        name="test",
        adapter=UniversalAdapter(executor=lambda d: None),
        formatter=bad_formatter,
    )
    transport.log(make_entry())  # must not raise
