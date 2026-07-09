"""
Logger for slpy.

Named loggers with child() and with_meta() for declarative context binding.
Synchronous hot path — no background workers, no queues.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .sanitize import clean_tree


def _iso_timestamp() -> str:
    """ISO-8601 with milliseconds and offset — the family timestamp format
    (identical to SyntropyLog and sl4n): 2026-07-09T14:00:00.123+00:00"""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

if TYPE_CHECKING:
    from .masking import MaskingEngine
    from .context import ContextManager
    from .matrix import LoggingMatrix
    from .retention import RetentionRegistry
    from .stats import SlpyStats
    from .transport import Transport

_LEVEL_ORDER = {"debug": 0, "info": 1, "warn": 2, "error": 3, "audit": 4, "silent": 99}


class Logger:
    """
    A named logger. Create via slpy.get_logger(name).

    Fluent API:
        logger.child(order_id="123").info("Processing")
        logger.with_meta({"ttl": 86400}).audit("Export complete")
    """

    def __init__(
        self,
        name: str,
        level: str,
        transports: List["Transport"],
        masking: Optional["MaskingEngine"],
        context_mgr: Optional["ContextManager"],
        bindings: Optional[Dict[str, Any]] = None,
        matrix: Optional["LoggingMatrix"] = None,
        stats: Optional["SlpyStats"] = None,
        on_log_failure: Optional[Callable[[BaseException, "Transport"], None]] = None,
        retention: Optional["RetentionRegistry"] = None,
    ) -> None:
        self._name = name
        self._level = level
        self._transports = transports
        self._masking = masking
        self._context_mgr = context_mgr
        self._bindings: Dict[str, Any] = bindings or {}
        self._matrix = matrix
        self._stats = stats
        self._on_log_failure = on_log_failure
        self._retention = retention

    # ------------------------------------------------------------------
    # Fluent API
    # ------------------------------------------------------------------

    def child(self, **bindings: Any) -> "Logger":
        """Return a new Logger with additional bound fields."""
        return Logger(
            name=self._name,
            level=self._level,
            transports=self._transports,
            masking=self._masking,
            context_mgr=self._context_mgr,
            bindings={**self._bindings, **bindings},
            matrix=self._matrix,
            stats=self._stats,
            on_log_failure=self._on_log_failure,
            retention=self._retention,
        )

    def with_meta(self, payload: Dict[str, Any]) -> "Logger":
        """
        Attach arbitrary structured metadata to every log emitted by this logger.
        The payload travels sanitized to all transports as logEntry['meta'].

        Use cases:
        - Audit routing:  .with_meta({"ttl": 90, "destination": "audit-log"})
        - Compliance:     .with_meta({"regulation": "GDPR", "data_class": "PII"})
        - Feature flags:  .with_meta({"experiment": "checkout-v2"})
        """
        return self.child(meta=payload)

    def with_retention(self, name_or_policy: Any) -> "Logger":
        """
        Tag every log from this logger with a retention policy, so the
        transport can route and expire it by compliance rules.

            audit = logger.with_retention('SOX_AUDIT_TRAIL')   # registered name
            audit = logger.with_retention({'days': 90, 'class': 'GDPR'})  # inline

        The stamped fields (retention / retention_class / retention_days)
        travel on every entry and are never filtered by the Logging Matrix
        (they are bindings, not context). An unregistered name still stamps
        `retention` — compliance intent is never silently dropped.
        """
        if self._retention is None:
            stamp = {"retention": name_or_policy} if isinstance(name_or_policy, str) else {}
        else:
            stamp = self._retention.stamp(name_or_policy)
        return self.child(**stamp)

    # ------------------------------------------------------------------
    # Log methods
    # ------------------------------------------------------------------

    def debug(self, message: str, **kwargs: Any) -> None:
        self._emit("debug", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._emit("info", message, **kwargs)

    def warn(self, message: str, **kwargs: Any) -> None:
        self._emit("warn", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._emit("error", message, **kwargs)

    def audit(self, message: str, **kwargs: Any) -> None:
        """Audit level — always emitted regardless of the configured level."""
        self._emit("audit", message, _force=True, **kwargs)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _should_emit(self, level: str) -> bool:
        return _LEVEL_ORDER.get(level, 0) >= _LEVEL_ORDER.get(self._level, 1)

    def _emit(self, level: str, message: str, _force: bool = False, **kwargs: Any) -> None:
        if not _force and not self._should_emit(level):
            return

        # Build entry: context → bindings → kwargs (most specific wins)
        ctx = self._context_mgr.get() if self._context_mgr else {}
        # Logging Matrix filters ONLY the auto-propagating context —
        # core fields, bindings and per-call kwargs are never filtered.
        if self._matrix is not None:
            ctx = self._matrix.filter_context(level, ctx)
        entry: Dict[str, Any] = {
            "level": level,
            "message": message,
            "timestamp": _iso_timestamp(),
            "service": self._name,
            **ctx,
            **self._bindings,
            **kwargs,
        }

        # Apply masking, then the injection boundary (strip ANSI/control chars)
        if self._masking:
            entry = self._masking.process(entry)
        entry = clean_tree(entry)

        if self._stats is not None:
            self._stats.incr_logs_processed()

        for transport in self._transports:
            try:
                transport.log(entry)
            except Exception as exc:
                self._report_transport_failure(exc, transport)

    def _report_transport_failure(self, exc: BaseException, transport: "Transport") -> None:
        """Silent Observer: a broken transport never takes the app down —
        but the failure is counted and surfaced through the hook."""
        if self._stats is not None:
            self._stats.incr_transport_failures()
        if self._on_log_failure is None:
            return
        try:
            self._on_log_failure(exc, transport)
        except Exception:
            pass  # the failure hook must never take the pipeline down
