"""
Example 09 — Observability layer: outbound event tracing.

Every time get_propagation_headers() is called, slpy emits an OutboundEvent
automatically. No code changes in the application — the trazability record is
produced by the framework, not by the developer.

These events are NOT logs. They track what context left the service, to which
target, with which headers, and when. Connect them to Jaeger, Zipkin, Datadog
APM, a custom store, or all at once via ObservabilityTransport.
"""

import asyncio
from slpy import slpy, ObservabilityTransport, OutboundEvent


# ---───────────────────────────────────────────────────────────────────────────
# Custom transport — capture events in memory for this demo
# ---───────────────────────────────────────────────────────────────────────────

class InMemoryObservabilityTransport(ObservabilityTransport):
    def __init__(self, name: str):
        self.name = name
        self.events = []

    def emit(self, event: OutboundEvent) -> None:
        self.events.append(event)
        print(
            f"[{self.name}] outbound ->target={event.target!r}"
            f"  corr={event.correlation_id!r}"
            f"  trace={event.trace_id!r}"
            f"  headers={event.headers}"
        )


# ---───────────────────────────────────────────────────────────────────────────
# Example 1: Default HTTP propagation
# ---───────────────────────────────────────────────────────────────────────────

async def example_http():
    print("\n--- HTTP propagation ---")
    obs = InMemoryObservabilityTransport("store-A")

    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs]},
    })

    async with slpy.context(correlation_id="req-001", trace_id="trace-xyz"):
        headers = slpy.get_propagation_headers()
        print(f"Headers sent: {headers}")

    await slpy.shutdown()
    print(f"Events recorded: {len(obs.events)}")


# ---───────────────────────────────────────────────────────────────────────────
# Example 2: Multi-target propagation — different key names per destination
# ---───────────────────────────────────────────────────────────────────────────

async def example_multi_target():
    print("\n---Multi-target propagation ---")
    obs = InMemoryObservabilityTransport("store-B")

    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs]},
        "context": {
            "targets": {
                "kafka": {"correlation_id": "correlationId", "trace_id": "traceId"},
                "s3":    {"correlation_id": "Correlation_ID"},
                "azure": {"correlation_id": "CorrelationID",  "trace_id": "TraceID"},
            }
        },
    })

    async with slpy.context(correlation_id="req-002", trace_id="trace-abc"):
        kafka_headers = slpy.get_propagation_headers("kafka")
        s3_metadata   = slpy.get_propagation_headers("s3")
        azure_props   = slpy.get_propagation_headers("azure")
        http_headers  = slpy.get_propagation_headers()          # default

        print(f"Kafka  ->{kafka_headers}")
        print(f"S3     ->{s3_metadata}")
        print(f"Azure  ->{azure_props}")
        print(f"HTTP   ->{http_headers}")

    await slpy.shutdown()
    print(f"Events recorded: {len(obs.events)} (one per call)")


# ---───────────────────────────────────────────────────────────────────────────
# Example 3: Multiple transports — fanout to Jaeger + Datadog + custom store
# ---───────────────────────────────────────────────────────────────────────────

async def example_fanout():
    print("\n---Fanout to multiple observability transports ---")

    jaeger  = InMemoryObservabilityTransport("jaeger")
    datadog = InMemoryObservabilityTransport("datadog")
    custom  = InMemoryObservabilityTransport("custom-store")

    await slpy.init({
        "logger": {"level": "info"},
        "observability": {
            "transports": [jaeger, datadog, custom],
        },
    })

    async with slpy.context(correlation_id="req-003", trace_id="trace-fan"):
        slpy.get_propagation_headers()          # ->fans out to all 3 transports

    await slpy.shutdown()
    print(f"jaeger={len(jaeger.events)}  datadog={len(datadog.events)}  custom={len(custom.events)}")


# ---───────────────────────────────────────────────────────────────────────────
# Example 4: to_dict() — serialize for any backend
# ---───────────────────────────────────────────────────────────────────────────

async def example_to_dict():
    print("\n---OutboundEvent.to_dict() ---")

    class DictCapture(ObservabilityTransport):
        def __init__(self): self.dicts = []
        def emit(self, event): self.dicts.append(event.to_dict())

    cap = DictCapture()
    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [cap]},
    })

    async with slpy.context(correlation_id="req-004", trace_id="trace-dict"):
        slpy.get_propagation_headers()

    await slpy.shutdown()

    import json
    print(json.dumps(cap.dicts[0], indent=2))


# ---───────────────────────────────────────────────────────────────────────────
# Example 5: Disabled — zero overhead, zero events
# ---───────────────────────────────────────────────────────────────────────────

async def example_disabled():
    print("\n---Observability disabled ---")
    obs = InMemoryObservabilityTransport("never-called")

    await slpy.init({
        "logger": {"level": "info"},
        "observability": {"transports": [obs], "enabled": False},
    })

    async with slpy.context(correlation_id="req-005"):
        slpy.get_propagation_headers()

    await slpy.shutdown()
    print(f"Events recorded: {len(obs.events)}  (expected: 0)")


# ---───────────────────────────────────────────────────────────────────────────
# Main
# ---───────────────────────────────────────────────────────────────────────────

async def main():
    await example_http()
    await example_multi_target()
    await example_fanout()
    await example_to_dict()
    await example_disabled()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
