"""
Logger for slpy.

Named loggers with child() and with_meta() for declarative context binding.
Synchronous hot path — no background workers, no queues.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, FrozenSet, List, Optional, TYPE_CHECKING

from . import retention_window
from .sanitize import clean_tree
from .transport import transport_name


def _iso_timestamp(at: datetime) -> str:
    """ISO-8601 with milliseconds and offset — the family timestamp format
    (identical to SyntropyLog and sl4n): 2026-07-09T14:00:00.123+00:00"""
    return at.isoformat(timespec="milliseconds")

if TYPE_CHECKING:
    from .masking import MaskingEngine
    from .context import ContextManager
    from .matrix import LoggingMatrix
    from .retention import RetentionPolicy, RetentionRegistry
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
        retention_policy: Optional["RetentionPolicy"] = None,
        exempt_transports: FrozenSet[str] = frozenset(),
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
        # Resolved ONCE, when with_retention() built this logger. The date it
        # implies cannot live in the bindings — see _emit.
        self._retention_policy = retention_policy
        # Names of transports that receive the entry unmasked. Validated at
        # init() against the configured pool; empty means the unmasked entry is
        # never built at all.
        self._exempt_transports = exempt_transports

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
            retention_policy=self._retention_policy,
            exempt_transports=self._exempt_transports,
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
            audit = logger.with_retention({'years': 7, 'class': 'SOX'})  # inline

        The stamped fields (retention / retention_class / retention_days) travel
        on every entry and are never filtered by the Logging Matrix — they are
        bindings, not context. `retention_until` is added per entry, from that
        entry's own timestamp; see `_emit`.

        Raises `RetentionPolicyNotFoundError` when the name is not registered.
        This is a logger-construction call, made once at wiring time, so it does
        not touch slpy's promise that a log call cannot throw. A typo here is a
        record persisted with no retention at all, found at audit time — that is
        worth a loud failure at startup.
        """
        from .retention import RetentionPolicyNotFoundError, _to_policy

        if isinstance(name_or_policy, dict):
            policy = _to_policy(name_or_policy)
            stamp = (
                self._retention.stamp(name_or_policy)
                if self._retention is not None
                else {}
            )
        else:
            if self._retention is None:
                raise RetentionPolicyNotFoundError(str(name_or_policy), ())
            stamp = self._retention.stamp(name_or_policy)
            policy = self._retention.require(name_or_policy)

        tagged = self.child(**stamp)
        tagged._retention_policy = policy
        return tagged

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
        at = datetime.now(timezone.utc)
        entry: Dict[str, Any] = {
            "level": level,
            "message": message,
            "timestamp": _iso_timestamp(at),
            "service": self._name,
            **ctx,
            **self._bindings,
            **kwargs,
        }

        # The compliance window is anchored to THIS entry's timestamp, not to
        # when the logger was built: a logger created at startup would otherwise
        # stamp the same date forever, and the window has to be reproducible from
        # the record. Written after the kwargs on purpose — the framework owns
        # this field and a per-call kwarg must not be able to move a retention date.
        if self._retention_policy is not None:
            ends = retention_window.until(at.date(), self._retention_policy)
            if ends is not None:
                entry["retention_until"] = retention_window.to_iso(ends)

        # Masking, then the injection boundary (strip ANSI/control chars).
        masked = self._masking.process(entry) if self._masking else entry
        masked = clean_tree(masked)

        # The unmasked line is built ONLY when a sink is declared exempt, so the
        # feature costs nothing when unused. Exempt skips masking and nothing
        # else: the matrix already filtered the context above, and the sanitizer
        # runs here too — an audit ledger still must not receive ANSI escapes.
        unmasked = clean_tree(entry) if self._exempt_transports else None

        if self._stats is not None:
            self._stats.incr_logs_processed()

        for transport in self._transports:
            try:
                transport.log(self._entry_for(transport, masked, unmasked))
            except Exception as exc:
                self._report_transport_failure(exc, transport)

    def _entry_for(
        self, transport: "Transport", masked: Dict[str, Any], unmasked: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Which of the two lines this sink gets. Guard clauses; decides nothing else.

        The identity check lives HERE, in the logger, where the transport is
        known — never inside a transport, which must not be able to exempt
        itself. The first guard is also what keeps the cost at zero when nobody
        declared an exemption: no name is even computed.
        """
        if unmasked is None:
            return masked
        if transport_name(transport) not in self._exempt_transports:
            return masked
        return unmasked

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
