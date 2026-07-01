"""Shared FastAPI dependencies — DB session, Redis, optional auth."""
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.session import get_db

# Re-export get_db for convenience
__all__ = ["get_db", "get_redis"]


async def get_redis() -> aioredis.Redis:
    """Yield an async Redis client."""
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()
