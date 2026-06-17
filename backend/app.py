"""
FastAPI Backend for the Legacy Refactoring Agent
=================================================
Wraps the pipeline_runner steps as HTTP endpoints for the React frontend.
 
Start with:
    cd backend
    uvicorn app:app --reload --port 8000
"""
 
import csv
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path
from typing import List
 
import importlib
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
 
anthropic = None
try:
    anthropic = importlib.import_module("anthropic")
except ImportError:
    anthropic = None
 
# ---------------------------------------------------------------------------
# Ensure extractor modules are importable
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
 
# Central configuration loads the repo-root .env into the environment on import
# (this runs after the sys.path setup above so `config` resolves in all launch modes).
from config import settings
 
from pipeline_runner import (
    step1_scan, step2_load_graph, step3_cluster,
    step4_generate, step5_summary,
    IMPORT_DIR, SERVICES_DIR, EDGES_CSV, NODES_CSV, CLUSTERS_JSON,
)
from validators import validate_clusters
from generate_services import dedup_service_names

# Auth + billing + rate limiting (all gated: no-ops until their keys are configured).
from auth import install_auth, get_principal, Principal
from billing import (
    PLANS,
    meter,
    create_checkout_session,
    create_portal_session,
    construct_event,
    handle_event,
)
from ratelimit import rate_limit
from cache import cache_get, cache_set
from jobs import enqueue_generate_all, get_job
import db
 
# ---------------------------------------------------------------------------
# App & CORS
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Legacy Refactoring Agent API",
    version="1.0.0",
    description="API layer for the monolith to microservices pipeline",
)

