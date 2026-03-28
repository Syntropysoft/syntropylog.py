"""
Example 08 — AdapterTransport + UniversalAdapter

You provide an executor function. slpy handles context propagation,
masking, level filtering, and error isolation. The executor receives
the clean, already-masked entry and routes it anywhere.

Same pattern as Node.js SyntropyLog:
    new AdapterTransport({ adapter: new UniversalAdapter({ executor }) })
"""

import asyncio
from datetime import datetime
from slpy import slpy, AdapterTransport, UniversalAdapter, ConsoleTransport

# ---------------------------------------------------------------------------
# In-memory store — stands in for Postgres, MongoDB, Elasticsearch, etc.
# ---------------------------------------------------------------------------
_postgres_rows: list = []
_mongo_docs: list = []
_elastic_docs: list = []


# ---------------------------------------------------------------------------
# Formatter — map slpy fields to your DB schema
# ---------------------------------------------------------------------------
def db_formatter(entry: dict) -> dict:
    return {
        **entry,
        "timestamp": datetime.fromtimestamp(entry["timestamp"] / 1000).isoformat(),
        "source": "slpy-example",
    }


# ---------------------------------------------------------------------------
# Executor — one function, N destinations, fully async
# ---------------------------------------------------------------------------
async def db_executor(data: dict) -> None:
    await asyncio.gather(
        save_postgres(data),
        save_mongo(data),
        save_elastic(data),
    )


async def save_postgres(row: dict) -> None:
    # await prisma.system_log.create(data=row)
    _postgres_rows.append(row)


async def save_mongo(doc: dict) -> None:
    # await mongo_collection.insert_one(doc)
    _mongo_docs.append(doc)


async def save_elastic(doc: dict) -> None:
    # await es.index(index='logs', body=doc)
    _elastic_docs.append(doc)


# ---------------------------------------------------------------------------
# Wire everything together
# ---------------------------------------------------------------------------
db_transport = AdapterTransport(
    name="db",
    adapter=UniversalAdapter(executor=db_executor),
    formatter=db_formatter,
)


async def main():
    await slpy.init({
        "logger": {
            "level": "info",
            "transports": [
                db_transport,       # → Postgres + MongoDB + Elasticsearch
                ConsoleTransport(), # → stdout as JSON
            ],
        },
        "masking": {"enable_default_rules": True},
    })

    logger = slpy.get_logger("payment-service")

    async with slpy.context(request_id="req-001", user_id="USR-42"):
        logger.info("Card charged", amount=299.90, email="john@example.com")
        logger.warn("Retry attempt", attempt=2, card="4111-1111-1111-1234")

    # Give async tasks a moment to complete
    await asyncio.sleep(0.05)

    print(f"\n--- Stored in Postgres ({len(_postgres_rows)} rows) ---")
    for row in _postgres_rows:
        print(f"  {row['level']}  {row['message']}  ts={row['timestamp']}")

    print(f"\n--- Stored in MongoDB ({len(_mongo_docs)} docs) ---")
    for doc in _mongo_docs:
        print(f"  {doc['level']}  {doc['message']}  email={doc.get('email', '(not present)')}")

    print(f"\n--- Stored in Elasticsearch ({len(_elastic_docs)} docs) ---")
    for doc in _elastic_docs:
        print(f"  request_id={doc.get('request_id')}  user_id={doc.get('user_id')}")

    await slpy.shutdown()


asyncio.run(main())
