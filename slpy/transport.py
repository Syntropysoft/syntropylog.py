"""
Transport layer for slpy.

Transports are synchronous — the hot path never spawns background tasks.
Extend Transport and implement log() to route entries to any destination.
"""

import datetime
import json
import sys
from typing import Any, Dict

# ---------------------------------------------------------------------------
# ANSI codes — no external dependencies
# ---------------------------------------------------------------------------
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"

_LEVEL_STYLE: Dict[str, str] = {
    "debug": "\033[2;37m",   # dim grey
    "info":  "\033[32m",     # green
    "warn":  "\033[33m",     # yellow
    "error": "\033[31m",     # red
    "audit": "\033[36m",     # cyan
}

_LEVEL_LABEL: Dict[str, str] = {
    "debug": "DEBUG",
    "info":  "INFO ",
    "warn":  "WARN ",
    "error": "ERROR",
    "audit": "AUDIT",
}

# Fields rendered in dedicated columns — excluded from key=value tail
_CORE_FIELDS = frozenset({"level", "message", "timestamp", "service"})


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


class PrettyConsoleTransport(Transport):
    """
    Human-readable colored output for development.

    Format:
        HH:MM:SS.mmm LEVEL  service  message          key=value key=value

    Colors per level (ANSI, no external deps):
        debug → dim grey   info → green   warn → yellow
        error → red        audit → cyan

    Auto-detects TTY: if stdout is not a terminal (CI, pipes, production)
    falls back to JSON automatically — same as ConsoleTransport.

    Usage:
        await slpy.init({
            'logger': {
                'level': 'debug',
                'transports': [PrettyConsoleTransport()],
            },
        })
    """

    def __init__(self, colors: bool = None) -> None:
        """
        Args:
            colors: Force colors on (True) or off (False).
                    Default (None) = auto-detect via sys.stdout.isatty().
        """
        if colors is None:
            self._colors = sys.stdout.isatty()
        else:
            self._colors = colors
        self._fallback = ConsoleTransport()

    def log(self, entry: Dict[str, Any]) -> None:
        if not self._colors:
            self._fallback.log(entry)
            return
        try:
            sys.stdout.write(self._format(entry) + "\n")
            sys.stdout.flush()
        except Exception:
            pass

    def _format(self, entry: Dict[str, Any]) -> str:
        level     = str(entry.get("level", "info")).lower()
        message   = str(entry.get("message", ""))
        service   = str(entry.get("service", ""))
        timestamp = entry.get("timestamp")

        # Timestamp — milliseconds epoch → HH:MM:SS.mmm
        if isinstance(timestamp, (int, float)):
            dt = datetime.datetime.fromtimestamp(timestamp / 1000)
            ts = dt.strftime("%H:%M:%S") + f".{dt.microsecond // 1000:03d}"
        else:
            ts = ""

        style = _LEVEL_STYLE.get(level, _LEVEL_STYLE["info"])
        label = _LEVEL_LABEL.get(level, level.upper()[:5].ljust(5))

        # Key=value tail — everything except core fields
        pairs = []
        for k, v in entry.items():
            if k in _CORE_FIELDS:
                continue
            if isinstance(v, dict):
                pairs.append(f"{k}={json.dumps(v, separators=(',', ':'))}")
            else:
                pairs.append(f"{k}={v}")
        tail = ("  " + "  ".join(pairs)) if pairs else ""

        return (
            f"{_DIM}{ts}{_RESET}  "
            f"{style}{_BOLD}{label}{_RESET}  "
            f"{_DIM}{service:<20}{_RESET}"
            f"{message}"
            f"{_DIM}{tail}{_RESET}"
        )
