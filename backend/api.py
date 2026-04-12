"""
FastAPI Backend for the Legacy Refactoring Agent
=================================================
Wraps the pipeline_runner steps as HTTP endpoints for the React frontend.
 
Start with:
    cd backend
    uvicorn api:app --reload --port 8000
"""
 
import csv
import json
import os
import sys
import traceback
from pathlib import Path
from typing import List
 
import importlib
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
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
 
# Load .env before importing pipeline modules
_env_path = Path(__file__).resolve().parent.parent / ".env"
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
    description="API layer for the monolith to microservices pipeline",
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
# Helpers
# ---------------------------------------------------------------------------
 
STALE_ARTIFACTS = ["edges.csv", "nodes.csv", "clusters.json", "graph.json"]
 
 
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
 
 
class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    context: str = ""
 
 
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
 
 
@app.post("/api/ingest/")
async def ingest_files(request: Request):
    """Ingest uploaded files: save to a temp dir, scan with AST, return results."""
    try:
        pipeline_state["error"] = None
 
        # Parse multipart form with raised limits (Starlette default is 1000)
        form = await request.form(max_files=10000, max_fields=1000)
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
 
    return {"nodes": nodes, "edges": edges}
 
 
@app.post("/api/chat/")
@app.post("/api/chat")
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
        "that has been decomposed into microservice clusters via Louvain community detection. "
        "Answer concisely. If cluster data is available, reference it specifically. "
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