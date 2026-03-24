# pipeline_runner.py
import os
import json
import logging
import argparse

from ingestion.ast_parser import parse_repository, build_edges_csv
from graph_analysis.graph_loader import import_edges_to_neo4j
from graph_analysis.community_detection import detect_communities
from context_builder.extract_functions import extract_functions_source
from context_builder.context_assembler import assemble_prompt
from ai_generation.llm_generator import generate_microservice_from_prompt
from verification.shadow_tester import run_shadow_tests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def infer_service_name(community_id: str, function_names: list[str]) -> str:
    """
    Attempt to infer a meaningful service name from the cluster's function names.
    Falls back to microservice_{community_id} if no keyword matches.
    """
    keywords = {
        "payment": ["payment", "stripe", "checkout", "charge", "refund", "transaction"],
        "auth":    ["auth", "login", "logout", "token", "password", "hash", "session"],
        "user":    ["user", "profile", "account", "register", "signup"],
        "order":   ["order", "cart", "purchase", "item", "shipping"],
        "email":   ["email", "notify", "send", "mail", "message"],
    }

    fn_names_lower = " ".join(function_names).lower()
    for service, terms in keywords.items():
        if any(term in fn_names_lower for term in terms):
            return f"{service}_service"

    return f"microservice_{community_id}"


def run_pipeline(repo_path: str, output_dir: str, monolith_url: str = "http://localhost:5000"):
    """
    Orchestrator for the full monolith -> microservice pipeline.

    Args:
        repo_path:     Path to the monolithic Python codebase
        output_dir:    Folder where outputs (CSV, clusters, microservices) will be saved
        monolith_url:  URL of the running monolith for shadow testing
    """
    os.makedirs(output_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # Step 1: Code Extraction (AST Parser)
    # -------------------------------------------------------------------------
    logging.info("Step 1: Code Extraction (AST Parser)")
    edges_csv = os.path.join(output_dir, "edges.csv")

    try:
        if not os.path.exists(edges_csv):
            parsed_data = parse_repository(repo_path)
            build_edges_csv(parsed_data, edges_csv)
            logging.info(f"Edges CSV generated at: {edges_csv}")
        else:
            logging.info("edges.csv already exists — skipping ingestion")
    except Exception as e:
        logging.error(f"Step 1 failed: {e}")
        raise

    # -------------------------------------------------------------------------
    # Step 2: Graph Analysis / Community Detection
    # -------------------------------------------------------------------------
    logging.info("Step 2: Graph Analysis / Community Detection")
    clusters_file = os.path.join(output_dir, "clusters.json")

    try:
        if not os.path.exists(clusters_file):
            import_edges_to_neo4j(edges_csv)
            clusters = detect_communities()
            with open(clusters_file, "w") as f:
                json.dump(clusters, f, indent=2)
            logging.info(f"Clusters saved at: {clusters_file}")
        else:
            logging.info("clusters.json already exists — skipping graph analysis")
            with open(clusters_file, "r") as f:
                clusters = json.load(f)
    except Exception as e:
        logging.error(f"Step 2 failed: {e}")
        raise

    # -------------------------------------------------------------------------
    # Step 3: Context Assembly (Prompt Engineering)
    # -------------------------------------------------------------------------
    logging.info("Step 3: Context Assembly")
    cluster_prompts = {}

    try:
        for community_id, function_names in clusters.items():
            if not function_names:
                logging.warning(f"Community {community_id} is empty — skipping")
                continue

            service_name   = infer_service_name(community_id, function_names)
            code_snippets  = extract_functions_source(repo_path, function_names)
            prompt         = assemble_prompt(service_name, code_snippets)
            cluster_prompts[community_id] = {
                "service_name": service_name,
                "prompt":       prompt,
            }
            logging.info(f"  Assembled prompt for community {community_id} → {service_name}")
    except Exception as e:
        logging.error(f"Step 3 failed: {e}")
        raise

    logging.info("Code context assembled for all clusters")

    # -------------------------------------------------------------------------
    # Step 4: AI Microservice Generation
    # -------------------------------------------------------------------------
    logging.info("Step 4: AI Microservice Generation")
    services_dir = os.path.join(output_dir, "generated_microservices")
    os.makedirs(services_dir, exist_ok=True)

    try:
        for community_id, cluster_data in cluster_prompts.items():
            service_name = cluster_data["service_name"]
            prompt       = cluster_data["prompt"]
            service_path = os.path.join(services_dir, service_name)
            os.makedirs(service_path, exist_ok=True)

            generate_microservice_from_prompt(prompt, service_path)
            logging.info(f"  Microservice generated at: {service_path}")
    except Exception as e:
        logging.error(f"Step 4 failed: {e}")
        raise

    # -------------------------------------------------------------------------
    # Step 5: Shadow Testing / Verification
    # -------------------------------------------------------------------------
    logging.info("Step 5: Shadow Testing / Verification")

    try:
        verification_results = run_shadow_tests(services_dir, monolith_url=monolith_url)
        results_file = os.path.join(output_dir, "verification_results.json")
        with open(results_file, "w") as f:
            json.dump(verification_results, f, indent=2)
        logging.info(f"Shadow testing results saved at: {results_file}")
    except Exception as e:
        logging.error(f"Step 5 failed: {e}")
        raise

    logging.info("Pipeline completed successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run monolith → microservice pipeline")
    parser.add_argument("--repo",     required=True,                    help="Path to monolithic Python repo")
    parser.add_argument("--output",   default="./pipeline_output",      help="Output folder")
    parser.add_argument("--monolith", default="http://localhost:5000",   help="URL of the running monolith for shadow testing")
    args = parser.parse_args()

    run_pipeline(args.repo, args.output, args.monolith)
