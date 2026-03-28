"""
Transport layer for slpy.

Transports are synchronous — the hot path never spawns background tasks.
Extend Transport and implement log() to route entries to any destination.
"""

import json
import sys
from typing import Any, Dict


class Transport:
    """Base transport. Override log() in subclasses."""

    def log(self, entry: Dict[str, Any]) -> None:
        raise NotImplementedError


class ConsoleTransport(Transport):
    """
    Writes structured JSON to stdout.
    Default transport when none is configured.
    """

    def log(self, entry: Dict[str, Any]) -> None:
        try:
            sys.stdout.write(
                json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n"
            )
            sys.stdout.flush()
        except Exception:
            pass  # Silent observer — never interrupt the application
