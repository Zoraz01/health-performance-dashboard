"""
Simple in-memory rate limiter as FastAPI dependencies.

Uses a per-key sliding window. Safe for single-process uvicorn; does not
survive restarts or scale across multiple workers. Sufficient for a
personal dashboard where the goal is preventing accidental loop hammering.
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request

_buckets: dict[str, list[float]] = defaultdict(list)


def make_limiter(limit: int, window_seconds: int):
    """Return a FastAPI dependency that enforces rate limiting by client IP.

    Args:
        limit: max requests allowed in the window
        window_seconds: rolling window length in seconds
    """
    async def _dep(request: Request) -> None:
        key = (request.client.host if request.client else "unknown")
        now = time.monotonic()
        cutoff = now - window_seconds
        bucket = [t for t in _buckets[key] if t > cutoff]
        if len(bucket) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded — max {limit} requests per {window_seconds}s",
            )
        bucket.append(now)
        _buckets[key] = bucket
    return _dep


# Pre-built limiters for each route group.
analyze_limiter = make_limiter(limit=5, window_seconds=60)    # 5/min — Claude subprocess
hevy_limiter    = make_limiter(limit=10, window_seconds=60)   # 10/min — external API
webhook_limiter = make_limiter(limit=30, window_seconds=60)   # 30/min — Apple Health bursts
