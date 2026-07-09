"""
Self-observability for slpy — the Python equivalent of SyntropyLog's
getStats() and sl4n's Sl4nStats.

The pipeline already survives every failure silently (Silent Observer);
these counters are how you SEE those survivals. Read them from a health
endpoint via slpy.get_stats().
"""

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class StatsSnapshot:
    """Immutable point-in-time view of the pipeline counters."""

    logs_processed: int
    transport_failures: int
    masking_failures: int
    uptime_seconds: float
    native_active: bool


class SlpyStats:
    """Thread-safe counters. Incremented by the pipeline, read via snapshot()."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._logs_processed = 0
        self._transport_failures = 0
        self._started_at = time.monotonic()

    def incr_logs_processed(self) -> None:
        with self._lock:
            self._logs_processed += 1

    def incr_transport_failures(self) -> None:
        with self._lock:
            self._transport_failures += 1

    def snapshot(self, masking_failures: int = 0, native_active: bool = False) -> StatsSnapshot:
        with self._lock:
            return StatsSnapshot(
                logs_processed=self._logs_processed,
                transport_failures=self._transport_failures,
                masking_failures=masking_failures,
                uptime_seconds=time.monotonic() - self._started_at,
                native_active=native_active,
            )
