"""Tests for ObservabilityEngine and outbound event recording."""

import pytest
from slpy import slpy
from slpy.observability import ObservabilityTransport, OutboundEvent


class CaptureObservabilityTransport(ObservabilityTransport):
    def __init__(self):
        self.events = []

    def emit(self, event: OutboundEvent) -> None:
        self.events.append(event)


@pytest.fixture(autouse=True)
async def reset():
    yield
    await slpy.shutdown()


# ------------------------------------------------------------------
# Basic emit
# ------------------------------------------------------------------

async def test_outbound_event_emitted_on_get_propagation_headers():
    obs = CaptureObservabilityTransport()
    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs]},
    })
    async with slpy.context(correlation_id="abc-123"):
        slpy.get_propagation_headers()

    assert len(obs.events) == 1
    assert obs.events[0].target == "http"
    assert obs.events[0].correlation_id == "abc-123"


async def test_outbound_event_target_name():
    obs = CaptureObservabilityTransport()
    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs]},
        "context": {
            "outbound": {
                "targets": {"kafka": {"correlation_id": "correlationId"}},
            }
        },
    })
    async with slpy.context(correlation_id="abc-123"):
        slpy.get_propagation_headers("kafka")

    assert obs.events[0].target == "kafka"


async def test_outbound_event_headers_match_target_mapping():
    obs = CaptureObservabilityTransport()
    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs]},
        "context": {
            "outbound": {
                "propagation": {"correlation_id": "X-Correlation-ID"},
                "targets": {"s3": {"correlation_id": "Correlation_ID"}},
            },
        },
    })
    async with slpy.context(correlation_id="abc-123"):
        slpy.get_propagation_headers("s3")

    assert obs.events[0].headers["Correlation_ID"] == "abc-123"


async def test_outbound_event_has_timestamp():
    obs = CaptureObservabilityTransport()
    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs]},
    })
    async with slpy.context(correlation_id="abc-123"):
        slpy.get_propagation_headers()

    assert obs.events[0].timestamp > 0


async def test_outbound_event_carries_trace_id():
    obs = CaptureObservabilityTransport()
    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs]},
    })
    async with slpy.context(correlation_id="abc-123", trace_id="trace-xyz"):
        slpy.get_propagation_headers()

    assert obs.events[0].trace_id == "trace-xyz"


# ------------------------------------------------------------------
# Multiple calls = multiple events
# ------------------------------------------------------------------

async def test_multiple_calls_emit_multiple_events():
    obs = CaptureObservabilityTransport()
    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs]},
        "context": {
            "outbound": {
                "targets": {
                    "kafka": {"correlation_id": "correlationId"},
                    "s3":    {"correlation_id": "Correlation_ID"},
                },
            }
        },
    })
    async with slpy.context(correlation_id="abc-123"):
        slpy.get_propagation_headers("kafka")
        slpy.get_propagation_headers("s3")
        slpy.get_propagation_headers()

    assert len(obs.events) == 3
    assert obs.events[0].target == "kafka"
    assert obs.events[1].target == "s3"
    assert obs.events[2].target == "http"


# ------------------------------------------------------------------
# Disabled
# ------------------------------------------------------------------

async def test_observability_disabled_emits_nothing():
    obs = CaptureObservabilityTransport()
    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs], "enabled": False},
    })
    async with slpy.context(correlation_id="abc-123"):
        slpy.get_propagation_headers()

    assert len(obs.events) == 0


# ------------------------------------------------------------------
# Silent observer
# ------------------------------------------------------------------

async def test_bad_transport_does_not_raise():
    class BrokenTransport(ObservabilityTransport):
        def emit(self, event):
            raise RuntimeError("transport down")

    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [BrokenTransport()]},
    })
    async with slpy.context(correlation_id="abc-123"):
        slpy.get_propagation_headers()  # must not raise


# ------------------------------------------------------------------
# to_dict()
# ------------------------------------------------------------------

async def test_outbound_event_to_dict():
    obs = CaptureObservabilityTransport()
    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs]},
    })
    async with slpy.context(correlation_id="abc-123", trace_id="xyz"):
        slpy.get_propagation_headers()

    d = obs.events[0].to_dict()
    assert d["event"] == "outbound"
    assert d["target"] == "http"
    assert d["correlation_id"] == "abc-123"
    assert d["trace_id"] == "xyz"
    assert "headers" in d
    assert "timestamp" in d
