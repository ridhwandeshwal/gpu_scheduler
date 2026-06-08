"""Redis queue operations for job dispatch, heartbeats, and distributed locks.

Redis is used ONLY for:
  - Dispatch queues (job scheduling → worker pickup)
  - Temporary distributed locks
  - Worker heartbeats

Redis is NEVER used as permanent storage. PostgreSQL is the single source of truth.
"""

from __future__ import annotations

import uuid
from typing import Optional

import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()

# ── Connection pool ───────────────────────────────────────

_pool: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Return a shared async Redis connection (lazily initialised)."""
    global _pool
    if _pool is None:
        _pool = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _pool


async def close_redis() -> None:
    """Close the Redis connection pool (call at app shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


# ── Queue operations ──────────────────────────────────────


async def push_job(queue_name: str, run_id: uuid.UUID) -> None:
    """Push a run_id onto the ready queue for worker pickup.

    Key format: ``queue:ready:<queue_name>``
    """
    r = await get_redis()
    key = f"queue:ready:{queue_name}"
    await r.rpush(key, str(run_id))


async def pop_job(queue_name: str, timeout: int = 0) -> Optional[str]:
    """Blocking pop from the ready queue.

    Args:
        queue_name: Name of the queue to pop from.
        timeout: Seconds to block. 0 = block indefinitely.

    Returns:
        The run_id as a string, or None if the timeout expired.
    """
    r = await get_redis()
    key = f"queue:ready:{queue_name}"
    result = await r.blpop(key, timeout=timeout)
    if result is None:
        return None
    # blpop returns (key, value)
    _, run_id = result
    return run_id


# ── Heartbeat operations ─────────────────────────────────


async def set_heartbeat(worker_id: uuid.UUID, ttl: int = 30) -> None:
    """Record a worker heartbeat with a TTL.

    Key format: ``worker:heartbeat:<worker_id>``
    """
    r = await get_redis()
    import time

    key = f"worker:heartbeat:{worker_id}"
    await r.set(key, str(int(time.time())), ex=ttl)


async def get_heartbeat(worker_id: uuid.UUID) -> Optional[str]:
    """Check whether a worker heartbeat is still alive."""
    r = await get_redis()
    key = f"worker:heartbeat:{worker_id}"
    return await r.get(key)


# ── Distributed locks ─────────────────────────────────────


async def acquire_lock(lock_key: str, ttl: int = 30) -> bool:
    """Attempt to acquire a distributed lock.

    Uses ``SET NX EX`` (set-if-not-exists with expiry).

    Args:
        lock_key: The Redis key for the lock.
        ttl: Lock expiry in seconds (auto-release safety net).

    Returns:
        True if the lock was acquired, False if already held.
    """
    r = await get_redis()
    result = await r.set(lock_key, "1", nx=True, ex=ttl)
    return result is True


async def release_lock(lock_key: str) -> None:
    """Release a distributed lock."""
    r = await get_redis()
    await r.delete(lock_key)
