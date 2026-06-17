"""
Async job queue via arq (gated on Redis).
====================================================================
Offloads long-running generation so the HTTP request returns immediately and the
UI polls for status. Entirely gated: arq is imported lazily and these helpers are
only reached when REDIS_URL is set (callers check ``settings.redis_enabled`` and
otherwise fall back to running generation synchronously).

The arq worker is a separate process (see worker.py / Procfile) that shares the
filesystem with the web process.
"""
from __future__ import annotations

from typing import Any, Optional

try:  # works whether launched from backend/ or as the backend package
    from config import settings
except ImportError:  # pragma: no cover
    from backend.config import settings


_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        _pool = await create_pool(RedisSettings.from_dsn(settings.require("redis_url")))
    return _pool


async def enqueue_generate_all(
    repo_path: str,
    cluster_names: Optional[list[str]],
    max_workers: Optional[int],
) -> str:
    pool = await get_pool()
    job = await pool.enqueue_job("generate_all_job", repo_path, cluster_names, max_workers)
    return job.job_id


async def get_job(job_id: str) -> dict[str, Any]:
    from arq.jobs import Job, JobStatus

    pool = await get_pool()
    job = Job(job_id, redis=pool)
    status = await job.status()
    status_str = status.value if hasattr(status, "value") else str(status)
    out: dict[str, Any] = {"job_id": job_id, "status": status_str}

    if status == JobStatus.complete:
        try:
            out["result"] = await job.result(timeout=1)
        except Exception as exc:  # job raised, or result expired
            out["error"] = str(exc)
    return out
