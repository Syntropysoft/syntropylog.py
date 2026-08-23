"""
Transport layer for slpy.

Transports are synchronous — the hot path never spawns background tasks.
Extend Transport and implement log() to route entries to any destination.

For async destinations (databases, HTTP APIs) use AdapterTransport +
UniversalAdapter — provide an executor function and slpy handles the rest.
"""

import asyncio
import datetime
import inspect
import json
import sys
from typing import Any, Callable, Dict, FrozenSet, Optional

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


def _format_clock(timestamp: Any) -> str:
    """HH:MM:SS.mmm from an ISO-8601 string (the family format) or a
    legacy epoch-milliseconds number. Anything else → empty."""
    if isinstance(timestamp, str):
        try:
            dt = datetime.datetime.fromisoformat(timestamp)
        except ValueError:
            return ""
        return dt.strftime("%H:%M:%S") + f".{dt.microsecond // 1000:03d}"
    if isinstance(timestamp, (int, float)):
        dt = datetime.datetime.fromtimestamp(timestamp / 1000)
        return dt.strftime("%H:%M:%S") + f".{dt.microsecond // 1000:03d}"
    return ""


class UnknownExemptTransportError(ValueError):
    """
    `masking.exempt_transports` names a transport that is not configured.

    Fail-loud on purpose, at init(). Exempting a transport REMOVES masking from
    it, so a typo would leave the audit sink masked — silently, and exactly where
    the truth was required. That is not something to warn about and continue.
    """

    def __init__(self, unknown, known) -> None:
        self.unknown = tuple(sorted(unknown))
        self.known = tuple(sorted(known))
        super().__init__(
            "masking.exempt_transports names unknown transport(s): [{}]. "
            "Configured transports: [{}]. A transport is named by its `name` "
            "attribute, or by its class name when it has none.".format(
                ", ".join(self.unknown), ", ".join(self.known)
            )
        )


def transport_name(transport: Any) -> str:
    """How a transport is addressed in config: its `name`, or its class name.

    Duck-typed on purpose — anything with a `log()` is a transport here, so this
    reads an attribute instead of requiring a base class.
    """
    return getattr(transport, "name", None) or type(transport).__name__


def resolve_exempt_transports(names, pool) -> FrozenSet[str]:
    """Validate the declared exemptions against the configured transports. Pure.

    Returns a frozen set — empty when nothing is declared, which is the signal
    the logger uses to skip building an unmasked entry at all.
    """
    if not names:
        return frozenset()
    known = {transport_name(t) for t in pool}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise UnknownExemptTransportError(unknown, known)
    return frozenset(names)


class Transport:
    """Base transport. Override log() in subclasses.

    Set `self.name` if the app config needs to address this instance — several
    adapters of the same class, or a sink listed in `masking.exempt_transports`.
    Without one, the class name is the name.
    """

    #: Overridden per instance when a transport needs to be addressable by name.
    name = ""

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

        ts = _format_clock(timestamp)

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


class UniversalAdapter:
    """
    Wraps an executor function — sync or async — that receives the log entry
    and routes it anywhere: database, HTTP API, queue, multiple destinations.

    The executor is the only thing you write. slpy handles context, masking,
    formatting, and error isolation.

    Usage:
        adapter = UniversalAdapter(
            executor=async def my_executor(data):
                await asyncio.gather(
                    prisma.system_log.create(data=data),
                    es_client.index(index='logs', body=data),
                )
        )
    """

    def __init__(self, executor: Callable[[Dict[str, Any]], Any]) -> None:
        self._executor = executor
        self._is_async = inspect.iscoroutinefunction(executor)

    def execute(self, data: Dict[str, Any]) -> None:
        if self._is_async:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._executor(data))
            except RuntimeError:
                asyncio.run(self._executor(data))
        else:
            self._executor(data)


class AdapterTransport(Transport):
    """
    Transport that delegates to a UniversalAdapter.

    Optionally applies a formatter to transform the entry before passing it
    to the executor — useful for mapping slpy fields to your DB schema.

    Usage:
        db_transport = AdapterTransport(
            name='db',
            adapter=UniversalAdapter(executor=my_executor),
            formatter=lambda e: {**e, 'ts': datetime.fromisoformat(e['timestamp'])},
        )

        await slpy.init({
            'logger': {
                'transports': [db_transport, ConsoleTransport()],
            },
        })
    """

    def __init__(
        self,
        name: str,
        adapter: UniversalAdapter,
        formatter: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self.name = name
        self._adapter = adapter
        self._formatter = formatter

    def log(self, entry: Dict[str, Any]) -> None:
        try:
            data = self._formatter(entry) if self._formatter else entry
            self._adapter.execute(data)
        except Exception:
            pass  # Silent observer — never interrupt the application
