import csv
import json
import os
import argparse
import time
from pathlib import Path
from neo4j import GraphDatabase

NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

GDS_GRAPH_NAME = "call_graph"

def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def wait_for_neo4j(driver, retries=10, delay=3):
    """Poll until Neo4j accepts connections."""
    print("Waiting for Neo4j to be ready...", end="", flush=True)
    for i in range(retries):
        try:
            with driver.session() as s:
                s.run("RETURN 1")
            print(" ready!\n")
            return
        except Exception:
            print(".", end="", flush=True)
            time.sleep(delay)
    raise RuntimeError("Neo4j did not become ready in time. Is Docker running?")

def clear_graph(session):
    print("Clearing existing graph data...")
    session.run("MATCH (n) DETACH DELETE n")


def load_edges(session, csv_path: str):
    """
    Read edges.csv and create (:Function)-[:CALLS]->(:Function) in Neo4j.
    Uses MERGE so re-running is safe (idempotent).
    """
    print(f"Loading edges from {csv_path}...")

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    batch_size = 500

    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        session.run(
            """
            UNWIND $rows AS row
            MERGE (caller:Function {name: row.caller_function, module: row.caller_module})
            MERGE (callee:Function {name: row.callee_function})
            ON CREATE SET callee.module = 'external'
            MERGE (caller)-[:CALLS]->(callee)
            """,
            rows=batch,
        )
        print(f"  Loaded {min(i + batch_size, total)}/{total} edges...")

    print(f"Done — {total} edges loaded.\n")

def drop_gds_graph_if_exists(session):
    result = session.run(
        "CALL gds.graph.exists($name) YIELD exists",
        name=GDS_GRAPH_NAME,
    )
    if result.single()["exists"]:
        print(f"Dropping existing GDS projection '{GDS_GRAPH_NAME}'...")
        session.run(
            "CALL gds.graph.drop($name) YIELD graphName",
            name=GDS_GRAPH_NAME,
        )


def project_gds_graph(session):
    """
    Create an in-memory GDS graph projection from the Neo4j data.
    This is required before running any GDS algorithm.
    """
    print(f"Projecting GDS graph '{GDS_GRAPH_NAME}'...")
    session.run(
        """
        CALL gds.graph.project(
        $name,
        'Function',
        'CALLS'
        )
        """,
        name=GDS_GRAPH_NAME,
    )
    print("Projection ready.\n")

def run_louvain(session):
    """
    Run Louvain Modularity community detection.
    Writes communityId back onto each Function node.
    """
    print("Running Louvain community detection...")
    session.run(
        """
        CALL gds.louvain.write(
        $name,
        { writeProperty: 'communityId' }
        )
        """,
        name=GDS_GRAPH_NAME,
    )
    print("Louvain complete — communityId written to all nodes.\n")

def read_clusters(session) -> dict:
    """
    Group Function nodes by their communityId.
    Filter out pure 'external' nodes (stdlib/third-party calls).
    """
    result = session.run(
        """
        MATCH (f:Function)
        WHERE f.module <> 'external'
        RETURN f.communityId AS community,
        f.name        AS function,
        f.module      AS module
        ORDER BY community, module, function
        """
    )

    clusters: dict[int, list[dict]] = {}
    for record in result:
        cid = record["community"]
        if cid not in clusters:
            clusters[cid] = []
        clusters[cid].append({
            "function": record["function"],
            "module":   record["module"],
        })

    return clusters


def format_clusters(raw: dict) -> dict:
    """
    Rename clusters to friendly names and add summary stats.
    Largest clusters first.
    """
    sorted_clusters = sorted(raw.items(), key=lambda x: len(x[1]), reverse=True)

    output = {}
    for i, (cid, members) in enumerate(sorted_clusters):
        # Guess a label from the most common module in the cluster
        modules = [m["module"].split(".")[0] for m in members]
        dominant = max(set(modules), key=modules.count)

        output[f"cluster_{i}"] = {
            "suggested_service": dominant,
            "community_id": cid,
            "size": len(members),
            "members": members,
        }

    return output


def print_summary(clusters: dict):
    print("=" * 55)
    print("  MICROSERVICE CLUSTER SUMMARY")
    print("=" * 55)
    for name, data in clusters.items():
        print(f"\n  {name}  →  suggested service: '{data['suggested_service']}'")
        print(f"  {data['size']} functions:")
        for m in data["members"]:
            print(f"    • {m['function']}")
    print("\n" + "=" * 55)

def main():
    parser = argparse.ArgumentParser(
        description="Phase 2: Load call graph into Neo4j and detect microservice clusters."
    )
    parser.add_argument(
        "--csv",
        default="../import/edges.csv",
        help="Path to edges.csv from Phase 1 (default: ../import/edges.csv)",
    )
    parser.add_argument(
        "--output",
        default="../import/clusters.json",
        help="Where to write clusters.json (default: ../import/clusters.json)",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Skip clearing the graph (useful if re-running Louvain only)",
    )
    args = parser.parse_args()

    if not Path(args.csv).exists():
        print(f"ERROR: edges.csv not found at {args.csv}")
        print("Run Phase 1 first:  python extract_edges.py <repo> --output-dir ../import")
        return

    driver = get_driver()

    with driver.session() as session:
        wait_for_neo4j(driver)

        if not args.keep:
            clear_graph(session)

        load_edges(session, args.csv)
        drop_gds_graph_if_exists(session)
        project_gds_graph(session)
        run_louvain(session)

        raw_clusters = read_clusters(session)

    driver.close()

    clusters = format_clusters(raw_clusters)
    print_summary(clusters)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clusters, f, indent=2)

    print(f"\nclusters.json written to {out_path}")
    print("Next step → Phase 3: extract each cluster into a FastAPI microservice.")


if __name__ == "__main__":
    main()