# Register auth BEFORE CORS so CORS stays the outermost middleware and 401
# responses still carry CORS headers (otherwise the browser hides the error).
install_auth(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
 
 
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
 
STALE_ARTIFACTS = ["edges.csv", "nodes.csv", "clusters.json", "graph.json"]
MAX_UPLOAD_PART_SIZE = 50 * 1024 * 1024
CLUSTER_META = IMPORT_DIR / "clusters.meta.json"


def _artifact_signature() -> dict:
    signature = {}
    for artifact in (EDGES_CSV, NODES_CSV):
        if artifact.exists():
            stat = artifact.stat()
            signature[artifact.name] = {
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
            }
    return signature


def _sig_for(*paths) -> str:
    """Stable cache fingerprint from file mtime/size (changes when inputs change)."""
    parts = []
    for p in paths:
        if p.exists():
            st = p.stat()
            parts.append(f"{p.name}:{st.st_mtime_ns}:{st.st_size}")
        else:
            parts.append(f"{p.name}:missing")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def _load_cached_clusters() -> dict | None:
    if not CLUSTERS_JSON.exists() or not CLUSTER_META.exists():
        return None

    try:
        meta = json.loads(CLUSTER_META.read_text(encoding="utf-8"))
        if meta.get("artifact_signature") != _artifact_signature():
            return None

        with open(CLUSTERS_JSON, encoding="utf-8") as f:
            clusters = json.load(f)
        validate_clusters(clusters)
        return dedup_service_names(clusters)
    except Exception:
        return None


def _write_cluster_meta():
    CLUSTER_META.write_text(
        json.dumps({"artifact_signature": _artifact_signature()}, indent=2),
        encoding="utf-8",
    )
 
 
def _clear_stale_artifacts():
    """Remove leftover pipeline artifacts so a new scan starts clean."""
    for filename in STALE_ARTIFACTS:
        artifact = IMPORT_DIR / filename
        if artifact.exists():
            artifact.unlink()
 
 
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
 
 
class GenerateAllRequest(BaseModel):
    repo_path: str
    cluster_names: list[str] | None = None
    max_workers: int | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    context: str = ""


class CheckoutRequest(BaseModel):
    plan: str
 
 
# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
 
@app.get("/api/status")
def get_status():
    """Return the current pipeline state plus which integrations are enabled."""
    return {
        "step1_done": pipeline_state["step1_done"],
        "step2_done": pipeline_state["step2_done"],
        "step3_done": pipeline_state["step3_done"],
        "step4_done": pipeline_state["step4_done"],
        "repo_path":  pipeline_state["repo_path"],
        "has_clusters": pipeline_state["clusters"] is not None,
        "error": pipeline_state["error"],
        # Feature flags only (no secret values) so the frontend can adapt its UI.
        "integrations": {
            "auth": settings.auth_enabled,
            "billing": settings.billing_enabled,
            "supabase": settings.supabase_enabled,
            "async_jobs": settings.redis_enabled,
        },
    }
 
 
@app.post("/api/scan", dependencies=[rate_limit("scan"), meter("scan")])
def scan_repo(req: ScanRequest):
    """Step 1: Scan a repo and generate edges.csv + nodes.csv."""
    try:
        pipeline_state["error"] = None
        repo = req.repo_path
 
        if not Path(repo).exists():
            raise HTTPException(status_code=400, detail=f"Repo path not found: {repo}")
 
        # --- FIX: Clear stale artifacts before scanning a new repo ---
        _clear_stale_artifacts()
        _reset_state()
 
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
 
 
@app.post("/api/ingest/", dependencies=[rate_limit("scan"), meter("scan")])
async def ingest_files(request: Request):
    """Ingest uploaded files: save to a temp dir, scan with AST, return results."""
    try:
        pipeline_state["error"] = None
 
        # Parse multipart form with raised limits. Starlette's default
        # max_part_size is 1 MB, which rejects common source repo files.
        form = await request.form(
            max_files=10000,
            max_fields=1000,
            max_part_size=MAX_UPLOAD_PART_SIZE,
        )
        session_id = form["session_id"]
        project_name = form.get("project_name", "") or ""
        files = form.getlist("files")

        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded.")

        # --- FIX: Clear stale artifacts so chat doesn't use old data ---
        _clear_stale_artifacts()
        _reset_state()
 
        # Use project name as directory (sanitized), fall back to session_id
        safe_name = "".join(
            c if (c.isalnum() or c in "._- ") else "_"
            for c in project_name
        ).strip() or session_id
        upload_dir = IMPORT_DIR / "uploads" / safe_name
        upload_dir.mkdir(parents=True, exist_ok=True)
 
        saved_files = []
        for f in files:
            rel_path = f.filename or f.filename
            dest = upload_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = await f.read()
            dest.write_bytes(content)
            saved_files.append(rel_path)
 
        # Run the scanner on the uploaded directory
        functions = step1_scan(str(upload_dir))
        pipeline_state["step1_done"] = True
        pipeline_state["repo_path"] = str(upload_dir)
 
        # Build per-file results for the frontend
        file_results = []
        modules_seen: dict[str, list] = {}
        for fn in functions:
            modules_seen.setdefault(fn.module, []).append(fn)
 
        for module, fns in modules_seen.items():
            file_results.append({
                "file": module,
                "chunks": len(fns),
                "summary": f"{len(fns)} functions: {', '.join(f.name for f in fns[:5])}"
                           + (" ..." if len(fns) > 5 else ""),
            })
 
        # Include any uploaded files that had no functions
        seen_modules = set(modules_seen.keys())
        for sf in saved_files:
            if sf.endswith(".py"):
                module_guess = sf.replace("/", ".").replace("\\", ".").removesuffix(".py")
                if module_guess not in seen_modules:
                    file_results.append({
                        "file": sf,
                        "chunks": 0,
                        "summary": "No functions found",
                    })

        # Clean up form resources
        await form.close()

        return {
            "files": file_results,
            "repo_path": str(upload_dir),
            "functions": len(functions),
            "edges": sum(len(fn.calls) for fn in functions),
        }
    except HTTPException:
        raise
    except Exception as e:
        pipeline_state["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/api/cluster", dependencies=[rate_limit("cluster"), meter("cluster")])
def run_clustering():
    """Steps 2-3: Load graph into Neo4j and run Louvain community detection."""
    if not pipeline_state["step1_done"]:
        raise HTTPException(
            status_code=400,
            detail="Step 1 (scan) must be completed first."
        )
 
    try:
        pipeline_state["error"] = None
        cached_clusters = _load_cached_clusters()
        if cached_clusters:
            pipeline_state["step2_done"] = True
            pipeline_state["step3_done"] = True
            pipeline_state["clusters"] = cached_clusters

            summary = {
                name: {
                    "suggested_service": data["suggested_service"],
                    "size": data["size"],
                    "community_id": data["community_id"],
                }
                for name, data in cached_clusters.items()
            }

            return {
                "status": "ok",
                "cached": True,
                "cluster_count": len(cached_clusters),
                "clusters": summary,
            }

        step2_load_graph()
        pipeline_state["step2_done"] = True
 
        clusters = step3_cluster()
        clusters = dedup_service_names(clusters)
        _write_cluster_meta()
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
            "cached": False,
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

    cache_key = "clusters:" + _sig_for(CLUSTERS_JSON)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        with open(CLUSTERS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        validate_clusters(data)
        cache_set(cache_key, data)
        return data
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid clusters.json: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/api/generate", dependencies=[rate_limit("generate"), meter("generate")])
def generate_service(req: GenerateRequest):
    """Step 4: Generate a microservice for a single cluster."""
    if not pipeline_state["step3_done"] and pipeline_state["clusters"] is None:
        raise HTTPException(
            status_code=400,
            detail="Clustering must be completed first."
        )
 
    clusters = pipeline_state["clusters"]
    if clusters is None:
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
        results = step4_generate(req.repo_path, filtered, force=False)
        result = results[0] if results else {}
 
        return {
            "status": "ok",
            "generation_status": result.get("status", "unknown"),
            "cluster": result.get("cluster", req.cluster_name),
            "service_name": result.get("service_name", clusters[req.cluster_name]["suggested_service"]),
            "dir": result.get("dir", f"{req.cluster_name}_{clusters[req.cluster_name]['suggested_service']}"),
            "files": result.get("files", []),
        }
    except Exception as e:
        pipeline_state["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-all", dependencies=[rate_limit("generate_all"), meter("generate_all")])
def generate_all_services(req: GenerateAllRequest):
    """Step 4: Generate multiple microservices with bounded parallelism."""
    if not pipeline_state["step3_done"] and pipeline_state["clusters"] is None:
        raise HTTPException(
            status_code=400,
            detail="Clustering must be completed first."
        )

    clusters = pipeline_state["clusters"]
    if clusters is None:
        if CLUSTERS_JSON.exists():
            with open(CLUSTERS_JSON, encoding="utf-8") as f:
                clusters = json.load(f)
        else:
            raise HTTPException(status_code=404, detail="No clusters available.")

    selected_names = req.cluster_names or list(clusters.keys())
    missing = [name for name in selected_names if name not in clusters]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Clusters not found: {missing}"
        )

    hard_cap = int(os.environ.get("GENERATION_MAX_WORKERS", "10"))
    max_workers = req.max_workers or int(os.environ.get("GENERATION_WORKERS", "5"))
    max_workers = max(1, min(max_workers, hard_cap, len(selected_names) or 1))
    filtered = {name: clusters[name] for name in selected_names}

    try:
        pipeline_state["error"] = None
        results = step4_generate(req.repo_path, filtered, force=False, max_workers=max_workers)
        pipeline_state["step4_done"] = any(
            result["status"] in {"generated", "skipped"} for result in results
        )

        return {
            "status": "ok",
            "max_workers": max_workers,
            "total": len(results),
            "generated": sum(1 for result in results if result["status"] == "generated"),
            "skipped": sum(1 for result in results if result["status"] == "skipped"),
            "failed": sum(1 for result in results if result["status"] == "error"),
            "services": results,
        }
    except Exception as e:
        pipeline_state["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-all/async", dependencies=[rate_limit("generate_all"), meter("generate_all")])
async def generate_all_async(req: GenerateAllRequest):
    """Queue batch generation as a background job (requires Redis); poll /api/jobs/{id}."""
    if not settings.redis_enabled:
        raise HTTPException(
            status_code=503,
            detail="Async jobs require Redis. Use /api/generate-all instead.",
        )

    clusters = pipeline_state["clusters"]
    if clusters is None:
        if CLUSTERS_JSON.exists():
            with open(CLUSTERS_JSON, encoding="utf-8") as f:
                clusters = json.load(f)
        else:
            raise HTTPException(status_code=404, detail="No clusters available.")

    selected_names = req.cluster_names or list(clusters.keys())
    missing = [name for name in selected_names if name not in clusters]
    if missing:
        raise HTTPException(status_code=404, detail=f"Clusters not found: {missing}")

    job_id = await enqueue_generate_all(req.repo_path, selected_names, req.max_workers)
    return {"job_id": job_id, "status": "queued", "total": len(selected_names)}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    """Poll the status/result of an async job."""
    if not settings.redis_enabled:
        raise HTTPException(status_code=503, detail="Async jobs require Redis.")
    return await get_job(job_id)


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
    """Reset the pipeline state and clear stale artifacts."""
    _reset_state()
    _clear_stale_artifacts()
    return {"status": "ok", "message": "Pipeline state reset."}
 
 
@app.get("/api/graph")
def get_graph():
    """Return call graph data in Cytoscape-compatible format."""
    nodes_csv = IMPORT_DIR / "nodes.csv"
    edges_csv = IMPORT_DIR / "edges.csv"
 
    if not nodes_csv.exists() or not edges_csv.exists():
        raise HTTPException(status_code=404, detail="Graph data not found. Run scan first.")

    cache_key = "graph:" + _sig_for(nodes_csv, edges_csv, CLUSTERS_JSON)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    # Build function -> cluster mapping from clusters.json
    fn_to_cluster: dict[str, str] = {}
    fn_to_community: dict[str, int] = {}
    if CLUSTERS_JSON.exists():
        with open(CLUSTERS_JSON, encoding="utf-8") as f:
            clusters = json.load(f)
        for cluster_name, cluster_data in clusters.items():
            for member in cluster_data["members"]:
                fn_to_cluster[member["function"]] = cluster_name
                fn_to_community[member["function"]] = cluster_data["community_id"]
 
    # Build node list
    nodes = []
    with open(nodes_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn_id = row["qualified_name"]
            nodes.append({
                "data": {
                    "id": fn_id,
                    "label": row["function"],
                    "module": row["module"],
                    "lineno": int(row.get("lineno", 0)),
                    "cluster": fn_to_cluster.get(fn_id, "unknown"),
                    "communityId": fn_to_community.get(fn_id, -1),
                }
            })
 
    # Build edge list (deduplicated)
    edges = []
    seen: set[str] = set()
    with open(edges_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            src = row["caller_function"]
            tgt = row["callee_function"]
            key = f"{src}->{tgt}"
            if key not in seen:
                seen.add(key)
                edges.append({
                    "data": {"id": f"e{i}", "source": src, "target": tgt}
                })

    result = {"nodes": nodes, "edges": edges}
    cache_set(cache_key, result)
    return result
 
 
@app.post("/api/chat/", dependencies=[rate_limit("chat"), meter("chat")])
@app.post("/api/chat", dependencies=[rate_limit("chat"), meter("chat")])
def chat(req: ChatRequest):
    """Answer questions about the scanned codebase using Claude."""
    if anthropic is None:
        raise HTTPException(status_code=500, detail="The 'anthropic' package is not installed.")
 
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")
 
    # --- FIX: Build context from current pipeline state, not just files ---
    context_str = req.context or ""
 
    # Priority 1: Use clusters.json if available AND matches current scan
    if not context_str and CLUSTERS_JSON.exists() and pipeline_state["step3_done"]:
        with open(CLUSTERS_JSON, encoding="utf-8") as f:
            clusters = json.load(f)
        lines = []
        for name, data in clusters.items():
            fns = [m["function"] for m in data["members"]]
            lines.append(
                f"{name} ({data['suggested_service']}, {data['size']} functions): "
                + ", ".join(fns[:15])
                + (" ..." if len(fns) > 15 else "")
            )
        context_str = "\n".join(lines)
 
    # Priority 2: Use nodes.csv if scan was done but no clusters yet
    nodes_csv = IMPORT_DIR / "nodes.csv"
    if not context_str and nodes_csv.exists() and pipeline_state["step1_done"]:
        lines = []
        with open(nodes_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lines.append(f"{row['qualified_name']} (module: {row['module']}, line {row['lineno']}, {row['call_count']} calls)")
        if lines:
            context_str = "Scanned functions:\n" + "\n".join(lines)
 
    # --- FIX: Include the repo path so the LLM knows what project is active ---
    repo_info = ""
    if pipeline_state["repo_path"]:
        repo_info = f"\nCurrently scanned repository: {pipeline_state['repo_path']}\n"
 
    system = (
        "You are an expert software architect helping analyze a codebase "
        "that has been decomposed into microservice clusters via Louvain community detection.\n\n"
        "FORMATTING RULES:\n"
        "- Use **bold** for function names, file names, and key terms.\n"
        "- Use `inline code` for code identifiers, paths, and short snippets.\n"
        "- Use bullet lists for listing functions, files, or features.\n"
        "- Use numbered lists for step-by-step explanations.\n"
        "- Use headings (## or ###) to separate major sections in longer answers.\n"
        "- Use fenced code blocks (```python) for multi-line code.\n"
        "- Keep paragraphs short (2-3 sentences max).\n"
        "- Be concise but thorough.\n\n"
        "If cluster data is available, reference specific clusters and their functions. "
        "If only scanned function data is available, use that to answer questions about the codebase.\n\n"
        + repo_info
        + ("Cluster summary:\n" + context_str if context_str else "No codebase data available yet. The user needs to run a scan first.")
    )
 
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": req.message}],
    )
    return {"reply": response.content[0].text}
 
 
@app.get("/api/services/{name}/{file_name}")
def get_service_file(name: str, file_name: str):
    """Return the content of a file inside a generated service directory."""
    service_dir = SERVICES_DIR / name
    if not service_dir.exists():
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")
    file_path = service_dir / file_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File '{file_name}' not in service '{name}'")
    return {"content": file_path.read_text(encoding="utf-8"), "name": file_name}
 

@app.get("/api/verification")
def get_verification():
    """Return shadow tester parity results."""
    results_path = IMPORT_DIR / "verification_results.json"
    if not results_path.exists():
        return {"results": [], "summary": {"total": 0, "passed": 0, "failed": 0}}
    with open(results_path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Billing (Stripe) — gated. Endpoints degrade gracefully when unconfigured.
# ---------------------------------------------------------------------------
@app.get("/api/billing/plans")
def billing_plans():
    """Public plan catalog (labels + monthly limits) and whether billing is live."""
    return {
        "billing_enabled": settings.billing_enabled,
        "plans": {
            name: {"label": p["label"], "limits": p["limits"]}
            for name, p in PLANS.items()
        },
    }


@app.get("/api/billing/subscription")
def billing_subscription(principal: Principal = Depends(get_principal)):
    """Return the caller's plan, status, and current-month usage."""
    if not settings.supabase_enabled:
        return {
            "plan": "free",
            "status": "active",
            "usage": {},
            "limits": PLANS["free"]["limits"],
        }
    user_id = db.get_or_create_user(principal.clerk_user_id, principal.email)
    sub = db.get_subscription(user_id) or {}
    plan = db.get_user_plan(user_id)
    usage = {
        event: db.count_usage_this_month(user_id, event)
        for event in PLANS["free"]["limits"].keys()
    }
    return {
        "plan": plan,
        "status": sub.get("status", "active"),
        "current_period_end": sub.get("current_period_end"),
        "usage": usage,
        "limits": PLANS.get(plan, PLANS["free"])["limits"],
    }


@app.post("/api/billing/checkout")
def billing_checkout(
    req: CheckoutRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
):
    if not settings.billing_enabled:
        raise HTTPException(status_code=503, detail="Billing is not configured.")
    origin = request.headers.get("origin") or settings.frontend_url or ""
    url = create_checkout_session(
        req.plan,
        principal.clerk_user_id,
        principal.email,
        success_url=f"{origin}/?checkout=success",
        cancel_url=f"{origin}/?checkout=cancel",
    )
    return {"url": url}


@app.post("/api/billing/portal")
def billing_portal(
    request: Request,
    principal: Principal = Depends(get_principal),
):
    if not settings.billing_enabled:
        raise HTTPException(status_code=503, detail="Billing is not configured.")
    if not settings.supabase_enabled:
        raise HTTPException(status_code=400, detail="No customer record available.")
    user_id = db.get_or_create_user(principal.clerk_user_id, principal.email)
    sub = db.get_subscription(user_id)
    customer_id = (sub or {}).get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe customer on file yet. Start a checkout first.",
        )
    return_url = (
        settings.stripe_portal_return_url
        or request.headers.get("origin")
        or settings.frontend_url
        or ""
    )
    return {"url": create_portal_session(customer_id, return_url)}


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook receiver. Authenticated by signature, not a JWT."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    event = construct_event(payload, sig)
    handle_event(event)
    return {"received": True}
