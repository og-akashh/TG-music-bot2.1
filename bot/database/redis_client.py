"""
redis_client.py — Async Redis wrapper built on aioredis.

Provides:
  • Queue persistence (per chat_id)
  • Playback state caching
  • Rate-limit counters
  • Generic key/value cache with TTL
"""

import json
from typing import Any, List, Optional

import aioredis

from bot.config import config
from bot.utils.logger import get_logger

log = get_logger(__name__)

# Module-level connection pool (initialised in connect())
_redis: Optional[aioredis.Redis] = None


async def connect() -> None:
    global _redis
    _redis = await aioredis.from_url(
        config.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    await _redis.ping()
    log.info("Redis connected ✓")


async def disconnect() -> None:
    if _redis:
        await _redis.close()
        log.info("Redis disconnected")


def _check() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not connected. Call connect() first.")
    return _redis


# ── Queue helpers ─────────────────────────────────────────────────────────────

QUEUE_KEY = "queue:{chat_id}"
NOW_PLAYING_KEY = "np:{chat_id}"
LOOP_KEY = "loop:{chat_id}"
VOLUME_KEY = "vol:{chat_id}"


async def queue_push(chat_id: int, track: dict) -> int:
    r = _check()
    return await r.rpush(QUEUE_KEY.format(chat_id=chat_id), json.dumps(track))


async def queue_pop(chat_id: int) -> Optional[dict]:
    r = _check()
    raw = await r.lpop(QUEUE_KEY.format(chat_id=chat_id))
    return json.loads(raw) if raw else None


async def queue_peek(chat_id: int) -> Optional[dict]:
    r = _check()
    items = await r.lrange(QUEUE_KEY.format(chat_id=chat_id), 0, 0)
    return json.loads(items[0]) if items else None


async def queue_get_all(chat_id: int) -> List[dict]:
    r = _check()
    items = await r.lrange(QUEUE_KEY.format(chat_id=chat_id), 0, -1)
    return [json.loads(i) for i in items]


async def queue_clear(chat_id: int) -> None:
    r = _check()
    await r.delete(QUEUE_KEY.format(chat_id=chat_id))


async def queue_length(chat_id: int) -> int:
    r = _check()
    return await r.llen(QUEUE_KEY.format(chat_id=chat_id))


async def queue_remove_index(chat_id: int, index: int) -> bool:
    """Remove track at a specific 0-based index from the queue."""
    r = _check()
    key = QUEUE_KEY.format(chat_id=chat_id)
    items = await r.lrange(key, 0, -1)
    if index < 0 or index >= len(items):
        return False
    # Use a placeholder delete trick (set to unique value, then lrem)
    placeholder = "__REMOVED__"
    await r.lset(key, index, placeholder)
    await r.lrem(key, 1, placeholder)
    return True


async def queue_shuffle(chat_id: int) -> None:
    import random
    r = _check()
    key = QUEUE_KEY.format(chat_id=chat_id)
    items = await r.lrange(key, 0, -1)
    if not items:
        return
    random.shuffle(items)
    pipe = r.pipeline()
    pipe.delete(key)
    for item in items:
        pipe.rpush(key, item)
    await pipe.execute()


# ── Now-playing state ─────────────────────────────────────────────────────────

async def set_now_playing(chat_id: int, track: dict) -> None:
    r = _check()
    await r.set(NOW_PLAYING_KEY.format(chat_id=chat_id), json.dumps(track))


async def get_now_playing(chat_id: int) -> Optional[dict]:
    r = _check()
    raw = await r.get(NOW_PLAYING_KEY.format(chat_id=chat_id))
    return json.loads(raw) if raw else None


async def clear_now_playing(chat_id: int) -> None:
    r = _check()
    await r.delete(NOW_PLAYING_KEY.format(chat_id=chat_id))


# ── Loop / Volume state ───────────────────────────────────────────────────────

async def set_loop(chat_id: int, mode: str) -> None:
    """mode: 'off' | 'single' | 'queue'"""
    await _check().set(LOOP_KEY.format(chat_id=chat_id), mode)


async def get_loop(chat_id: int) -> str:
    r = _check()
    val = await r.get(LOOP_KEY.format(chat_id=chat_id))
    return val or "off"


async def set_volume(chat_id: int, volume: int) -> None:
    await _check().set(VOLUME_KEY.format(chat_id=chat_id), volume)


async def get_volume(chat_id: int) -> int:
    r = _check()
    val = await r.get(VOLUME_KEY.format(chat_id=chat_id))
    return int(val) if val else 100


# ── Generic cache ─────────────────────────────────────────────────────────────

async def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    await _check().set(f"cache:{key}", json.dumps(value), ex=ttl)


async def cache_get(key: str) -> Optional[Any]:
    raw = await _check().get(f"cache:{key}")
    return json.loads(raw) if raw else None


# ── Rate limiting ─────────────────────────────────────────────────────────────

async def rate_limit_check(user_id: int, command: str, max_calls: int = 5, window: int = 60) -> bool:
    """Returns True if the user is within the rate limit, False if exceeded."""
    r = _check()
    key = f"rl:{user_id}:{command}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window)
    return count <= max_calls
