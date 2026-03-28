"""
Example 03 — Context propagation with async with slpy.context()

slpy uses Python's native contextvars — the same mechanism as AsyncLocalStorage in Node.js.
Context set in a scope propagates automatically to all log calls within that scope,
including nested async functions and asyncio.gather() tasks.

No need to thread request_id through every function signature.
"""

import asyncio
from slpy import slpy

logger = None  # will be set after init


async def handle_database_query(query: str) -> dict:
    # request_id and user_id from the outer context appear automatically
    logger.debug('Running query', query=query)
    logger.info('Query complete', rows=42)
    return {'rows': 42}


async def handle_request(request_id: str, user_id: str, path: str) -> None:
    async with slpy.context(request_id=request_id, user_id=user_id, path=path):
        logger.info('Request received')

        result = await handle_database_query('SELECT * FROM orders')

        logger.info('Request complete', status=200, rows=result['rows'])


async def main():
    global logger
    await slpy.init({'logger': {'level': 'debug'}})
    logger = slpy.get_logger('api-service')

    # Simulate two concurrent requests — contexts are fully isolated
    await asyncio.gather(
        handle_request('req-001', 'usr-10', '/api/orders'),
        handle_request('req-002', 'usr-20', '/api/products'),
    )

    await slpy.shutdown()


asyncio.run(main())
