"""
Testing toolkit for slpy — assert on emitted logs without touching stdout.

    from slpy.testing import SpyTransport

    spy = SpyTransport()
    await slpy.init({'logger': {'transports': [spy]}})

    ...exercise your code...

    assert spy.count == 2
    assert spy.at_level('error') == []
    assert spy.any_message_contains('info', 'charged')
    assert spy.with_field('order_id', 'o-1')
"""

import threading
from typing import Any, Dict, List, Optional


class SpyTransport:
    """Captures every emitted entry in memory, in emit order. Thread-safe.
    The slpy equivalent of SyntropyLog's and sl4n's SpyTransport."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: List[Dict[str, Any]] = []

    def log(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            self._entries.append(dict(entry))   # defensive copy

    # ------------------------------------------------------------------
    # Reads — every accessor returns a snapshot; mutating it affects nothing
    # ------------------------------------------------------------------

    @property
    def entries(self) -> List[Dict[str, Any]]:
        """All captured entries, in emit order."""
        with self._lock:
            return [dict(e) for e in self._entries]

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def first_entry(self) -> Optional[Dict[str, Any]]:
        entries = self.entries
        return entries[0] if entries else None

    @property
    def last_entry(self) -> Optional[Dict[str, Any]]:
        entries = self.entries
        return entries[-1] if entries else None

    def clear(self) -> None:
        """Discard all captured entries."""
        with self._lock:
            self._entries.clear()

    def at_level(self, level: str) -> List[Dict[str, Any]]:
        """Captured entries at the given level."""
        return [e for e in self.entries if e.get("level") == level]

    def with_field(self, key: str, value: Any) -> List[Dict[str, Any]]:
        """Captured entries carrying field `key` equal to `value`."""
        return [e for e in self.entries if e.get(key) == value]

    def any_message_contains(self, level: str, substring: str) -> bool:
        """True if any entry at `level` has a message containing `substring`."""
        return any(substring in str(e.get("message", "")) for e in self.at_level(level))
