from collections.abc import AsyncIterator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings
from app.core.logging import get_logger


logger = get_logger(__name__)
_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    settings = get_settings()
    return get_client()[settings.mongodb_database]


async def init_db() -> None:
    db = get_database()
    await db.users.create_index("email", unique=True)
    await db.sessions.create_index([("user_id", 1), ("updated_at", -1)])
    await db.saved_sources.create_index([("user_id", 1), ("uri_fingerprint", 1)], unique=True)
    await db.refresh_tokens.create_index([("user_id", 1), ("created_at", -1)])
    logger.info("Mongo indexes ensured.")


async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("Mongo client closed.")


async def collection_names() -> AsyncIterator[str]:
    for name in await get_database().list_collection_names():
        yield name
