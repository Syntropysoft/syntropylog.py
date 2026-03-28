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
from .transport import Transport, ConsoleTransport, PrettyConsoleTransport
from .masking import MaskingEngine, MaskingRule, MaskingStrategy
from .logger import Logger

# Pre-built singleton — import and use directly
slpy = SyntropyLog()

__all__ = [
    "slpy",
    "SyntropyLog",
    "Transport",
    "ConsoleTransport",
    "PrettyConsoleTransport",
    "MaskingEngine",
    "MaskingRule",
    "MaskingStrategy",
    "Logger",
]

__version__ = "0.1.0"
__author__ = "Syntropysoft"
__license__ = "Apache-2.0"
