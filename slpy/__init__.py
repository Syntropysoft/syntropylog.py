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
from .transport import Transport, ConsoleTransport, PrettyConsoleTransport, UniversalAdapter, AdapterTransport
from .masking import MASK_KEYS, MaskingEngine, MaskingRule, MaskingStrategy, mask_pattern
from .matrix import LoggingMatrix
from .retention import RetentionPolicy, RetentionRegistry
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
    "DurableFileTransport",
    "MaskingEngine",
    "MaskingRule",
    "MaskingStrategy",
    "MASK_KEYS",
    "mask_pattern",
    "LoggingMatrix",
    "StatsSnapshot",
    "RetentionPolicy",
    "RetentionRegistry",
    "ObservabilityTransport",
    "ConsoleObservabilityTransport",
    "OutboundEvent",
    "Logger",
]

__version__ = "0.4.1"
__author__ = "Syntropysoft"
__license__ = "Apache-2.0"
