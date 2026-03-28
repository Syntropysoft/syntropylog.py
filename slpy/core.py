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

    def get_correlation_id(self) -> Optional[str]:
        """
        Return the correlation_id from the current context, or None if not set.

        Useful when you need to forward the correlation_id to an outgoing
        HTTP call or a message queue without going through a logger.

            correlation_id = slpy.get_correlation_id()
            headers = {"X-Correlation-ID": correlation_id} if correlation_id else {}
        """
        self._require_initialized()
        return self._context.get().get("correlation_id")

    def get_correlation_id_header_name(self) -> str:
        """
        Return the HTTP header name used for correlation_id propagation.

        Matches the correlation_header configured in SyntropyMiddleware
        (default: 'X-Correlation-ID').

            header_name = slpy.get_correlation_id_header_name()
            correlation_id = request.headers.get(header_name)
        """
        try:
            from slpy.fastapi import _correlation_header
            return _correlation_header
        except ImportError:
            return "X-Correlation-ID"

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
