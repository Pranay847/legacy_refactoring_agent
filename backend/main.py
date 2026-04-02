"""
main.py — Legacy Refactoring Agent · Pipeline Orchestrator
============================================================
Wires the pranay-branch backend modules together in order:

  Step 1  →  ingester.py
              scan_repo(repo_root)        → list[FunctionNode]
              write_edges_csv(fns, path)  → edges.csv
              write_nodes_csv(fns, path)  → nodes.csv

  Step 2  →  load_graph.py
              Imports edges.csv + nodes.csv into Neo4j, runs Louvain,
              writes clusters.json  {cluster_N: {suggested_service, size, members}}

  Step 3/4 → generate_services.py
              load_clusters(clusters_path) → dict
              dedup_service_names(clusters)
              collect_source_for_cluster(cluster, repo_root)
              build_prompt / call_claude / parse_generated_files / save_service

  Step 5  →  api.py
              shadow_test(payload, monolith_url, microservice_url) → dict

  Any step →  validators.py
              validate_edges(path) / validate_services(path)

Usage
-----
  python main.py --repo ./my_monolith                    # full pipeline
  python main.py --repo ./my_monolith --step 1           # AST ingest only
  python main.py --step 2 --output-dir ./output          # Neo4j + Louvain only
  python main.py --repo ./my_monolith --step 34          # AI generation only
  python main.py --step 34 --only cluster_0              # one cluster only
  python main.py --step 5  --service payment_service --payload '{"amount":99}'

Environment / .env
------------------
  ANTHROPIC_API_KEY   sk-ant-...
  NEO4J_URI           bolt://localhost:7687
  NEO4J_USER          neo4j
  NEO4J_PASS          password
  MONOLITH_URL        http://localhost:5000
  MICROSERVICE_URL    http://localhost:8000
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path

# ── Load .env (same logic used in generate_services.py) ─────────────────────
def _load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


# ── Safe local import ────────────────────────────────────────────────────────
def _import(module_name: str):
    import importlib
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        log.error("Cannot import '%s': %s", module_name, exc)
        log.error("Run this script from the backend/ directory.")
        sys.exit(1)


# ════════════════════════════════════════════════════════════════════════════
# STEP 1 — AST ingest  →  edges.csv + nodes.csv
# Uses: ingester.scan_repo(), write_edges_csv(), write_nodes_csv()
# ════════════════════════════════════════════════════════════════════════════

def run_step1(repo_dir: str, output_dir: str, emit_json: bool = False) -> tuple[str, str]:
    """
    Returns (edges_csv_path, nodes_csv_path).

    ingester.py public surface used:
        scan_repo(repo_root: str)                          -> list[FunctionNode]
        write_edges_csv(functions, output_path: str)
        write_nodes_csv(functions, output_path: str)
        write_graph_json(functions, output_path: str)      # optional
        print_summary(functions)
    """
    log.info("━" * 60)
    log.info("STEP 1 ▶ Scanning repo: %s", repo_dir)

    if not Path(repo_dir).exists():
        log.error("Repo not found: %s", repo_dir)
        sys.exit(1)

    ingester = _import("ingester")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    edges_path = str(out / "edges.csv")
    nodes_path = str(out / "nodes.csv")
    json_path  = str(out / "graph.json")

    functions = ingester.scan_repo(repo_dir)

    ingester.write_edges_csv(functions, edges_path)
    ingester.write_nodes_csv(functions, nodes_path)

    if emit_json:
        ingester.write_graph_json(functions, json_path)
        log.info("STEP 1   graph.json → %s", json_path)

    ingester.print_summary(functions)

    log.info("STEP 1 ✓  edges → %s", edges_path)
    log.info("STEP 1 ✓  nodes → %s", nodes_path)

    return edges_path, nodes_path


# ════════════════════════════════════════════════════════════════════════════
# STEP 2 — Neo4j import + Louvain  →  clusters.json
# Uses: load_graph (your load_graph.py)
# ════════════════════════════════════════════════════════════════════════════

def run_step2(edges_path: str, nodes_path: str, output_dir: str) -> str:
    """
    Loads edges.csv + nodes.csv into Neo4j, runs the Louvain GDS algorithm,
    and writes clusters.json.

    Returns the path to clusters.json.

    Expected load_graph.py surface (adapt if yours differs):
        load_graph.load_and_cluster(
            edges_csv:  str,
            nodes_csv:  str,
            output_dir: str,
        ) -> str   # path to clusters.json
    """
    log.info("━" * 60)
    log.info("STEP 2 ▶ Loading into Neo4j + running Louvain")

    for p in (edges_path, nodes_path):
        if not Path(p).exists():
            log.error("Required file missing: %s — run Step 1 first.", p)
            sys.exit(1)

    load_graph = _import("load_graph")

    clusters_path = None

    # Support common function name variants
    if hasattr(load_graph, "load_and_cluster"):
        clusters_path = load_graph.load_and_cluster(edges_path, nodes_path, output_dir)
    elif hasattr(load_graph, "run"):
        clusters_path = load_graph.run(edges_path, nodes_path, output_dir)
    elif hasattr(load_graph, "main"):
        # Fall back to calling main() with patched argv if no clean API
        import sys as _sys
        _sys.argv = ["load_graph.py",
                     "--edges", edges_path,
                     "--nodes", nodes_path,
                     "--output", output_dir]
        load_graph.main()
        clusters_path = str(Path(output_dir) / "clusters.json")
    else:
        log.error("load_graph.py needs a 'load_and_cluster' or 'run' function.")
        sys.exit(1)

    if not clusters_path or not Path(clusters_path).exists():
        log.error("clusters.json was not produced. Check load_graph.py output.")
        sys.exit(1)

    # Print a quick summary
    with open(clusters_path) as f:
        clusters = json.load(f)
    log.info("STEP 2 ✓  %d clusters detected → %s", len(clusters), clusters_path)
    for key, data in sorted(clusters.items()):
        log.info("   %-12s  %-30s  %d functions",
                 key, data.get("suggested_service", "?"), data.get("size", 0))

    return clusters_path


# ════════════════════════════════════════════════════════════════════════════
# STEP 3 + 4 — Extract source + call Claude  →  /services/<cluster>_<name>/
# Uses: generate_services.*  (exact functions from generate_services.py)
# ════════════════════════════════════════════════════════════════════════════

def run_step34(
    clusters_path: str,
    repo_dir:      str,
    output_dir:    str,
    only:          str | None = None,
) -> list[str]:
    """
    For each cluster in clusters.json:
      1. Collect source code for every member function  (Step 3)
      2. Build a strict prompt and call Claude           (Step 4)
      3. Parse the response and write service files

    Uses directly from generate_services.py:
        load_clusters(clusters_path)
        dedup_service_names(clusters)
        collect_source_for_cluster(cluster, repo_root)
        build_prompt(cluster_name, service_name, sources)
        call_claude(prompt)
        parse_generated_files(response)
        save_service(service_dir_name, files, output_dir)
    """
    log.info("━" * 60)
    log.info("STEP 3/4 ▶ Generating microservices")
    log.info("  clusters : %s", clusters_path)
    log.info("  repo     : %s", repo_dir)
    log.info("  output   : %s", output_dir)
    if only:
        log.info("  filter   : %s only", only)

    if not Path(clusters_path).exists():
        log.error("clusters.json not found at '%s' — run Step 2 first.", clusters_path)
        sys.exit(1)

    gs = _import("generate_services")

    clusters = gs.load_clusters(clusters_path)
    clusters = gs.dedup_service_names(clusters)
    total    = len(clusters)

    log.info("  Found %d cluster(s) in %s", total, clusters_path)

    generated_dirs: list[str] = []

    for cluster_name, cluster_data in clusters.items():
        if only and cluster_name != only:
            continue

        service_name = cluster_data["suggested_service"]
        size         = cluster_data["size"]
        log.info("  [%s] '%s' — %d functions", cluster_name, service_name, size)

        # Step 3 — extract source
        sources = gs.collect_source_for_cluster(cluster_data, repo_dir)
        if not sources:
            log.warning("  No source extracted for %s — skipping.", cluster_name)
            continue
        log.info("  Extracted %d function(s): %s",
                 len(sources), ", ".join(list(sources.keys())[:5]))

        # Step 4 — call Claude
        prompt = gs.build_prompt(cluster_name, service_name, sources)
        try:
            response = gs.call_claude(prompt)
        except Exception as exc:
            log.error("  Claude call failed for %s: %s", cluster_name, exc)
            continue

        # Parse + save
        files = gs.parse_generated_files(response)
        if not files:
            raw_path = Path(output_dir) / f"{cluster_name}_raw.txt"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(response, encoding="utf-8")
            log.warning("  No files parsed; raw response → %s", raw_path)
            continue

        service_dir_name = f"{cluster_name}_{service_name}"
        gs.save_service(service_dir_name, files, output_dir)
        generated_dirs.append(str(Path(output_dir) / service_dir_name))

        if total > 1:
            time.sleep(1)   # avoid Claude rate-limiting

    log.info("STEP 3/4 ✓  Generated %d service(s)", len(generated_dirs))
    return generated_dirs


# ════════════════════════════════════════════════════════════════════════════
# STEP 5 — Shadow testing: dual-fire + output comparison
# Uses: api.shadow_test()
# ════════════════════════════════════════════════════════════════════════════

def run_step5(
    service_name:     str,
    payload:          dict,
    monolith_url:     str | None = None,
    microservice_url: str | None = None,
) -> bool:
    """
    Fires the same payload at both the monolith and the new microservice,
    compares their outputs, and appends the result to shadow_test_log.jsonl.

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
        log.error("api.py needs a 'shadow_test(payload, monolith_url, microservice_url)' function.")
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
    entry = {
        "timestamp":    time.strftime("%Y-%m-%dT%H:%M:%S"),
        "service":      service_name,
        "payload":      payload,
        "monolith":     monolith_val,
        "microservice": microservice_val,
        "match":        match,
    }
    with open("shadow_test_log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
    log.info("  Result appended → shadow_test_log.jsonl")

    return match


# ════════════════════════════════════════════════════════════════════════════
# VALIDATION — delegates to validators.py
# ════════════════════════════════════════════════════════════════════════════

def run_validation(edges_path: str | None, output_dir: str | None) -> list:
    log.info("━" * 60)
    log.info("VALIDATE ▶ Running validators")

    validators = _import("validators")
    errors: list[str] = []

    if edges_path and Path(edges_path).exists():
        if hasattr(validators, "validate_edges"):
            errs = validators.validate_edges(edges_path)
            errors.extend(errs)
            msg = f"✓ edges.csv clean" if not errs else f"✗ {len(errs)} issue(s): {errs}"
            log.info("  %s", msg)

    if output_dir and Path(output_dir).exists():
        if hasattr(validators, "validate_services"):
            errs = validators.validate_services(output_dir)
            errors.extend(errs)
            msg = f"✓ services clean" if not errs else f"✗ {len(errs)} issue(s): {errs}"
            log.info("  %s", msg)

    log.info("VALIDATE %s", "✓ All good" if not errors else f"✗ {len(errors)} total issue(s)")
    return errors


# ════════════════════════════════════════════════════════════════════════════
# FULL PIPELINE
# ════════════════════════════════════════════════════════════════════════════

def run_full_pipeline(args: argparse.Namespace):
    t0 = time.time()

    log.info("=" * 60)
    log.info("  Legacy Refactoring Agent — Full Pipeline")
    log.info("  repo   : %s", args.repo)
    log.info("  output : %s", args.output_dir)
    log.info("=" * 60)

    # Step 1 — ingest
    edges_path, nodes_path = run_step1(
        repo_dir=args.repo,
        output_dir=args.output_dir,
        emit_json=args.json,
    )

    # Step 2 — graph + Louvain
    clusters_path = run_step2(
        edges_path=edges_path,
        nodes_path=nodes_path,
        output_dir=args.output_dir,
    )

    # Step 3/4 — AI generation
    services_dir = str(Path(args.output_dir) / "services")
    generated = run_step34(
        clusters_path=clusters_path,
        repo_dir=args.repo,
        output_dir=services_dir,
        only=args.only,
    )

    # Step 5 — shadow test each generated service
    if args.payload:
        payload    = json.loads(args.payload)
        all_passed = True
        for service_path in generated:
            passed = run_step5(
                service_name=Path(service_path).name,
                payload=payload,
                monolith_url=args.monolith_url,
                microservice_url=args.microservice_url,
            )
            all_passed = all_passed and passed
        if not all_passed:
            log.error("One or more shadow tests FAILED — see shadow_test_log.jsonl")

    if args.validate:
        run_validation(edges_path, services_dir)

    log.info("=" * 60)
    log.info("  Pipeline complete in %.1fs", time.time() - t0)
    log.info("  Artifacts    → %s", args.output_dir)
    log.info("  Services     → %s", services_dir)
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

    # ── shared ────────────────────────────────────────────────────────────
    p.add_argument("--repo",       default=".",
                   help="Monolith repo path (Step 1 + 3/4)")
    p.add_argument("--output-dir", default="./output",
                   help="Root folder for all generated artifacts (default: ./output)")
    p.add_argument("--step",       default="all",
                   choices=["1", "2", "34", "5", "all"],
                   help="Which step to run (default: all)")
    p.add_argument("--log-level",  default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    # ── step 1 ────────────────────────────────────────────────────────────
    p.add_argument("--json", action="store_true",
                   help="Also emit graph.json in Step 1")

    # ── step 2 ────────────────────────────────────────────────────────────
    p.add_argument("--edges", default=None,
                   help="Path to edges.csv (overrides default output-dir location)")
    p.add_argument("--nodes", default=None,
                   help="Path to nodes.csv (overrides default output-dir location)")

    # ── step 3/4 ──────────────────────────────────────────────────────────
    p.add_argument("--clusters", default=None,
                   help="Path to clusters.json (overrides default output-dir location)")
    p.add_argument("--only", default=None,
                   help="Only generate this cluster, e.g. --only cluster_0")

    # ── step 5 ────────────────────────────────────────────────────────────
    p.add_argument("--service",          default=None,
                   help="Service name label for shadow test logging")
    p.add_argument("--payload",          default=None,
                   help='JSON payload for shadow testing, e.g. \'{"amount": 100}\'')
    p.add_argument("--monolith-url",     default=None,
                   help="Monolith base URL (overrides MONOLITH_URL env)")
    p.add_argument("--microservice-url", default=None,
                   help="Microservice base URL (overrides MICROSERVICE_URL env)")

    # ── validation ────────────────────────────────────────────────────────
    p.add_argument("--validate", action="store_true",
                   help="Run validators.py after selected step(s)")

    return p


def main():
    parser = build_parser()
    args   = parser.parse_args()
    logging.getLogger().setLevel(args.log_level)

    out        = Path(args.output_dir)
    edges_path = args.edges    or str(out / "edges.csv")
    nodes_path = args.nodes    or str(out / "nodes.csv")
    clusters_path = args.clusters or str(out / "clusters.json")
    services_dir  = str(out / "services")

    step = args.step

    if step == "1":
        run_step1(args.repo, args.output_dir, emit_json=args.json)

    elif step == "2":
        run_step2(edges_path, nodes_path, args.output_dir)

    elif step == "34":
        run_step34(clusters_path, args.repo, services_dir, only=args.only)

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

    # Standalone validate (skip if already run inside full pipeline)
    if args.validate and step != "all":
        run_validation(edges_path, services_dir)


if __name__ == "__main__":
    main()
