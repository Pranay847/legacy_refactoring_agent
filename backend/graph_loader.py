# graph_analysis/graph_analysis.py
import csv
import logging
from neo4j import GraphDatabase

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "password"

GDS_GRAPH_NAME = "function_call_graph"

logger = logging.getLogger(__name__)


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# -----------------------------------------------------------------------------
# Graph Loading
# -----------------------------------------------------------------------------

def _clear_graph(tx):
    tx.run("MATCH (n) DETACH DELETE n")


def _create_function_node(tx, name: str):
    tx.run("MERGE (f:Function {name: $name})", name=name)


def _create_call_edge(tx, caller: str, callee: str, call_count: int):
    tx.run(
        """
        MATCH (a:Function {name: $caller})
        MATCH (b:Function {name: $callee})
        MERGE (a)-[r:CALLS]->(b)
        ON CREATE SET r.call_count = $call_count
        ON MATCH  SET r.call_count = r.call_count + $call_count
        """,
        caller=caller,
        callee=callee,
        call_count=call_count
    )


def import_edges_to_neo4j(edges_csv_path: str):
    """
    Reads edges.csv and populates Neo4j with Function nodes and CALLS edges.

    Expected CSV format:
        caller,callee,call_count
        checkout_cart,calculate_tax,12
    """
    logger.info(f"Importing edges from {edges_csv_path} into Neo4j...")

    driver = get_driver()

    try:
        with driver.session() as session:
            session.execute_write(_clear_graph)
            logger.info("Cleared existing graph")

            with open(edges_csv_path, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                raise ValueError(f"edges.csv is empty or malformed: {edges_csv_path}")

            # First pass: create all unique function nodes
            unique_functions = set()
            for row in rows:
                unique_functions.add(row["caller"])
                unique_functions.add(row["callee"])

            for fn in unique_functions:
                session.execute_write(_create_function_node, fn)

            logger.info(f"Created {len(unique_functions)} Function nodes")

            # Second pass: create all CALLS edges
            for row in rows:
                session.execute_write(
                    _create_call_edge,
                    row["caller"],
                    row["callee"],
                    int(row.get("call_count", 1))
                )

            logger.info(f"Created {len(rows)} CALLS edges")

    except FileNotFoundError:
        logger.error(f"edges.csv not found at: {edges_csv_path}")
        raise
    except Exception as e:
        logger.error(f"Failed to import edges into Neo4j: {e}")
        raise
    finally:
        driver.close()

    logger.info("Graph import complete")


# -----------------------------------------------------------------------------
# Community Detection
# -----------------------------------------------------------------------------

def _drop_projection_if_exists(session, graph_name: str):
    result = session.run(
        "CALL gds.graph.exists($name) YIELD exists",
        name=graph_name
    )
    if result.single()["exists"]:
        session.run("CALL gds.graph.drop($name)", name=graph_name)
        logger.info(f"Dropped existing GDS projection: {graph_name}")


def _project_graph(session, graph_name: str):
    session.run(
        """
        CALL gds.graph.project(
            $name,
            'Function',
            {
                CALLS: {
                    orientation: 'UNDIRECTED',
                    properties: 'call_count'
                }
            }
        )
        """,
        name=graph_name
    )
    logger.info(f"GDS in-memory projection created: {graph_name}")


def _run_louvain(session, graph_name: str):
    session.run(
        """
        CALL gds.louvain.write($name, {
            writeProperty: 'communityId',
            relationshipWeightProperty: 'call_count'
        })
        """,
        name=graph_name
    )
    logger.info("Louvain algorithm complete — communityId written to nodes")


def _fetch_communities(session) -> dict:
    result = session.run(
        """
        MATCH (f:Function)
        WHERE f.communityId IS NOT NULL
        RETURN f.name AS name, toString(f.communityId) AS community_id
        ORDER BY f.communityId
        """
    )

    clusters: dict[str, list[str]] = {}
    for record in result:
        cid = record["community_id"]
        clusters.setdefault(cid, []).append(record["name"])

    return clusters


def detect_communities() -> dict:
    """
    Full Louvain pipeline:
      1. Project the graph into GDS memory
      2. Run Louvain, write communityId back to nodes
      3. Query and return clusters as { community_id: [function_names] }
    """
    logger.info("Starting community detection (Louvain)...")

    driver = get_driver()
    clusters = {}

    try:
        with driver.session() as session:
            _drop_projection_if_exists(session, GDS_GRAPH_NAME)
            _project_graph(session, GDS_GRAPH_NAME)
            _run_louvain(session, GDS_GRAPH_NAME)
            clusters = _fetch_communities(session)

    except Exception as e:
        logger.error(f"Community detection failed: {e}")
        raise
    finally:
        driver.close()

    if not clusters:
        raise ValueError("Louvain returned no communities — check that the graph was imported correctly")

    logger.info(f"Detected {len(clusters)} communities")
    for cid, fns in clusters.items():
        logger.info(f"  Community {cid}: {len(fns)} functions")

    return clusters
