"""
Redis response cache (gated).
====================================================================
Thin JSON cache over Redis. Every function is a no-op when REDIS_URL is unset,
so behavior is identical in local development. Cache keys should embed an
artifact signature (file mtime/size) so results invalidate automatically when
the underlying pipeline artifacts change.
"""
from __future__ import annotations

import json
from typing import Any, Optional

try:  # works whether launched from backend/ or as the backend package
    from config import settings
except ImportError:  # pragma: no cover
    from backend.config import settings


_client = None


def _get_client():
    global _client
    if _client is None:
        import redis  # lazy: only imported when Redis is configured

        _client = redis.from_url(settings.require("redis_url"))
    return _client


def cache_get(key: str) -> Optional[Any]:
    if not settings.redis_enabled:
        return None
    try:
        raw = _get_client().get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    if not settings.redis_enabled:
        return
    try:
        _get_client().set(key, json.dumps(value), ex=ttl)
    except Exception:
        # Caching is best-effort; never fail a request because Redis is down.
        pass
