"""
slpy — The Declarative Observability Framework for Python.

You declare what each log should carry. slpy handles the rest.

Quick start:

    from slpy import slpy

    async def main():
        await slpy.init({
            'logger': {'level': 'info'},
            'masking': {'enable_default_rules': True},
        })

        logger = slpy.get_logger('my-service')
        logger.info('Ready')

        async with slpy.context(user_id='123', request_id='abc'):
            logger.info('User action')

        await slpy.shutdown()
"""

from .core import SyntropyLog
from .durable import DurableFileTransport
from .transport import (AdapterTransport, ConsoleTransport, PrettyConsoleTransport,
                        Transport, UniversalAdapter, UnknownExemptTransportError,
                        transport_name)
from .masking import (MASK_KEYS, MaskingEngine, MaskingRule, MaskingStrategy,
                      mask_pattern, strategy_to_spec)
from .mask_spec import REDACTED, MaskSpec, apply_mask
from .matrix import LoggingMatrix
from .retention import (RetentionConfigurationError, RetentionPolicy,
                        RetentionPolicyNotFoundError, RetentionRegistry)
from .retention_window import retention_until
from .stats import StatsSnapshot
from .observability import ObservabilityTransport, ConsoleObservabilityTransport, OutboundEvent
from .logger import Logger

# Pre-built singleton — import and use directly
slpy = SyntropyLog()

__all__ = [
    "slpy",
    "SyntropyLog",
    "Transport",
    "ConsoleTransport",
    "PrettyConsoleTransport",
    "UniversalAdapter",
    "AdapterTransport",
    "UnknownExemptTransportError",
    "transport_name",
    "DurableFileTransport",
    "MaskingEngine",
    "MaskingRule",
    "MaskingStrategy",
    "MASK_KEYS",
    "mask_pattern",
    "MaskSpec",
    "apply_mask",
    "strategy_to_spec",
    "REDACTED",
    "LoggingMatrix",
    "StatsSnapshot",
    "RetentionPolicy",
    "RetentionRegistry",
    "RetentionPolicyNotFoundError",
    "RetentionConfigurationError",
    "retention_until",
    "ObservabilityTransport",
    "ConsoleObservabilityTransport",
    "OutboundEvent",
    "Logger",
]

__version__ = "1.0.0"
__author__ = "Syntropysoft"
__license__ = "Apache-2.0"
