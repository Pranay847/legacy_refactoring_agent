# pipeline_runner.py
import os
import logging
from ingestion.ast_parser import parse_repository, build_edges_csv
from graph_analysis.graph_loader import import_edges_to_neo4j
from graph_analysis.community_detection import detect_communities
from context_builder.extract_functions import extract_functions_source
from ai_generation.llm_generator import generate_microservice_from_prompt
from verification.shadow_tester import run_shadow_tests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def run_pipeline(repo_path: str, output_dir: str):
    """
    Orchestrator for the full monolith -> microservice pipeline
    Args:
        repo_path: Path to the monolithic Python codebase
        output_dir: Folder where outputs (CSV, clusters, microservices) will be saved
    """

    os.makedirs(output_dir, exist_ok=True)

    logging.info("Step 1: Code Extraction (AST Parser)")
    edges_csv = os.path.join(output_dir, "edges.csv")
    parse_repository(repo_path)
    build_edges_csv(repo_path, edges_csv)
    logging.info(f"Edges CSV generated at: {edges_csv}")

    logging.info("Step 2: Graph Analysis / Community Detection")
    import_edges_to_neo4j(edges_csv)
    clusters = detect_communities()
    clusters_file = os.path.join(output_dir, "clusters.json")
    # save clusters to JSON
    import json
    with open(clusters_file, "w") as f:
        json.dump(clusters, f, indent=2)
    logging.info(f"Clusters saved at: {clusters_file}")

    logging.info("Step 3: Context Assembly")
    # clusters is a dict {CommunityID: [function_names]}
    cluster_contexts = {}
    for community_id, functions in clusters.items():
        code_snippets = extract_functions_source(repo_path, functions)
        cluster_contexts[community_id] = code_snippets
    logging.info("Code context for each cluster assembled")

    logging.info("Step 4: AI Microservice Generation")
    services_dir = os.path.join(output_dir, "generated_microservices")
    os.makedirs(services_dir, exist_ok=True)
    for community_id, code_snippets in cluster_contexts.items():
        service_name = f"microservice_{community_id}"
        service_path = os.path.join(services_dir, service_name)
        os.makedirs(service_path, exist_ok=True)
        generate_microservice_from_prompt(code_snippets, service_path)
        logging.info(f"Microservice generated at: {service_path}")

    logging.info("Step 5: Shadow Testing / Verification")
    verification_results = run_shadow_tests(services_dir)
    results_file = os.path.join(output_dir, "verification_results.json")
    with open(results_file, "w") as f:
        json.dump(verification_results, f, indent=2)
    logging.info(f"Shadow testing results saved at: {results_file}")

    logging.info("Pipeline completed successfully!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run monolith → microservice pipeline")
    parser.add_argument("--repo", required=True, help="Path to monolithic Python repo")
    parser.add_argument("--output", default="./pipeline_output", help="Output folder")
    args = parser.parse_args()

    run_pipeline(args.repo, args.output)
