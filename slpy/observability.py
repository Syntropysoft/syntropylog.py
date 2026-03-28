"""
Observability layer for slpy.

Tracks outbound propagation events — what headers left, to which target,
and when. Not logs — trazability of context propagation between services.

These events are emitted automatically when get_propagation_headers() is
called. No code changes needed in the application.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OutboundEvent:
    """
    Represents a single outbound propagation event.

    Emitted automatically by get_propagation_headers() every time context
    is about to leave the service — to HTTP, Kafka, S3, Azure, gRPC, etc.

    Fields are never masked — these are protocol headers, not application data.
    """
    target: str                          # "kafka", "s3", "azure", "http", etc.
    headers: Dict[str, str]              # key/value pairs as they will be sent
    correlation_id: Optional[str]        # from current context — links to logs
    trace_id: Optional[str]              # from current context
    timestamp: int = field(             # epoch milliseconds
        default_factory=lambda: int(time.time() * 1000)
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event":          "outbound",
            "target":         self.target,
            "headers":        self.headers,
            "correlation_id": self.correlation_id,
            "trace_id":       self.trace_id,
            "timestamp":      self.timestamp,
        }


class ObservabilityTransport:
    """
    Base class for observability transports.

    Implement emit(event) to route outbound events to any destination:
    Jaeger, Zipkin, Datadog APM, console, a custom store, etc.
    """

    def emit(self, event: OutboundEvent) -> None:
        raise NotImplementedError


class ConsoleObservabilityTransport(ObservabilityTransport):
    """
    Writes outbound events to stdout as structured JSON.
    Default when no observability transport is configured.
    """

    def emit(self, event: OutboundEvent) -> None:
        import json
        import sys
        try:
            sys.stdout.write(
                json.dumps(event.to_dict(), separators=(",", ":"), ensure_ascii=False)
                + "\n"
            )
            sys.stdout.flush()
        except Exception:
            pass


class ObservabilityEngine:
    """
    Receives outbound events and fans them out to all configured transports.
    Silent observer — errors never propagate to the application.
    """

    def __init__(self, transports: List[ObservabilityTransport]) -> None:
        self._transports = transports

    def record(self, event: OutboundEvent) -> None:
        for transport in self._transports:
            try:
                transport.emit(event)
            except Exception:
                pass  # Silent observer
