"""
Example 02 — Named loggers and child()

Each service / component gets its own named logger.
child() binds context once — every log from that instance carries it automatically.
Bindings are immutable and composable: child() always returns a new logger.
"""

import asyncio
from slpy import slpy


async def process_order(order_id: str, user_id: str) -> None:
    # Bind order context once — no need to repeat on every log call
    logger = slpy.get_logger('order-service').child(
        order_id=order_id,
        user_id=user_id,
    )

    logger.info('Processing order')

    total = 3 * 99.90
    logger.info('Order calculated', total=total, items=3)

    # Nested child — adds more context without losing the parent bindings
    payment_logger = logger.child(step='payment')
    payment_logger.info('Charging card')
    payment_logger.info('Payment approved', amount=total)

    logger.info('Order complete')


async def validate_order(order_id: str) -> bool:
    logger = slpy.get_logger('validation-service').child(order_id=order_id)
    logger.info('Validating')
    logger.info('Validation passed')
    return True


async def main():
    await slpy.init({'logger': {'level': 'info'}})

    await validate_order('ORD-001')
    await process_order('ORD-001', 'USR-42')

    await slpy.shutdown()


asyncio.run(main())
