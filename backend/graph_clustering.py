"""
Neo4j-free Louvain clustering
=============================
Drop-in replacement for the Neo4j + Graph Data Science path in
``graph_loader.py``. Reads the same ``edges.csv`` and returns the same shape
``read_clusters()`` does, so ``format_clusters()`` consumes either identically.

Why this exists: Neo4j was used for exactly one thing — ``gds.louvain``. There
is no free managed Neo4j-with-GDS (Aura's standard tiers exclude GDS, and
Neptune has no ``gds.*``), which forces a paid host for one graph algorithm.
NetworkX ships Louvain in pure Python, so the whole database drops out and the
backend deploys anywhere.

Select with ``CLUSTERING_BACKEND=networkx`` (the default) or ``neo4j``.

Fidelity notes vs. the GDS implementation:
  * Louvain is stochastic and implementations differ, so the partition will not
    match GDS exactly — expect a similar community count over the same nodes.
    ``seed`` makes runs here reproducible.
  * ``load_edges`` MERGEs callers on ``{name, module}`` but callees on
    ``{name}`` alone, so a function that is both can become TWO Neo4j nodes —
    one real, one ``module='external'``. Here each name is a single node and
    the caller's module wins, which is the intent of the
    ``WHERE f.module <> 'external'`` filter.
"""
from __future__ import annotations

import csv
from pathlib import Path

EXTERNAL_MODULE = "external"


def build_call_graph(edges_csv_path: str | Path):
    """Build an undirected call graph plus a node -> module map.

    Mirrors ``load_edges``: ``caller_function`` holds the caller's qualified
    name and carries ``caller_module``; ``callee_function`` is the raw call
    target and is ``external`` unless it is also defined in the scanned repo.

    Returns ``(networkx.Graph, dict[str, str])``.
    """
    import networkx as nx  # imported lazily so module import stays cheap

    path = Path(edges_csv_path)
    if not path.exists():
        raise FileNotFoundError(
            f"edges.csv not found at {path}. Run the scan (step 1) first."
        )

    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    modules: dict[str, str] = {}

    # Callers are authoritative for module ownership, so resolve them first.
    # A name seen only as a callee stays external.
    for row in rows:
        modules[row["caller_function"]] = row["caller_module"]

    graph = nx.Graph()
    for row in rows:
        caller = row["caller_function"]
        callee = row["callee_function"]
        modules.setdefault(callee, EXTERNAL_MODULE)
        graph.add_edge(caller, callee)

    return graph, modules


def cluster_from_edges_csv(
    edges_csv_path: str | Path,
    seed: int = 42,
    resolution: float = 1.0,
) -> dict[int, list[dict]]:
    """Run Louvain and group internal functions by community.

    Matches ``read_clusters()``: external-only nodes are filtered out and
    members are ordered by (module, function). Communities left with no
    internal functions are dropped, exactly as the Cypher filter does.

    Returns ``{community_id: [{"function": str, "module": str}, ...]}``.
    """
    from networkx.algorithms.community import louvain_communities

    graph, modules = build_call_graph(edges_csv_path)

    print("Running Louvain community detection (networkx)...")
    communities = louvain_communities(graph, seed=seed, resolution=resolution)

    clusters: dict[int, list[dict]] = {}
    for community_id, members in enumerate(communities):
        internal = [
            {"function": name, "module": modules[name]}
            for name in members
            if modules.get(name) != EXTERNAL_MODULE
        ]
        if not internal:
            continue
        internal.sort(key=lambda m: (m["module"], m["function"]))
        clusters[community_id] = internal

    total = sum(len(v) for v in clusters.values())
    print(
        f"Louvain complete — {len(clusters)} communities "
        f"over {total} internal functions.\n"
    )
    return clusters
