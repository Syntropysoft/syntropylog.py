"""
Example 07 — PrettyConsoleTransport

Human-readable colored output for development.
Automatically falls back to JSON when stdout is not a TTY (CI, pipes, production).

Run this example in a real terminal to see colors.
"""

import asyncio
from slpy import slpy, PrettyConsoleTransport


async def main():
    await slpy.init({
        'logger': {
            'level': 'debug',
            'transports': [PrettyConsoleTransport()],
        },
        'masking': {'enable_default_rules': True},
    })

    logger = slpy.get_logger('payment-service')

    logger.debug('Starting up', version='0.1.0')
    logger.info('Service ready', port=8080)
    logger.warn('High memory usage', heap_mb=420, threshold_mb=512)
    logger.error('Connection refused', host='db.internal', port=5432)

    # child() bindings appear in the key=value tail
    order_log = logger.child(order_id='ORD-001', user_id='USR-42')
    order_log.info('Processing order')
    order_log.info('Payment approved', amount=299.90, currency='USD')

    # Masking active — email masked automatically
    logger.info('User login', email='john@example.com', ip='192.168.1.1')

    # audit level — cyan
    logger.with_meta({'regulation': 'GDPR'}).audit('Data exported', records=1500)

    # Context propagation — fields from context appear in the tail
    async with slpy.context(request_id='req-abc', path='/api/orders'):
        logger.info('Request handled', status=200, duration_ms=42)

    await slpy.shutdown()


asyncio.run(main())
