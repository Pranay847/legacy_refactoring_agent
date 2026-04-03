"""
main.py — Legacy Refactoring Agent · CLI Orchestrator
======================================================
CLI alternative to api.py (the HTTP server).
Calls the exact same pipeline steps in sequence from the command line.

Module → functions actually called
───────────────────────────────────────────────────────────────────
ingester.py         scan_repo(), write_edges_csv(), write_nodes_csv(),
                    write_graph_json(), print_summary()

load_graph.py       get_driver(), wait_for_neo4j(), clear_graph(),
                    load_edges(), drop_gds_graph_if_exists(),
                    project_gds_graph(), run_louvain(),
                    read_clusters(), format_clusters(), print_summary()

generate_services.py load_clusters(), dedup_service_names(),
                     collect_source_for_cluster(), build_prompt(),
                     call_claude(), parse_generated_files(), save_service()

validators.py       validate_clusters()

api.py              → HTTP server for React frontend (not called here)
pipeline_runner.py  → used by api.py internally (not called here)

Usage
─────
  # Full pipeline end-to-end
  python main.py --repo ./my_monolith

  # Individual steps
  python main.py --repo ./my_monolith   --step 1
  python main.py                        --step 2
  python main.py --repo ./my_monolith   --step 34
  python main.py --repo ./my_monolith   --step 34  --only cluster_0

  # With custom paths
  python main.py --repo ./my_monolith \\
                 --edges  ./output/edges.csv \\
                 --clusters ./output/clusters.json \\
                 --output  ./output/services

  # Shadow-test a generated service (Step 5)
  python main.py --step 5 \\
                 --monolith-url     http://localhost:5000/checkout \\
                 --microservice-url http://localhost:8001/checkout \\
                 --payload '{"cart_id": "abc", "user_id": 42}'

Environment / .env
──────────────────
  ANTHROPIC_API_KEY   sk-ant-...
  NEO4J_URI           bolt://localhost:7687
  NEO4J_USER          neo4j
  NEO4J_PASSWORD      password          ← matches load_graph.py variable name
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

# ── .env loader (mirrors the one in generate_services.py) ────────────────────
def _load_env():
    for candidate in [
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent / ".env",
    ]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            break

_load_env()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

# ── Safe local importer ───────────────────────────────────────────────────────
def _import(name: str):
    import importlib
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        log.error("Cannot import '%s': %s", name, exc)
        log.error("Run this script from the backend/ directory.")
        sys.exit(1)


# ════════════════════════════════════════════════════════════════════════════
# STEP 1 — AST ingest  →  edges.csv  +  nodes.csv
# ════════════════════════════════════════════════════════════════════════════

def run_step1(repo_dir: str, output_dir: str, emit_json: bool = False) -> str:
    """
    Calls ingester.py directly.

    ingester functions used (exact names from source):
        scan_repo(repo_root: str)                   → list[FunctionNode]
        write_edges_csv(functions, output_path: str)
        write_nodes_csv(functions, output_path: str)
        write_graph_json(functions, output_path: str)   # only with --json
        print_summary(functions)

    Returns: path to edges.csv
    """
    log.info("━" * 60)
    log.info("STEP 1 ▶ Scanning repo: %s", repo_dir)

    if not Path(repo_dir).exists():
        log.error("Repo path not found: %s", repo_dir)
        sys.exit(1)

    ingester = _import("ingester")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    edges_path = str(out / "edges.csv")
    nodes_path = str(out / "nodes.csv")

    # ── exact call sequence from ingester.py main() ──
    functions = ingester.scan_repo(repo_dir)
    ingester.write_edges_csv(functions, edges_path)
    ingester.write_nodes_csv(functions, nodes_path)
    if emit_json:
        ingester.write_graph_json(functions, str(out / "graph.json"))
    ingester.print_summary(functions)

    log.info("STEP 1 ✓  edges.csv → %s", edges_path)
    log.info("STEP 1 ✓  nodes.csv → %s", nodes_path)
    return edges_path


# ════════════════════════════════════════════════════════════════════════════
# STEP 2 — Neo4j import + Louvain  →  clusters.json
# ════════════════════════════════════════════════════════════════════════════

def run_step2(edges_path: str, clusters_out: str, keep: bool = False) -> str:
    """
    Calls load_graph.py functions directly in the exact order its main() does.

    load_graph functions used (exact names from source):
        get_driver()
        wait_for_neo4j(driver, retries, delay)
        clear_graph(session)                        # skipped when keep=True
        load_edges(session, csv_path: str)          # only needs edges.csv
        drop_gds_graph_if_exists(session)
        project_gds_graph(session)
        run_louvain(session)
        read_clusters(session)  → dict[int, list[dict]]
        format_clusters(raw)    → {cluster_N: {suggested_service, ...}}
        print_summary(clusters)

    Returns: path to clusters.json
    """
    log.info("━" * 60)
    log.info("STEP 2 ▶ Loading graph into Neo4j + running Louvain")

    if not Path(edges_path).exists():
        log.error("edges.csv not found at '%s' — run Step 1 first.", edges_path)
        sys.exit(1)

    lg = _import("load_graph")

    driver = lg.get_driver()
    try:
        with driver.session() as session:
            lg.wait_for_neo4j(driver)

            if not keep:
                lg.clear_graph(session)

            lg.load_edges(session, edges_path)
            lg.drop_gds_graph_if_exists(session)
            lg.project_gds_graph(session)
            lg.run_louvain(session)

            raw_clusters = lg.read_clusters(session)
    finally:
        driver.close()

    clusters = lg.format_clusters(raw_clusters)
    lg.print_summary(clusters)

    out_path = Path(clusters_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clusters, f, indent=2)

    log.info("STEP 2 ✓  %d clusters → %s", len(clusters), out_path)
    return str(out_path)


# ════════════════════════════════════════════════════════════════════════════
# STEP 3 + 4 — Extract source + call Claude  →  /services/
# ════════════════════════════════════════════════════════════════════════════

def run_step34(
    clusters_path: str,
    repo_dir:      str,
    output_dir:    str,
    only:          str | None = None,
) -> list[str]:
    """
    Mirrors generate_services.py main() exactly.

    generate_services functions used (exact names from source):
        load_clusters(clusters_path: str)             → dict
        dedup_service_names(clusters: dict)           → dict
        collect_source_for_cluster(cluster, repo_root)→ dict[str, str]
        build_prompt(cluster_name, service_name, sources) → str
        call_claude(prompt: str)                      → str
        parse_generated_files(response: str)          → dict[str, str]
        save_service(service_dir_name, files, output_dir)

    Also runs validators.validate_clusters() before generating.
    """
    log.info("━" * 60)
    log.info("STEP 3/4 ▶ Generating microservices")
    log.info("  clusters : %s", clusters_path)
    log.info("  repo     : %s", repo_dir)
    log.info("  output   : %s", output_dir)

    if not Path(clusters_path).exists():
        log.error("clusters.json not found at '%s' — run Step 2 first.", clusters_path)
        sys.exit(1)

    gs         = _import("generate_services")
    validators = _import("validators")

    # Load + validate clusters (mirrors api.py /api/clusters endpoint)
    clusters = gs.load_clusters(clusters_path)
    try:
        validators.validate_clusters(clusters)
    except ValueError as exc:
        log.error("Invalid clusters.json: %s", exc)
        sys.exit(1)

    clusters = gs.dedup_service_names(clusters)
    total    = len(clusters)
    log.info("  %d cluster(s) loaded", total)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    generated_dirs: list[str] = []

    for cluster_name, cluster_data in clusters.items():
        if only and cluster_name != only:
            continue

        service_name = cluster_data["suggested_service"]
        size         = cluster_data["size"]
        log.info("\n  [%s] '%s' — %d functions", cluster_name, service_name, size)

        # Step 3 — collect source
        sources = gs.collect_source_for_cluster(cluster_data, repo_dir)
        if not sources:
            log.warning("  No source found for %s — skipping.", cluster_name)
            continue

        log.info("  Extracted %d function(s):", len(sources))
        for name in sources:
            log.info("    • %s", name)

        # Step 4 — build prompt + call Claude
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
            raw_path.write_text(response, encoding="utf-8")
            log.warning("  No structured files parsed; raw response → %s", raw_path)
            continue

        service_dir_name = f"{cluster_name}_{service_name}"
        gs.save_service(service_dir_name, files, output_dir)
        generated_dirs.append(str(Path(output_dir) / service_dir_name))

        if total > 1:
            time.sleep(1)   # avoid Claude rate-limit

    log.info("\nSTEP 3/4 ✓  Generated %d service(s)", len(generated_dirs))
    return generated_dirs


# ════════════════════════════════════════════════════════════════════════════
# STEP 5 — Shadow testing
# (api.py is the React HTTP server; shadow testing is implemented here)
# ════════════════════════════════════════════════════════════════════════════

def run_step5(
    payload:          dict,
    monolith_url:     str,
    microservice_url: str,
    service_label:    str = "service",
) -> bool:
    """
    Fires the same JSON payload at the monolith and the new microservice,
    compares their responses, and logs the result to shadow_test_log.jsonl.

    This implements the 'Shadow Middleware' described in the project spec.
    api.py is the React frontend server — shadow testing lives here instead.
    """
    try:
        import httpx
    except ModuleNotFoundError:
        log.error("httpx not installed. Run: pip install httpx")
        sys.exit(1)

    log.info("━" * 60)
    log.info("STEP 5 ▶ Shadow test: %s", service_label)
    log.info("  Monolith     → %s", monolith_url)
    log.info("  Microservice → %s", microservice_url)
    log.info("  Payload      → %s", json.dumps(payload))

    monolith_result = microservice_result = None
    monolith_err    = microservice_err    = None

    # Fire both requests (monolith first, microservice async-style via sequential calls)
    with httpx.Client(timeout=30.0) as client:
        try:
            r = client.post(monolith_url, json=payload)
            r.raise_for_status()
            monolith_result = r.json()
        except Exception as exc:
            monolith_err = str(exc)
            log.error("  Monolith request failed: %s", exc)

        try:
            r = client.post(microservice_url, json=payload)
            r.raise_for_status()
            microservice_result = r.json()
        except Exception as exc:
            microservice_err = str(exc)
            log.error("  Microservice request failed: %s", exc)

    match = (monolith_result == microservice_result) and not monolith_err and not microservice_err

    log.info("  Monolith result     : %s", monolith_result or f"ERROR: {monolith_err}")
    log.info("  Microservice result : %s", microservice_result or f"ERROR: {microservice_err}")

    if match:
        log.info("STEP 5 ✓ PASS — outputs match")
    else:
        log.error("STEP 5 ✗ FAIL — outputs differ!")

    # Append to rolling test log
    entry = {
        "timestamp":    time.strftime("%Y-%m-%dT%H:%M:%S"),
        "service":      service_label,
        "payload":      payload,
        "monolith":     monolith_result,
        "microservice": microservice_result,
        "monolith_err": monolith_err,
        "micro_err":    microservice_err,
        "match":        match,
    }
    with open("shadow_test_log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
    log.info("  Result appended → shadow_test_log.jsonl")

    return match


# ════════════════════════════════════════════════════════════════════════════
# FULL PIPELINE
# ════════════════════════════════════════════════════════════════════════════

def run_full_pipeline(args: argparse.Namespace):
    t0 = time.time()

    log.info("=" * 60)
    log.info("  Legacy Refactoring Agent — Full Pipeline")
    log.info("  repo     : %s", args.repo)
    log.info("  output   : %s", args.output_dir)
    log.info("=" * 60)

    out           = Path(args.output_dir)
    edges_path    = str(out / "edges.csv")
    clusters_path = str(out / "clusters.json")
    services_dir  = str(out / "services")

    # 1 → ingest
    run_step1(args.repo, str(out), emit_json=args.json)

    # 2 → graph + Louvain
    run_step2(edges_path, clusters_path, keep=args.keep)

    # 3/4 → AI generation
    generated = run_step34(clusters_path, args.repo, services_dir, only=args.only)

    # 5 → shadow test (optional; needs --payload)
    if args.payload:
        monolith_url     = args.monolith_url     or os.getenv("MONOLITH_URL",     "http://localhost:5000")
        microservice_url = args.microservice_url or os.getenv("MICROSERVICE_URL", "http://localhost:8000")
        payload          = json.loads(args.payload)

        all_passed = True
        for service_path in generated:
            passed = run_step5(
                payload=payload,
                monolith_url=monolith_url,
                microservice_url=microservice_url,
                service_label=Path(service_path).name,
            )
            all_passed = all_passed and passed

        if not all_passed:
            log.error("One or more shadow tests FAILED — see shadow_test_log.jsonl")

    log.info("=" * 60)
    log.info("  Done in %.1fs", time.time() - t0)
    log.info("  Artifacts → %s", str(out))
    log.info("  Services  → %s", services_dir)
    log.info("=" * 60)


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Legacy Refactoring Agent — CLI Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # shared
    p.add_argument("--repo",       default=".",
                   help="Monolith repo path (Steps 1 & 3/4)")
    p.add_argument("--output-dir", default="./output",
                   help="Root folder for all artifacts (default: ./output)")
    p.add_argument("--step",       default="all",
                   choices=["1", "2", "34", "5", "all"],
                   help="Which step to run (default: all)")
    p.add_argument("--log-level",  default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    # step 1
    p.add_argument("--json", action="store_true",
                   help="Also emit graph.json (Step 1)")

    # step 2
    p.add_argument("--edges", default=None,
                   help="Override edges.csv path for Step 2")
    p.add_argument("--keep",  action="store_true",
                   help="Skip clearing Neo4j graph (re-run Louvain only)")

    # step 3/4
    p.add_argument("--clusters", default=None,
                   help="Override clusters.json path for Step 3/4")
    p.add_argument("--only",     default=None,
                   help="Only generate one cluster, e.g. --only cluster_0")

    # step 5
    p.add_argument("--payload",          default=None,
                   help='JSON payload string for shadow testing')
    p.add_argument("--monolith-url",     default=None,
                   help="Monolith endpoint URL (overrides MONOLITH_URL env)")
    p.add_argument("--microservice-url", default=None,
                   help="Microservice endpoint URL (overrides MICROSERVICE_URL env)")
    p.add_argument("--service",          default="service",
                   help="Label for shadow test log entry")

    return p


def main():
    parser = build_parser()
    args   = parser.parse_args()
    logging.getLogger().setLevel(args.log_level)

    out           = Path(args.output_dir)
    edges_path    = args.edges    or str(out / "edges.csv")
    clusters_path = args.clusters or str(out / "clusters.json")
    services_dir  = str(out / "services")

    step = args.step

    if step == "1":
        run_step1(args.repo, str(out), emit_json=args.json)

    elif step == "2":
        run_step2(edges_path, clusters_path, keep=args.keep)

    elif step == "34":
        run_step34(clusters_path, args.repo, services_dir, only=args.only)

    elif step == "5":
        if not args.payload:
            log.error("--payload is required for Step 5.")
            sys.exit(1)
        monolith_url     = args.monolith_url     or os.getenv("MONOLITH_URL",     "http://localhost:5000")
        microservice_url = args.microservice_url or os.getenv("MICROSERVICE_URL", "http://localhost:8000")
        run_step5(
            payload=json.loads(args.payload),
            monolith_url=monolith_url,
            microservice_url=microservice_url,
            service_label=args.service,
        )

    elif step == "all":
        run_full_pipeline(args)


if __name__ == "__main__":
    main()
