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
from .transport import ConsoleTransport, Transport


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
        self._loggers: Dict[str, Logger] = {}

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
        )

        # Transports — fall back to ConsoleTransport if none provided
        configured = cfg.logger.transports
        self._transports = list(configured) if configured else [ConsoleTransport()]

        self._initialized = True

    async def shutdown(self) -> None:
        """Release resources and reset state. Safe to call multiple times."""
        self._initialized = False
        self._config = None
        self._context = None
        self._masking = None
        self._transports = []
        self._loggers = {}

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

    def get_propagation_headers(self) -> Dict[str, str]:
        """
        Return all propagation headers with their configured HTTP header names
        and current context values. Only includes fields that have a value.

        Use this to forward context to any outgoing call — HTTP, Kafka,
        gRPC, RabbitMQ, or any other transport.

            headers = slpy.get_propagation_headers()
            # → {"X-Correlation-ID": "abc-123", "X-Trace-ID": "xyz-789"}

            await httpx.get(url, headers=headers)
            await kafka_producer.send(topic, headers=headers)
        """
        self._require_initialized()
        ctx: Dict[str, Any] = self._context.get()
        propagation: Dict[str, str] = self._config.context.propagation
        result: Dict[str, str] = {}
        for field_name, header_name in propagation.items():
            value = ctx.get(field_name)
            if value is not None:
                result[header_name] = str(value)
        return result

    def get_correlation_id(self) -> Optional[str]:
        """Return the current correlation_id from context, or None."""
        self._require_initialized()
        return self._context.get().get("correlation_id")

    def get_trace_id(self) -> Optional[str]:
        """Return the current trace_id from context, or None."""
        self._require_initialized()
        return self._context.get().get("trace_id")

    def get_session_id(self) -> Optional[str]:
        """Return the current session_id from context, or None."""
        self._require_initialized()
        return self._context.get().get("session_id")

    def get_transaction_id(self) -> Optional[str]:
        """Return the current transaction_id from context, or None."""
        self._require_initialized()
        return self._context.get().get("transaction_id")

    def get_propagation_header_name(self, field_name: str) -> Optional[str]:
        """
        Return the configured HTTP header name for a conceptual field.

            slpy.get_propagation_header_name("correlation_id")
            # → "X-Correlation-ID"

            slpy.get_propagation_header_name("trace_id")
            # → "X-B3-TraceId"  (if configured)
        """
        self._require_initialized()
        return self._config.context.propagation.get(field_name)

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
