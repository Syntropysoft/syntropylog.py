"""
Example 05 — with_meta() and audit level

with_meta(payload) attaches arbitrary structured metadata to every log
emitted by that logger instance. The payload travels sanitized to all
transports as logEntry['meta'].

Use cases:
- Retention routing:  tell the executor how long to keep this log
- Compliance tagging: GDPR, PCI-DSS, SOX
- Feature context:    experiment IDs, release tags

audit level bypasses the configured level filter — always emitted.
Use it for compliance events that must always be recorded.
"""

import asyncio
from slpy import slpy


async def main():
    await slpy.init({
        'logger': {'level': 'info'},
        'masking': {'enable_default_rules': True},
    })

    logger = slpy.get_logger('compliance-service')

    # Retention policy attached once — every log from this instance carries it
    audit_logger = logger.with_meta({
        'ttl_days': 2 * 365,        # keep for 2 years
        'regulation': 'GDPR',
        'data_class': 'PII',
        'destination': 'audit-store',
    })

    audit_logger.audit('User data exported', user_id='USR-42', records=1500)
    audit_logger.audit('Consent updated', user_id='USR-42', action='opt-out')

    # Combine with_meta + child for full context
    payment_logger = logger.with_meta({
        'ttl_days': 7 * 365,
        'regulation': 'PCI-DSS',
        'destination': 'payment-audit',
    }).child(merchant_id='MCH-001')

    payment_logger.audit('Card charged', amount=299.90, currency='USD')
    payment_logger.audit('Refund issued', amount=50.00, reason='item-returned')

    # audit always emits — even when level is 'error'
    await slpy.shutdown()
    await slpy.init({'logger': {'level': 'error'}})
    restricted_logger = slpy.get_logger('restricted')
    restricted_logger.info('This will NOT appear — level is error')
    restricted_logger.audit('This WILL appear — audit bypasses level filter')

    await slpy.shutdown()


asyncio.run(main())
