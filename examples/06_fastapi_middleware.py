"""
Example 06 — FastAPI middleware

SyntropyMiddleware wires automatic context propagation into every request.
Every log emitted during a request automatically carries:
    correlation_id, method, path

Install: pip install slpy[fastapi]
Run:     uvicorn examples.06_fastapi_middleware:app --reload
"""

import asyncio
from contextlib import asynccontextmanager

from slpy import slpy
from slpy.fastapi import SyntropyMiddleware

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
except ImportError:
    print("FastAPI not installed. Run: pip install fastapi uvicorn")
    exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await slpy.init({
        'logger': {'level': 'info'},
        'masking': {'enable_default_rules': True},
    })
    yield
    await slpy.shutdown()


app = FastAPI(lifespan=lifespan)
app.add_middleware(SyntropyMiddleware)

# Logger is obtained lazily — slpy.get_logger() requires init() to have run.
# In FastAPI, initialization happens in lifespan, not at import time.
def get_logger():
    return slpy.get_logger('api')


@app.get('/orders/{order_id}')
async def get_order(order_id: str):
    logger = get_logger()
    # correlation_id, method, path are already in context — no extra work needed
    logger.info('Fetching order', order_id=order_id)

    # Simulate a nested service call — context propagates automatically
    await fetch_from_db(order_id)

    logger.info('Order returned', order_id=order_id)
    return JSONResponse({'order_id': order_id, 'status': 'active'})


@app.post('/orders')
async def create_order(data: dict = None):
    order_logger = get_logger().child(action='create-order')
    order_logger.info('Creating order', payload=data)
    order_logger.audit('Order created', order_id='ORD-NEW', amount=299.90)
    return JSONResponse({'order_id': 'ORD-NEW', 'status': 'created'}, status_code=201)


async def fetch_from_db(order_id: str) -> dict:
    # context_id and all context fields are still here — same contextvars scope
    get_logger().debug('DB query', table='orders', order_id=order_id)
    return {'order_id': order_id}
