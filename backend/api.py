"""
FastAPI Backend for the Legacy Refactoring Agent
=================================================
Wraps the pipeline_runner steps as HTTP endpoints for the React frontend.

Start with:
    cd extractor
    uvicorn api:app --reload --port 8000
"""

import json
import os
import sys
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Ensure extractor modules are importable
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))

# Load .env before importing pipeline modules
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from pipeline_runner import (
    step1_scan, step2_load_graph, step3_cluster,
    step4_generate, step5_summary,
    IMPORT_DIR, SERVICES_DIR, CLUSTERS_JSON,
)
from validators import validate_clusters
from generate_services import dedup_service_names

# ---------------------------------------------------------------------------
# App & CORS
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Legacy Refactoring Agent API",
    version="1.0.0",
    description="API layer for the monolith → microservices pipeline",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:5174",   # Vite fallback port
        "http://localhost:3000",   # CRA fallback
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pipeline state (in-memory, resets on server restart)
# ---------------------------------------------------------------------------
pipeline_state = {
    "step1_done": False,
    "step2_done": False,
    "step3_done": False,
    "step4_done": False,
    "repo_path": None,
    "clusters": None,
    "error": None,
}


def _reset_state():
    pipeline_state.update({
        "step1_done": False,
        "step2_done": False,
        "step3_done": False,
        "step4_done": False,
        "repo_path": None,
        "clusters": None,
        "error": None,
    })


# Check for pre-existing artifacts on startup
if CLUSTERS_JSON.exists():
    try:
        with open(CLUSTERS_JSON, encoding="utf-8") as f:
            pipeline_state["clusters"] = json.load(f)
        pipeline_state["step1_done"] = True
        pipeline_state["step2_done"] = True
        pipeline_state["step3_done"] = True
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ScanRequest(BaseModel):
    repo_path: str


class GenerateRequest(BaseModel):
    cluster_name: str
    repo_path: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status")
def get_status():
    """Return the current pipeline state."""
    return {
        "step1_done": pipeline_state["step1_done"],
        "step2_done": pipeline_state["step2_done"],
        "step3_done": pipeline_state["step3_done"],
        "step4_done": pipeline_state["step4_done"],
        "repo_path":  pipeline_state["repo_path"],
        "has_clusters": pipeline_state["clusters"] is not None,
        "error": pipeline_state["error"],
    }


@app.post("/api/scan")
def scan_repo(req: ScanRequest):
    """Step 1: Scan a repo and generate edges.csv + nodes.csv."""
    try:
        pipeline_state["error"] = None
        repo = req.repo_path

        if not Path(repo).exists():
            raise HTTPException(status_code=400, detail=f"Repo path not found: {repo}")

        functions = step1_scan(repo)
        pipeline_state["step1_done"] = True
        pipeline_state["repo_path"] = repo

        edges_count = sum(len(fn.calls) for fn in functions)
        return {
            "status": "ok",
            "functions": len(functions),
            "edges": edges_count,
            "repo_path": repo,
        }
    except HTTPException:
        raise
    except Exception as e:
        pipeline_state["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cluster")
def run_clustering():
    """Steps 2-3: Load graph into Neo4j and run Louvain community detection."""
    if not pipeline_state["step1_done"]:
        raise HTTPException(
            status_code=400,
            detail="Step 1 (scan) must be completed first."
        )

    try:
        pipeline_state["error"] = None
        step2_load_graph()
        pipeline_state["step2_done"] = True

        clusters = step3_cluster()
        clusters = dedup_service_names(clusters)
        pipeline_state["step3_done"] = True
        pipeline_state["clusters"] = clusters

        summary = {
            name: {
                "suggested_service": data["suggested_service"],
                "size": data["size"],
                "community_id": data["community_id"],
            }
            for name, data in clusters.items()
        }

        return {
            "status": "ok",
            "cluster_count": len(clusters),
            "clusters": summary,
        }
    except Exception as e:
        pipeline_state["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clusters")
def get_clusters():
    """Return the current clusters.json contents."""
    if not CLUSTERS_JSON.exists():
        raise HTTPException(status_code=404, detail="clusters.json not found. Run clustering first.")

    try:
        with open(CLUSTERS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        validate_clusters(data)
        return data
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid clusters.json: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate")
def generate_service(req: GenerateRequest):
    """Step 4: Generate a microservice for a single cluster."""
    if not pipeline_state["step3_done"] and pipeline_state["clusters"] is None:
        raise HTTPException(
            status_code=400,
            detail="Clustering must be completed first."
        )

    clusters = pipeline_state["clusters"]
    if clusters is None:
        # Try loading from disk
        if CLUSTERS_JSON.exists():
            with open(CLUSTERS_JSON, encoding="utf-8") as f:
                clusters = json.load(f)
        else:
            raise HTTPException(status_code=404, detail="No clusters available.")

    if req.cluster_name not in clusters:
        raise HTTPException(
            status_code=404,
            detail=f"Cluster '{req.cluster_name}' not found. "
                   f"Available: {list(clusters.keys())}"
        )

    try:
        pipeline_state["error"] = None
        filtered = {req.cluster_name: clusters[req.cluster_name]}
        step4_generate(req.repo_path, filtered, force=False)

        service_name = clusters[req.cluster_name]["suggested_service"]
        dir_name = f"{req.cluster_name}_{service_name}"
        service_dir = SERVICES_DIR / dir_name

        generated_files = []
        if service_dir.exists():
            generated_files = [
                f.name for f in service_dir.iterdir()
                if f.is_file() and f.name != "_checkpoint.json"
            ]

        return {
            "status": "ok",
            "cluster": req.cluster_name,
            "service_name": service_name,
            "dir": dir_name,
            "files": generated_files,
        }
    except Exception as e:
        pipeline_state["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/services")
def list_services():
    """Step 5: List all generated microservices."""
    if not SERVICES_DIR.exists():
        return {"services": []}

    services = []
    for d in sorted(SERVICES_DIR.iterdir()):
        if d.is_dir():
            files = [f.name for f in d.iterdir() if f.is_file() and f.name != "_checkpoint.json"]
            checkpoint = d / "_checkpoint.json"
            meta = None
            if checkpoint.exists():
                try:
                    meta = json.loads(checkpoint.read_text(encoding="utf-8"))
                except Exception:
                    pass

            services.append({
                "name": d.name,
                "files": files,
                "checkpoint": meta,
            })

    pipeline_state["step4_done"] = len(services) > 0
    return {"services": services}


@app.post("/api/reset")
def reset_pipeline():
    """Reset the pipeline state (does not delete generated files)."""
    _reset_state()
    return {"status": "ok", "message": "Pipeline state reset."}
