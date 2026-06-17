import os
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()


import sys
sys.path.insert(0, str(Path(__file__).parent))

from ingester import scan_repo, write_edges_csv, write_nodes_csv
from graph_loader import (
    get_driver, wait_for_neo4j, clear_graph, load_edges,
    drop_gds_graph_if_exists, project_gds_graph, run_louvain,
    read_clusters, format_clusters,
)
from generate_services import (
    load_clusters, collect_source_for_cluster,
    build_prompt, call_claude, parse_generated_files, save_service,
    model_for_cluster_size,
)
from validators import validate_clusters

BASE_DIR      = Path(__file__).resolve().parent.parent
IMPORT_DIR    = BASE_DIR / "import"
SERVICES_DIR  = BASE_DIR / "services"
EDGES_CSV     = IMPORT_DIR / "edges.csv"
NODES_CSV     = IMPORT_DIR / "nodes.csv"
CLUSTERS_JSON = IMPORT_DIR / "clusters.json"

IMPORT_DIR.mkdir(exist_ok=True)
SERVICES_DIR.mkdir(exist_ok=True)


def banner(step: int, title: str):
    print(f"\n{'='*55}")
    print(f"  STEP {step}: {title}")
    print(f"{'='*55}")


def step1_scan(repo_path: str):
    banner(1, "Scanning repo (ingester)")
    functions = scan_repo(repo_path)
    if not functions:
        raise RuntimeError("No functions found. Check repo path.")
    write_edges_csv(functions, str(EDGES_CSV))
    write_nodes_csv(functions, str(NODES_CSV))
    edges_count = sum(len(fn.calls) for fn in functions)
    print(f"  {len(functions)} functions, {edges_count} edges written.")
    return functions


def step2_load_graph():
    banner(2, "Loading graph into Neo4j")
    driver = get_driver()
    with driver.session() as session:
        wait_for_neo4j(driver, retries=5, delay=2)
        clear_graph(session)
        load_edges(session, str(EDGES_CSV))
    driver.close()
    print("  Graph loaded.")


def step3_cluster():
    banner(3, "Running Louvain community detection")
    driver = get_driver()
    with driver.session() as session:
        drop_gds_graph_if_exists(session)
        project_gds_graph(session)
        run_louvain(session)
        raw_clusters = read_clusters(session)
    driver.close()
    clusters = format_clusters(raw_clusters)
    with open(CLUSTERS_JSON, "w", encoding="utf-8") as f:
        json.dump(clusters, f, indent=2)
    validate_clusters(clusters)
    print(f"  {len(clusters)} clusters detected -> {CLUSTERS_JSON}")
    return clusters


def _generate_one_cluster(repo_path: str, cluster_name: str, cluster_data: dict, force: bool = False) -> dict:
    service_name = cluster_data["suggested_service"]
    dir_name     = f"{cluster_name}_{service_name}"
    service_dir  = SERVICES_DIR / dir_name
    checkpoint   = service_dir / "_checkpoint.json"

    print(f"\n  [{cluster_name}] {service_name} - {cluster_data['size']} functions")

    if not force and checkpoint.exists():
        print("    [OK] Already generated - skipping (use --force-regen to override)")
        files = [
            f.name for f in service_dir.iterdir()
            if f.is_file() and f.name != "_checkpoint.json"
        ]
        return {
            "status": "skipped",
            "cluster": cluster_name,
            "service_name": service_name,
            "dir": dir_name,
            "files": files,
        }

    sources = collect_source_for_cluster(cluster_data, repo_path)
    if not sources:
        print("    No source extracted - skipping.")
        return {
            "status": "skipped",
            "cluster": cluster_name,
            "service_name": service_name,
            "dir": dir_name,
            "files": [],
            "error": "No source extracted.",
        }

    model    = model_for_cluster_size(cluster_data["size"])
    prompt   = build_prompt(cluster_name, service_name, sources)
    response = call_claude(prompt, model=model)
    files    = parse_generated_files(response)

    if not files:
        print("    Could not parse response - skipping.")
        return {
            "status": "error",
            "cluster": cluster_name,
            "service_name": service_name,
            "dir": dir_name,
            "files": [],
            "error": "Could not parse model response.",
        }

    save_service(dir_name, files, str(SERVICES_DIR))
    checkpoint_data = {
        "cluster_name": cluster_name,
        "service_name": service_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "files": list(files.keys()),
    }
    checkpoint.write_text(
        json.dumps(checkpoint_data, indent=2), encoding="utf-8"
    )
    return {
        "status": "generated",
        "cluster": cluster_name,
        "service_name": service_name,
        "dir": dir_name,
        "files": list(files.keys()),
    }


