"""
Example 01 — Basic setup and initialization

The canonical pattern:
    await slpy.init(config)   → initialize once
    slpy.get_logger(name)     → named logger, cached per name
    await slpy.shutdown()     → clean up at exit

If no transport is configured, ConsoleTransport (JSON) is used automatically.
"""

import asyncio
from slpy import slpy


async def main():
    await slpy.init({
        'logger': {'level': 'info'},
    })

    logger = slpy.get_logger('my-service')

    logger.debug('This will not appear — level is info')
    logger.info('Service started')
    logger.warn('Low disk space', disk_free_mb=512)
    logger.error('Connection refused', host='db.internal', port=5432)

    await slpy.shutdown()


asyncio.run(main())
