"""
SyntropyLog core — slpy singleton.

Lifecycle: await slpy.init(config) → use → await slpy.shutdown()
"""

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from .config import ConfigManager
from .context import ContextManager
from .logger import Logger
from .masking import MaskingEngine, MaskingRule, MaskingStrategy
from .matrix import LoggingMatrix
from .observability import ConsoleObservabilityTransport, ObservabilityEngine, OutboundEvent
from .retention import RetentionRegistry
from .stats import SlpyStats, StatsSnapshot
from .transport import ConsoleTransport, resolve_exempt_transports


class SyntropyLog:
    """
    Central singleton. Import and use the pre-built instance:

        from slpy import slpy
        await slpy.init({'logger': {'level': 'info'}})
        logger = slpy.get_logger('my-service')
        logger.info('Ready')
    """

    def __init__(self) -> None:
        self._initialized = False
        self._config: Optional[ConfigManager] = None
        self._context: Optional[ContextManager] = None
        self._masking: Optional[MaskingEngine] = None
        self._transports: list = []
        self._observability: Optional[ObservabilityEngine] = None
        self._loggers: Dict[str, Logger] = {}
        self._matrix: Optional[LoggingMatrix] = None
        self._exempt_transports = frozenset()
        self._stats: Optional[SlpyStats] = None
        self._retention: Optional[RetentionRegistry] = None

    async def init(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize slpy. Call once at application startup.

            await slpy.init({
                'logger': {'level': 'info'},
                'masking': {'enable_default_rules': True},
            })

        If no transport is configured, ConsoleTransport (JSON) is used.
        """
        if self._initialized:
            raise RuntimeError("slpy is already initialized. Call shutdown() first.")

        cfg = ConfigManager(config or {})
        cfg.validate()
        self._config = cfg

        # Context
        self._context = ContextManager()

        # Logging Matrix — per-level whitelist of context fields
        self._matrix = LoggingMatrix.create(cfg.logging_matrix)

        # Self-observability counters (slpy.get_stats())
        self._stats = SlpyStats()

        # Retention policies — compliance metadata resolved by name
        self._retention = RetentionRegistry.create(cfg.retention_policies)

        # Masking
        masking_cfg = cfg.masking
        extra_rules = [
            MaskingRule(
                pattern=r["pattern"],
                strategy=MaskingStrategy(r.get("strategy", "token")),
                preserve_length=r.get("preserve_length", True),
                mask_char=r.get("mask_char", "*"),
            )
            for r in masking_cfg.rules
        ]
        self._masking = MaskingEngine(
            enable_default_rules=masking_cfg.enable_default_rules,
            extra_rules=extra_rules or None,
            max_depth=masking_cfg.max_depth,
            on_masking_error=masking_cfg.on_masking_error,
        )

        # Transports — fall back to ConsoleTransport if none provided
        configured = cfg.logger.transports
        self._transports = list(configured) if configured else [ConsoleTransport()]

        # Masking exemptions, validated against the transports that actually
        # exist. Raises here rather than masking the audit sink in silence.
        self._exempt_transports = resolve_exempt_transports(
            masking_cfg.exempt_transports, self._transports
        )

        # Observability — fall back to ConsoleObservabilityTransport if none provided
        obs_cfg = cfg.observability
        obs_transports = list(obs_cfg.transports) if obs_cfg.transports else [ConsoleObservabilityTransport()]
        self._observability = ObservabilityEngine(
            transports=obs_transports if obs_cfg.enabled else []
        )

        self._initialized = True

    async def shutdown(self) -> None:
        """Release resources and reset state. Safe to call multiple times."""
        self._initialized = False
        self._config = None
        self._context = None
        self._masking = None
        self._transports = []
        self._observability = None
        self._loggers = {}
        self._matrix = None
        self._stats = None
        self._exempt_transports = frozenset()
        self._retention = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_logger(self, name: str) -> Logger:
        """
        Return a named logger. Instances are cached — same name, same logger.

            payment_log = slpy.get_logger('payment-service')
            payment_log.child(order_id='123').info('Processing')
        """
        self._require_initialized()
        if name not in self._loggers:
            self._loggers[name] = Logger(
                name=name,
                level=self._config.logger.level,
                transports=self._transports,
                masking=self._masking,
                context_mgr=self._context,
                matrix=self._matrix,
                stats=self._stats,
                on_log_failure=self._config.logger.on_log_failure,
                retention=self._retention,
                exempt_transports=self._exempt_transports,
            )
        return self._loggers[name]

    @asynccontextmanager
    async def context(self, **kwargs: Any):
        """
        Open a context scope. All logs within the scope carry the given fields.

            async with slpy.context(user_id='123', request_id='abc'):
                logger.info('User action')
        """
        self._require_initialized()
        async with self._context.scope(**kwargs):
            yield

    def set_level(self, level: str) -> None:
        """Change log level at runtime for all loggers."""
        self._require_initialized()
        self._config.logger.level = level
        for logger in self._loggers.values():
            logger._level = level

    def reconfigure_logging_matrix(self, matrix: Dict[str, list]) -> None:
        """
        Replace the Logging Matrix at runtime — no restart needed.

        Security boundary: only context-field visibility changes; masking,
        levels and transports stay as set at init().

            slpy.reconfigure_logging_matrix({'default': ['correlation_id'], 'error': ['*']})
        """
        self._require_initialized()
        self._matrix = LoggingMatrix.create(matrix)
        for logger in self._loggers.values():
            logger._matrix = self._matrix

    def get_propagation_headers(self, target: Optional[str] = None) -> Dict[str, str]:
        """
        Return propagation fields with the key names for the given target.

        Without target — uses the HTTP header names from context.propagation:
            slpy.get_propagation_headers()
            # → {"X-Correlation-ID": "abc-123", "X-Trace-ID": "xyz-789"}

        With target — uses the key names configured in context.targets:
            slpy.get_propagation_headers("kafka")
            # → {"correlationId": "abc-123", "traceId": "xyz-789"}

            slpy.get_propagation_headers("s3")
            # → {"Correlation_ID": "abc-123"}

        Only fields that have a value in the current context are included.

        Usage:
            await httpx.get(url, headers=slpy.get_propagation_headers())
            await kafka.send(topic, headers=slpy.get_propagation_headers("kafka"))
            await s3.put_object(Metadata=slpy.get_propagation_headers("s3"))
            await azure_bus.send(msg, properties=slpy.get_propagation_headers("azure"))
        """
        self._require_initialized()
        ctx: Dict[str, Any] = self._context.get()
        result: Dict[str, str] = {}
        target_key = target or "http"
        target_map: Dict[str, str] = self._config.context.outbound.get(target_key, {})

        for field_name, wire_name in target_map.items():
            value = ctx.get(field_name)
            if value is not None:
                result[wire_name] = str(value)

        # Emit outbound event — trazability of context leaving the service
        self._observability.record(OutboundEvent(
            target=target_key,
            headers=result,
            correlation_id=ctx.get("correlation_id"),
            trace_id=ctx.get("trace_id"),
        ))

        return result

    def get(self, field_name: str) -> Optional[str]:
        """
        Return the current value of any context field, or None.

            slpy.get(slpy.CORRELATION_ID)   # -> 'req-001'
            slpy.get(slpy.TRACE_ID)         # -> 'trace-xyz'
            slpy.get('tenant_id')           # -> works for any custom field too
        """
        self._require_initialized()
        return self._context.get().get(field_name)

    def get_propagation_header_name(self, field_name: str) -> Optional[str]:
        """
        Return the configured HTTP header name for a conceptual field.

            slpy.get_propagation_header_name("correlation_id")
            # → "X-Correlation-ID"

            slpy.get_propagation_header_name("trace_id")
            # → "X-B3-TraceId"  (if configured)
        """
        self._require_initialized()
        return self._config.context.outbound.get("http", {}).get(field_name)

    def get_stats(self) -> StatsSnapshot:
        """
        Snapshot of the pipeline's health counters — how many entries were
        processed, and how many failures the Silent Observer absorbed.

            stats = slpy.get_stats()
            stats.logs_processed      # entries emitted
            stats.transport_failures  # transport.log() raised (isolated)
            stats.masking_failures    # masking failed (safe payload emitted)
            stats.uptime_seconds
            stats.native_active       # Rust masking engine in use
        """
        self._require_initialized()
        return self._stats.snapshot(
            masking_failures=self._masking.failures if self._masking else 0,
            native_active=self._masking.is_native if self._masking else False,
        )

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError(
                "slpy is not initialized. Call `await slpy.init(config)` first."
            )
