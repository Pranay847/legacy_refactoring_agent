"""
models.py — Pydantic Models for the Legacy Refactoring Agent
=============================================================
Single source of truth for every request, response, and internal
data structure used across the pipeline.

Import map
──────────────────────────────────────────────────────────────────
api.py              → ScanRequest, GenerateRequest
                      StatusResponse, ScanResponse, ClusterSummary,
                      ClusterResponse, GenerateResponse,
                      ServiceEntry, ServicesResponse, ResetResponse

pipeline_runner.py  → (use any model freely)

generate_services.py → ClusterMember, Cluster, ClustersFile
                       GeneratedFiles

ingester.py         → FunctionNodeModel   (Pydantic mirror of the dataclass)

validators.py       → ValidationResult
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ════════════════════════════════════════════════════════════════════════════
# INGESTER — mirrors ingester.FunctionNode dataclass
# ════════════════════════════════════════════════════════════════════════════

class FunctionNodeModel(BaseModel):
    """Pydantic mirror of ingester.FunctionNode (used for JSON serialisation)."""
    module:    str  = Field(..., description="Dotted module path, e.g. 'app.billing.views'")
    name:      str  = Field(..., description="Function name, possibly nested: 'MyClass.my_method'")
    qualified: str  = Field(..., description="module + '.' + name")
    lineno:    int  = Field(..., ge=1)
    calls:     list[str] = Field(default_factory=list, description="Raw callee strings found in the function body")

    @property
    def call_count(self) -> int:
        return len(self.calls)


class ScanSummary(BaseModel):
    """Summary stats returned after a repo scan (Step 1)."""
    functions_found: int = Field(..., ge=0)
    edges_found:     int = Field(..., ge=0)
    modules_scanned: int = Field(..., ge=0)
    avg_calls_per_fn: float = Field(..., ge=0)
    top_callers: list[str] = Field(default_factory=list, description="Top 10 qualified names by outgoing call count")


# ════════════════════════════════════════════════════════════════════════════
# LOAD GRAPH — cluster data structures written to clusters.json
# ════════════════════════════════════════════════════════════════════════════

class ClusterMember(BaseModel):
    """One function inside a detected community. Matches load_graph.read_clusters() output."""
    function: str = Field(..., description="Function name (qualified within its module)")
    module:   str = Field(..., description="Dotted module path")

    @property
    def qualified(self) -> str:
        return f"{self.module}.{self.function}"


class Cluster(BaseModel):
    """
    One entry in clusters.json.
    Matches load_graph.format_clusters() output exactly:
        {
          "suggested_service": "billing",
          "community_id": 3,
          "size": 12,
          "members": [{"function": "...", "module": "..."}]
        }
    """
    suggested_service: str           = Field(..., description="Dominant top-level module name used as service label")
    community_id:      int           = Field(..., description="Raw Louvain communityId from Neo4j")
    size:              int           = Field(..., ge=1)
    members:           list[ClusterMember]

    @field_validator("members")
    @classmethod
    def members_not_empty(cls, v: list[ClusterMember]) -> list[ClusterMember]:
        if not v:
            raise ValueError("A cluster must have at least one member function.")
        return v

    @model_validator(mode="after")
    def size_matches_members(self) -> "Cluster":
        if self.size != len(self.members):
            # Allow size to be a hint rather than a hard constraint
            self.size = len(self.members)
        return self


class ClustersFile(BaseModel):
    """
    The full clusters.json file, keyed by 'cluster_N'.
    Used by validators.validate_clusters() and generate_services.load_clusters().
    """
    clusters: dict[str, Cluster]

    @field_validator("clusters")
    @classmethod
    def keys_must_be_cluster_prefixed(cls, v: dict[str, Cluster]) -> dict[str, Cluster]:
        bad = [k for k in v if not k.startswith("cluster_")]
        if bad:
            raise ValueError(f"Cluster keys must start with 'cluster_', got: {bad}")
        return v

    @classmethod
    def from_file(cls, path: str) -> "ClustersFile":
        import json
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls(clusters={k: Cluster(**v) for k, v in raw.items()})


# ════════════════════════════════════════════════════════════════════════════
# GENERATE SERVICES — AI generation output
# ════════════════════════════════════════════════════════════════════════════

class GeneratedFiles(BaseModel):
    """
    The files written to disk for one generated microservice.
    Matches the ### headers parse_generated_files() looks for.
    """
    main_py:          str = Field(..., alias="main.py")
    logic_py:         str = Field(..., alias="logic.py")
    requirements_txt: str = Field(..., alias="requirements.txt")
    dockerfile:       str = Field(..., alias="Dockerfile")

    model_config = {"populate_by_name": True}


class ServiceCheckpoint(BaseModel):
    """Written to _checkpoint.json inside each service folder. Tracks generation metadata."""
    cluster_name:    str
    service_name:    str
    generated_at:    str   = Field(..., description="ISO-8601 timestamp")
    model_used:      str   = Field(default="claude-sonnet-4-5")
    functions_count: int
    files_written:   list[str]


# ════════════════════════════════════════════════════════════════════════════
# API — request models  (currently in api.py, consolidated here)
# ════════════════════════════════════════════════════════════════════════════

class ScanRequest(BaseModel):
    """POST /api/scan"""
    repo_path: str = Field(..., description="Absolute or relative path to the monolith repo root")

    @field_validator("repo_path")
    @classmethod
    def path_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("repo_path cannot be empty.")
        return v.strip()


class GenerateRequest(BaseModel):
    """POST /api/generate"""
    cluster_name: str = Field(..., description="e.g. 'cluster_0'")
    repo_path:    str = Field(..., description="Path to the monolith repo (needed to extract source)")

    @field_validator("cluster_name")
    @classmethod
    def must_be_cluster_key(cls, v: str) -> str:
        if not v.startswith("cluster_"):
            raise ValueError(f"cluster_name must start with 'cluster_', got '{v}'")
        return v


# ════════════════════════════════════════════════════════════════════════════
# API — response models
# ════════════════════════════════════════════════════════════════════════════

class StatusResponse(BaseModel):
    """GET /api/status"""
    step1_done:   bool
    step2_done:   bool
    step3_done:   bool
    step4_done:   bool
    repo_path:    Optional[str]   = None
    has_clusters: bool            = False
    error:        Optional[str]   = None


class ScanResponse(BaseModel):
    """POST /api/scan → success body"""
    status:    str = "ok"
    functions: int = Field(..., ge=0, description="Number of function definitions found")
    edges:     int = Field(..., ge=0, description="Total call edges extracted")
    repo_path: str


class ClusterSummary(BaseModel):
    """Condensed cluster info returned in /api/cluster response (no members list)."""
    suggested_service: str
    size:              int
    community_id:      int


class ClusterResponse(BaseModel):
    """POST /api/cluster → success body"""
    status:        str = "ok"
    cluster_count: int
    clusters:      dict[str, ClusterSummary]


class GenerateResponse(BaseModel):
    """POST /api/generate → success body"""
    status:       str = "ok"
    cluster:      str
    service_name: str
    dir:          str  = Field(..., description="Folder name inside SERVICES_DIR")
    files:        list[str] = Field(default_factory=list, description="Generated filenames")


class ServiceEntry(BaseModel):
    """One item in the /api/services list."""
    name:       str                           = Field(..., description="Service directory name")
    files:      list[str]                     = Field(default_factory=list)
    checkpoint: Optional[ServiceCheckpoint]  = None


class ServicesResponse(BaseModel):
    """GET /api/services"""
    services: list[ServiceEntry]


class ResetResponse(BaseModel):
    """POST /api/reset"""
    status:  str = "ok"
    message: str = "Pipeline state reset."


class ErrorResponse(BaseModel):
    """Returned by any endpoint on 4xx / 5xx."""
    detail: str


# ════════════════════════════════════════════════════════════════════════════
# SHADOW TESTER — Step 5 (implemented in main.py)
# ════════════════════════════════════════════════════════════════════════════

class ShadowTestRequest(BaseModel):
    """Input to the shadow tester."""
    payload:          dict[str, Any] = Field(..., description="JSON body fired at both endpoints")
    monolith_url:     str
    microservice_url: str
    service_label:    str = "service"


class ShadowTestResult(BaseModel):
    """One row written to shadow_test_log.jsonl."""
    timestamp:    str
    service:      str
    payload:      dict[str, Any]
    monolith:     Optional[Any]   = None
    microservice: Optional[Any]   = None
    monolith_err: Optional[str]   = None
    micro_err:    Optional[str]   = None
    match:        bool


# ════════════════════════════════════════════════════════════════════════════
# VALIDATORS — result shape
# ════════════════════════════════════════════════════════════════════════════

class ValidationResult(BaseModel):
    """Returned by validators.validate_clusters() when called programmatically."""
    valid:    bool
    errors:   list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(valid=True)

    @classmethod
    def fail(cls, errors: list[str], warnings: list[str] | None = None) -> "ValidationResult":
        return cls(valid=False, errors=errors, warnings=warnings or [])
