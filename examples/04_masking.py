"""
Example 04 — Data masking

Masking runs automatically on every log entry.
Default rules cover: email, password, token, credit card, SSN, phone.
Add custom rules at init() — patterns are compiled once, applied on every log.

The masking engine flattens nested objects, applies rules by leaf key name,
then reconstructs the original structure. No manual scrubbing needed.
"""

import asyncio
from slpy import slpy, MaskingRule, MaskingStrategy


async def main():
    await slpy.init({
        'logger': {'level': 'info'},
        'masking': {
            'enable_default_rules': True,
            # Add a custom rule for internal fields
            'rules': [
                {
                    'pattern': r'internal_code',
                    'strategy': 'token',
                    'mask_char': '#',
                },
            ],
        },
    })

    logger = slpy.get_logger('payment-service')

    # Sensitive fields are masked automatically — no changes to log call needed
    logger.info('User registered',
        email='john.doe@example.com',
        password='super-secret-123',
        name='John Doe',
    )

    logger.info('Payment initiated',
        credit_card_number='4111-1111-1111-1234',
        amount=299.90,
        currency='USD',
    )

    logger.info('Token issued',
        auth_token='eyJhbGciOiJIUzI1NiJ9.payload.signature',
        user_id='USR-42',
    )

    # Nested objects are flattened and masked at any depth
    logger.info('Order placed', order={
        'id': 'ORD-001',
        'user': {
            'email': 'jane@example.com',
            'token': 'secret-token-abc',
        },
        'total': 149.00,
    })

    await slpy.shutdown()


asyncio.run(main())
