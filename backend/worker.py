"""
arq worker process (Phase 5).
====================================================================
Runs the long-running generation jobs enqueued by the web process. Requires
REDIS_URL and shares the filesystem with the web process.

Start it (from the repo root):
    arq backend.worker.WorkerSettings
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Make the sibling modules importable in every launch mode.
sys.path.insert(0, str(Path(__file__).parent))

from config import settings
from arq.connections import RedisSettings

from pipeline_runner import step4_generate, CLUSTERS_JSON
from generate_services import dedup_service_names


async def generate_all_job(ctx, repo_path, cluster_names, max_workers):
    """Generate microservices for the selected clusters (runs in the worker)."""
    with open(CLUSTERS_JSON, encoding="utf-8") as f:
        clusters = dedup_service_names(json.load(f))

    selected = cluster_names or list(clusters.keys())
    filtered = {name: clusters[name] for name in selected if name in clusters}
    workers = max_workers or settings.generation_workers

    # step4_generate is synchronous/blocking; run it off the event loop.
    results = await asyncio.get_event_loop().run_in_executor(
        None, lambda: step4_generate(repo_path, filtered, False, workers)
    )

    return {
        "status": "ok",
        "total": len(results),
        "generated": sum(1 for r in results if r["status"] == "generated"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "services": results,
    }


class WorkerSettings:
    functions = [generate_all_job]
    redis_settings = (
        RedisSettings.from_dsn(settings.redis_url)
        if settings.redis_url
        else RedisSettings()
    )