def step4_generate(repo_path: str, clusters: dict, force: bool = False, max_workers: int = 1) -> list[dict]:
    banner(4, "Generating microservices via Claude API")
    workers = max(1, min(max_workers, len(clusters) or 1))
    results: list[dict] = []

    if workers == 1:
        for cluster_name, cluster_data in clusters.items():
            results.append(_generate_one_cluster(repo_path, cluster_name, cluster_data, force))
    else:
        print(f"  Running up to {workers} generations in parallel.")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_generate_one_cluster, repo_path, cluster_name, cluster_data, force): cluster_name
                for cluster_name, cluster_data in clusters.items()
            }
            for future in as_completed(futures):
                cluster_name = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    cluster_data = clusters[cluster_name]
                    results.append({
                        "status": "error",
                        "cluster": cluster_name,
                        "service_name": cluster_data["suggested_service"],
                        "dir": f"{cluster_name}_{cluster_data['suggested_service']}",
                        "files": [],
                        "error": str(exc),
                    })

    generated = sum(1 for result in results if result["status"] == "generated")
    skipped = sum(1 for result in results if result["status"] == "skipped")
    failed = sum(1 for result in results if result["status"] == "error")
    print(f"\n  Summary: {generated} generated, {skipped} skipped, {failed} failed (checkpointed)")
    return results


def step5_summary():
    banner(5, "Summary")
    if not SERVICES_DIR.exists():
        print("  No services generated yet.")
        return
    services = [d for d in SERVICES_DIR.iterdir() if d.is_dir()]
    print(f"  {len(services)} microservices generated:")
    for s in services:
        files = [f.name for f in s.iterdir() if f.is_file()]
        print(f"    - {s.name}: {', '.join(files)}")


def main():
    parser = argparse.ArgumentParser(description="Legacy Refactoring Agent - Full Pipeline")
    parser.add_argument("--repo",        required=True, help="Path to the monolith repo")
    parser.add_argument("--skip-scan",   action="store_true", help="Skip Step 1 (use existing edges.csv)")
    parser.add_argument("--skip-neo4j",  action="store_true", help="Skip Steps 2-3 (use existing clusters.json)")
    parser.add_argument("--only",        help="Only generate one cluster (e.g. cluster_0)")
    parser.add_argument("--force-regen", action="store_true", help="Re-generate services even if checkpointed")
    args = parser.parse_args()

    print("\nLegacy Refactoring Agent - Full Pipeline")
    print(f"   Repo: {args.repo}\n")

    # Step 1
    if not args.skip_scan:
        step1_scan(args.repo)
    else:
        print("Skipping Step 1 (--skip-scan)")

    # Steps 2-3
    if not args.skip_neo4j:
        step2_load_graph()
        clusters = step3_cluster()
    else:
        print("Skipping Steps 2-3 (--skip-neo4j)")
        if not CLUSTERS_JSON.exists():
            raise RuntimeError("clusters.json not found. Run without --skip-neo4j first.")
        with open(CLUSTERS_JSON) as f:
            clusters = json.load(f)
        validate_clusters(clusters)

    # Step 4 - filter if --only specified
    if args.only:
        clusters = {k: v for k, v in clusters.items() if k == args.only}
        if not clusters:
            print(f"Cluster '{args.only}' not found.")
            return

    step4_generate(args.repo, clusters, force=args.force_regen)
    step5_summary()

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
