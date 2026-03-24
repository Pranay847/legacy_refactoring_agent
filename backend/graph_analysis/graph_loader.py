# graph_analysis/graph_loader.py
import csv
import logging
from neo4j import GraphDatabase

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "password"

logger = logging.getLogger(__name__)


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def clear_graph(tx):
    """Wipe the graph before a fresh import."""
    tx.run("MATCH (n) DETACH DELETE n")


def create_function_node(tx, name: str):
    tx.run(
        "MERGE (f:Function {name: $name})",
        name=name
    )


def create_call_edge(tx, caller: str, callee: str, call_count: int):
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
            # Clear existing graph for a clean run
            session.execute_write(clear_graph)
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
                session.execute_write(create_function_node, fn)

            logger.info(f"Created {len(unique_functions)} Function nodes")

            # Second pass: create all CALLS edges
            for row in rows:
                session.execute_write(
                    create_call_edge,
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
