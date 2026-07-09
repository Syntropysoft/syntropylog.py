"""
DurableFileTransport for slpy — delivery guarantees across outages AND
process restarts. The Python port of sl4n's DurableFileTransport.

It is a durability BUFFER in front of an inner transport — not a log
archive. In the happy path entries go straight to the inner transport and
nothing touches disk. When the inner transport raises, entries are spooled
to a JSONL file and retried on subsequent logs (and on restart); once the
backlog drains, the file is DELETED. The spool only ever holds the
undelivered backlog, so it self-empties on recovery — no rotation, no
archive, no cleanup to maintain.

    durable = DurableFileTransport(
        inner=AdapterTransport(name='audit', adapter=UniversalAdapter(executor=save)),
        spool_path='/var/log/app/audit-spool.jsonl',
    )

Delivery is at-least-once: a crash mid-delivery re-sends the current spool
on the next start — make the inner executor idempotent. Use a LOCAL disk
path: the spool is the safety net, not the destination.
"""

import json
import os
import threading
from typing import Any, Dict, List, Optional

from .transport import Transport


def _serialize(entry: Dict[str, Any]) -> str:
    """One JSONL line; non-JSON values are stringified rather than lost."""
    return json.dumps(entry, separators=(",", ":"), ensure_ascii=False, default=str)


def _deserialize(line: str) -> Dict[str, Any]:
    return json.loads(line)


class DurableFileTransport(Transport):
    """Wraps any Transport with a self-emptying disk spool. Thread-safe."""

    def __init__(self, inner: Transport, spool_path: str) -> None:
        self._inner = inner
        self._spool_path = spool_path
        self._lock = threading.Lock()
        self._has_backlog = False
        with self._lock:
            self._recover()

    def log(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            if not self._has_backlog:
                if self._try_forward(entry):
                    return                      # happy path — disk untouched
                self._has_backlog = True        # sink just went down → begin buffering
                self._append(_serialize(entry))
                return
            self._append(_serialize(entry))     # buffer the new entry (preserves order)
            self._drain()                       # probe recovery; deletes the file when drained

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _recover(self) -> None:
        """On startup, flush any spool left over from a crash during a prior outage."""
        if not os.path.exists(self._spool_path):
            return
        self._has_backlog = True
        self._drain()

    def _try_forward(self, entry: Dict[str, Any]) -> bool:
        try:
            self._inner.log(entry)
            return True
        except Exception:
            return False   # buffering IS the failure handling — swallow and spool

    def _drain(self) -> None:
        """Deliver spooled entries in order, stopping at the first failure.
        Deletes the file when the backlog fully drains; rewrites it with the
        remainder on partial progress; returns fast (no progress, file kept
        intact) while the inner transport is still down."""
        if not os.path.exists(self._spool_path):
            self._has_backlog = False
            return

        delivered = 0
        remainder: Optional[List[str]] = None
        with open(self._spool_path, "r", encoding="utf-8") as spool:
            for raw in spool:
                line = raw.rstrip("\n")
                if not line:
                    continue
                if remainder is not None:
                    remainder.append(line)
                    continue
                if self._try_forward(_deserialize(line)):
                    delivered += 1
                    continue
                if delivered == 0:
                    return                       # still down, no progress → file intact
                remainder = [line]               # partial progress → collect the rest

        if remainder is None:
            os.remove(self._spool_path)          # fully drained → spool gone until next outage
            self._has_backlog = False
            return
        with open(self._spool_path, "w", encoding="utf-8") as spool:
            spool.write("\n".join(remainder) + "\n")

    def _append(self, line: str) -> None:
        directory = os.path.dirname(self._spool_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self._spool_path, "a", encoding="utf-8") as spool:
            spool.write(line + "\n")
