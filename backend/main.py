"""
main.py — Legacy Refactoring Agent · Pipeline Orchestrator
============================================================
Wires together every module in the pranay-branch backend:

  Step 1   →  ingester.py           AST walk → edges.csv
  Step 2   →  load_graph.py         Neo4j import + Louvain community detection
  Step 3/4 →  generate_services.py  Context assembly + AI microservice generation
  Step 5   →  api.py                Shadow-mode dual-fire verification
  Any step →  validators.py         Output validation

Usage examples
--------------
  # Run the full pipeline against a local monolith folder
  python main.py --repo ./my_monolith

  # Run only a specific step
  python main.py --repo ./my_monolith --step 1
  python main.py --step 2 --edges edges.csv
  python main.py --step 34 --community 1
  python main.py --step 5 --service payment_service --payload '{"amount": 100}'

  # Validate outputs without re-running
  python main.py --validate --edges edges.csv --output-dir ./new_microservices

Environment variables (or .env file)
--------------------------------------
  NEO4J_URI         bolt://localhost:7687
  NEO4J_USER        neo4j
  NEO4J_PASS        password
  ANTHROPIC_API_KEY sk-ant-...
  MONOLITH_URL      http://localhost:5000
  MICROSERVICE_URL  http://localhost:8000
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path

from dotenv import load_dotenv  # pip install python-dotenv

# ── Load .env before anything else ──────────────────────────────────────────
load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


# ── Safe module importer ─────────────────────────────────────────────────────
def _import(module_name: str):
    """Import a local module by name; exit with a clear error if missing."""
    import importlib
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        log.error("Cannot import '%s': %s", module_name, exc)
        log.error("Make sure you're running from the backend/ directory.")
        sys.exit(1)


# ════════════════════════════════════════════════════════════════════════════
# STEP 1 — Ingest: AST walk → edges.csv
# Delegates to: ingester.py
# ════════════════════════════════════════════════════════════════════════════

def run_step1(repo_dir: str, edges_csv: str = "edges.csv") -> str:
    """
    Calls ingester.py to walk every .py file in repo_dir,
    extract caller → callee relationships via AST, and write edges.csv.

    Expected ingester.py surface (either works):
        ingester.extract_edges(repo_dir, output_path) -> str
        ingester.run(repo_dir, output_path)           -> str
    """
    log.info("━" * 60)
    log.info("STEP 1 ▶ Ingesting call graph from: %s", repo_dir)

    if not Path(repo_dir).exists():
        log.error("Repo directory not found: %s", repo_dir)
        sys.exit(1)

    ingester = _import("ingester")

    if hasattr(ingester, "extract_edges"):
        result = ingester.extract_edges(repo_dir, edges_csv)
    elif hasattr(ingester, "run"):
        result = ingester.run(repo_dir, edges_csv)
    else:
        log.error("ingester.py needs an 'extract_edges' or 'run' function.")
        sys.exit(1)

    out = result if isinstance(result, str) else edges_csv
    log.info("STEP 1 ✓ edges written → %s", out)
    return out


# ════════════════════════════════════════════════════════════════════════════
# STEP 2 — Graph load + Louvain community detection
# Delegates to: load_graph.py
# ════════════════════════════════════════════════════════════════════════════

def run_step2(edges_csv: str = "edges.csv") -> dict:
    """
    Calls load_graph.py to:
      1. Import edges.csv into Neo4j
      2. Run the Louvain modularity algorithm (GDS library)
      3. Return {community_id: [function_name, ...]}

    Expected load_graph.py surface (either works):
        load_graph.load_and_detect(edges_csv) -> dict[int, list[str]]
        load_graph.run(edges_csv)             -> dict[int, list[str]]
    """
    log.info("━" * 60)
    log.info("STEP 2 ▶ Loading graph into Neo4j + running Louvain")

    if not Path(edges_csv).exists():
        log.error("edges.csv not found at '%s' — run Step 1 first.", edges_csv)
        sys.exit(1)

    load_graph = _import("load_graph")

    if hasattr(load_graph, "load_and_detect"):
        communities = load_graph.load_and_detect(edges_csv)
    elif hasattr(load_graph, "run"):
        communities = load_graph.run(edges_csv)
    else:
        log.error("load_graph.py needs a 'load_and_detect' or 'run' function.")
        sys.exit(1)

    log.info("STEP 2 ✓ Detected %d communities:", len(communities))
    for cid, funcs in sorted(communities.items(), key=lambda x: -len(x[1])):
        preview = ", ".join(funcs[:5]) + (" …" if len(funcs) > 5 else "")
        log.info("   Community %d → %d functions  [%s]", cid, len(funcs), preview)

    # Cache so Steps 3/4 can reload without re-running Neo4j
    cache_path = "communities.json"
    with open(cache_path, "w") as f:
        json.dump({str(k): v for k, v in communities.items()}, f, indent=2)
    log.info("STEP 2   community map cached → %s", cache_path)

    return communities


# ════════════════════════════════════════════════════════════════════════════
# STEP 3 + 4 — Context assembly + AI microservice generation
# Delegates to: generate_services.py
# ════════════════════════════════════════════════════════════════════════════

def run_step34(
    repo_dir: str,
    communities: dict,
    community_id: int | None,
    output_dir: str = "./new_microservices",
) -> list:
    """
    For each community (or just one if --community is set):
      - Extracts the source code of every function in that cluster (Step 3)
      - Sends an assembled prompt to the LLM (Step 4)
      - Writes the generated FastAPI service files to output_dir/

    Expected generate_services.py surface:
        generate_services.generate(
            repo_dir:     str,
            functions:    list[str],
            community_id: int,
            output_dir:   str,
        ) -> str   # path to the generated service folder
    """
    log.info("━" * 60)
    log.info("STEP 3/4 ▶ Generating microservices → %s", output_dir)

    gen = _import("generate_services")

    if not hasattr(gen, "generate"):
        log.error("generate_services.py needs a 'generate' function.")
        sys.exit(1)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    targets = (
        {community_id: communities[community_id]}
        if community_id is not None
        else communities
    )

    if not targets:
        log.error("No communities to generate. Run Step 2 first.")
        sys.exit(1)

    generated_paths = []
    for cid, funcs in targets.items():
        log.info("  Processing Community %d (%d functions)…", cid, len(funcs))
        try:
            service_path = gen.generate(
                repo_dir=repo_dir,
                functions=funcs,
                community_id=cid,
                output_dir=output_dir,
            )
            generated_paths.append(service_path)
            log.info("  ✓ Community %d → %s", cid, service_path)
        except Exception as exc:
            log.error("  ✗ Community %d failed: %s", cid, exc, exc_info=True)

    log.info("STEP 3/4 ✓ Generated %d service(s)", len(generated_paths))
    return generated_paths


# ════════════════════════════════════════════════════════════════════════════
# STEP 5 — Shadow testing: dual-fire + output comparison
# Delegates to: api.py
# ════════════════════════════════════════════════════════════════════════════

def run_step5(
    service_name: str,
    payload: dict,
    monolith_url: str | None = None,
    microservice_url: str | None = None,
) -> bool:
    """
    Fires the same payload at both the monolith and the generated microservice,
    compares their outputs, and logs the result to shadow_test_log.jsonl.

    Expected api.py surface:
        api.shadow_test(
            payload:          dict,
            monolith_url:     str,
            microservice_url: str,
        ) -> dict   # {"monolith": ..., "microservice": ..., "match": bool}
    """
    log.info("━" * 60)
    log.info("STEP 5 ▶ Shadow testing: %s", service_name)

    monolith_url     = monolith_url     or os.getenv("MONOLITH_URL",     "http://localhost:5000")
    microservice_url = microservice_url or os.getenv("MICROSERVICE_URL", "http://localhost:8000")

    api = _import("api")

    if not hasattr(api, "shadow_test"):
        log.error("api.py needs a 'shadow_test' function.")
        sys.exit(1)

    log.info("  Monolith     → %s", monolith_url)
    log.info("  Microservice → %s", microservice_url)
    log.info("  Payload      → %s", json.dumps(payload))

    result           = api.shadow_test(payload, monolith_url, microservice_url)
    monolith_val     = result.get("monolith")
    microservice_val = result.get("microservice")
    match            = result.get("match", monolith_val == microservice_val)

    log.info("  Monolith result     : %s", monolith_val)
    log.info("  Microservice result : %s", microservice_val)

    if match:
        log.info("STEP 5 ✓ PASS — outputs match")
    else:
        log.error("STEP 5 ✗ FAIL — outputs differ!")

    # Append to running test log
    log_entry = {
        "timestamp":    time.strftime("%Y-%m-%dT%H:%M:%S"),
        "service":      service_name,
        "payload":      payload,
        "monolith":     monolith_val,
        "microservice": microservice_val,
        "match":        match,
    }
    with open("shadow_test_log.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    log.info("  Result appended → shadow_test_log.jsonl")

    return match


# ════════════════════════════════════════════════════════════════════════════
# VALIDATION — runs validators.py against any step's output
# Delegates to: validators.py
# ════════════════════════════════════════════════════════════════════════════

def run_validation(edges_csv: str | None, output_dir: str | None) -> list:
    """
    Calls validators.py to sanity-check pipeline artifacts.

    Expected validators.py surface (any subset works):
        validators.validate_edges(path: str)    -> list[str]   # error strings
        validators.validate_services(path: str) -> list[str]
    """
    log.info("━" * 60)
    log.info("VALIDATE ▶ Running validators")

    validators = _import("validators")
    errors = []

    if edges_csv and Path(edges_csv).exists():
        if hasattr(validators, "validate_edges"):
            errs = validators.validate_edges(edges_csv)
            errors.extend(errs)
            if errs:
                log.error("  edges.csv — %d issue(s): %s", len(errs), errs)
            else:
                log.info("  ✓ edges.csv passed validation")

    if output_dir and Path(output_dir).exists():
        if hasattr(validators, "validate_services"):
            errs = validators.validate_services(output_dir)
            errors.extend(errs)
            if errs:
                log.error("  services   — %d issue(s): %s", len(errs), errs)
            else:
                log.info("  ✓ Generated services passed validation")

    status = "✓ All checks passed" if not errors else f"✗ {len(errors)} issue(s) found"
    log.info("VALIDATE %s", status)
    return errors


# ════════════════════════════════════════════════════════════════════════════
# FULL PIPELINE
# ════════════════════════════════════════════════════════════════════════════

def run_full_pipeline(args: argparse.Namespace):
    t0 = time.time()

    log.info("=" * 60)
    log.info("  Legacy Refactoring Agent — Full Pipeline")
    log.info("  Repo : %s", args.repo)
    log.info("  Out  : %s", args.output_dir)
    log.info("=" * 60)

    edges_csv   = run_step1(args.repo, args.edges)
    communities = run_step2(edges_csv)
    generated   = run_step34(args.repo, communities, args.community, args.output_dir)

    if args.payload:
        payload    = json.loads(args.payload)
        all_passed = True
        for service_path in generated:
            passed     = run_step5(
                service_name=Path(service_path).name,
                payload=payload,
                monolith_url=args.monolith_url,
                microservice_url=args.microservice_url,
            )
            all_passed = all_passed and passed

        if not all_passed:
            log.error("One or more shadow tests FAILED — see shadow_test_log.jsonl")

    if args.validate:
        run_validation(edges_csv, args.output_dir)

    log.info("=" * 60)
    log.info("  Done in %.1fs  |  services → %s", time.time() - t0, args.output_dir)
    log.info("=" * 60)


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Legacy Refactoring Agent — Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--repo",            default=".",
                   help="Monolith repo path to analyse (default: .)")
    p.add_argument("--step",            default="all",
                   choices=["1", "2", "3", "4", "34", "5", "all"],
                   help="Which step to run (default: all)")
    p.add_argument("--edges",           default="edges.csv",
                   help="Path to edges.csv (Step 1 output / Step 2 input)")
    p.add_argument("--community",       type=int, default=None,
                   help="Target a single community ID for Step 3/4")
    p.add_argument("--output-dir",      default="./new_microservices",
                   help="Root folder for generated service files")
    p.add_argument("--service",         default=None,
                   help="Service name label for Step 5 shadow test")
    p.add_argument("--payload",         default=None,
                   help="JSON string payload for shadow testing")
    p.add_argument("--monolith-url",    default=None,
                   help="Monolith base URL (overrides MONOLITH_URL env)")
    p.add_argument("--microservice-url",default=None,
                   help="Microservice base URL (overrides MICROSERVICE_URL env)")
    p.add_argument("--validate",        action="store_true",
                   help="Run validators.py after the selected step(s)")
    p.add_argument("--log-level",       default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Logging verbosity")
    return p


def main():
    parser = build_parser()
    args   = parser.parse_args()
    logging.getLogger().setLevel(args.log_level)

    step = args.step

    if step == "1":
        run_step1(args.repo, args.edges)

    elif step == "2":
        run_step2(args.edges)

    elif step in ("3", "4", "34"):
        cache = Path("communities.json")
        if not cache.exists():
            log.error("communities.json not found — run Step 2 first.")
            sys.exit(1)
        with open(cache) as f:
            raw = json.load(f)
        communities = {int(k): v for k, v in raw.items()}
        run_step34(args.repo, communities, args.community, args.output_dir)

    elif step == "5":
        if not args.payload:
            log.error("--payload is required for Step 5.")
            sys.exit(1)
        run_step5(
            service_name=args.service or "unnamed_service",
            payload=json.loads(args.payload),
            monolith_url=args.monolith_url,
            microservice_url=args.microservice_url,
        )

    elif step == "all":
        run_full_pipeline(args)

    # Standalone validate (if not already run inside full pipeline)
    if args.validate and step != "all":
        run_validation(args.edges, args.output_dir)


if __name__ == "__main__":
    main()
