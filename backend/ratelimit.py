"""
Request rate limiting (gated).
====================================================================
Fixed-window limiter keyed by the authenticated user (falling back to client
IP). Backend selection:

  * REDIS_URL set            -> Redis counters (shared across workers/instances).
  * RATE_LIMIT_ENABLED=true   -> per-process in-memory fallback (single instance).
  * neither                   -> no-op (local development is unaffected).

Limits are intentionally generous; they exist to stop abuse/runaway loops, while
per-plan monthly quotas (see billing.py) handle fair-use accounting.
"""
from __future__ import annotations

import threading
import time

from fastapi import Depends, HTTPException, Request

try:  # works whether launched from backend/ or as the backend package
    from config import settings
except ImportError:  # pragma: no cover
    from backend.config import settings


# name -> (max_requests, window_seconds)
LIMITS: dict[str, tuple[int, int]] = {
    "scan": (10, 60),
    "cluster": (10, 60),
    "generate": (20, 60),
    "generate_all": (5, 60),
    "chat": (30, 60),
}
_DEFAULT_LIMIT = (60, 60)


def _active() -> bool:
    return settings.redis_enabled or settings.rate_limit_enabled


# ---------------------------------------------------------------------------
# In-memory fallback (per process)
# ---------------------------------------------------------------------------
_mem_lock = threading.Lock()
_mem_hits: dict[str, tuple[int, float]] = {}


def _mem_allow(key: str, limit: int, window: int) -> bool:
    now = time.time()
    with _mem_lock:
        count, start = _mem_hits.get(key, (0, now))
        if now - start >= window:
            count, start = 0, now
        count += 1
        _mem_hits[key] = (count, start)
        return count <= limit


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis  # lazy: only imported when Redis is configured

        _redis_client = redis.from_url(settings.require("redis_url"))
    return _redis_client


def _redis_allow(key: str, limit: int, window: int) -> bool:
    try:
        client = _get_redis()
        bucket = int(time.time() // window)
        redis_key = f"rl:{key}:{bucket}"
        count = client.incr(redis_key)
        if count == 1:
            client.expire(redis_key, window)
        return count <= limit
    except Exception:
        # If Redis is unreachable, fail open so we never block real users
        # because of an infra hiccup.
        return True


# ---------------------------------------------------------------------------
# Identity + enforcement
# ---------------------------------------------------------------------------
def _identity(request: Request) -> str:
    principal = getattr(request.state, "principal", None)
    if principal is not None and getattr(principal, "clerk_user_id", None):
        return f"user:{principal.clerk_user_id}"
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return "ip:" + xff.split(",")[0].strip()
    client = request.client
    return "ip:" + (client.host if client else "unknown")


def check_rate_limit(request: Request, name: str) -> None:
    if not _active():
        return
    limit, window = LIMITS.get(name, _DEFAULT_LIMIT)
    key = f"{name}:{_identity(request)}"
    allowed = _redis_allow(key, limit, window) if settings.redis_enabled else _mem_allow(key, limit, window)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for '{name}'. Try again in up to {window}s.",
            headers={"Retry-After": str(window)},
        )


def rate_limit(name: str):
    """Build a dependency that enforces the rate limit for ``name``."""

    def _dependency(request: Request):
        check_rate_limit(request, name)

    return Depends(_dependency)
