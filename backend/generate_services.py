import os
import ast
import json
import argparse
import textwrap
import time
from pathlib import Path
import anthropic

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL             = "claude-sonnet-4-5"
MAX_TOKENS        = 4096

#Load clusters
def load_clusters(clusters_path: str) -> dict:
    with open(clusters_path, encoding="utf-8") as f:
        return json.load(f)


def dedup_service_names(clusters: dict) -> dict:
    """
    Detect duplicate 'suggested_service' values across clusters and
    disambiguate them by appending _2, _3, etc.

    Example:
        cluster_0 → "utils", cluster_1 → "utils", cluster_8 → "utils"
        becomes:
        cluster_0 → "utils", cluster_1 → "utils_2", cluster_8 → "utils_3"
    """
    seen: dict[str, int] = {}  # service_name → count of occurrences so far
    updated = dict(clusters)   # shallow copy so we don't mutate input

    for cluster_key in sorted(updated.keys()):
        cluster = updated[cluster_key]
        name = cluster["suggested_service"]

        if name in seen:
            seen[name] += 1
            new_name = f"{name}_{seen[name]}"
            print(f"  [WARN] Service name collision: '{name}' already used — "
                  f"renaming {cluster_key} to '{new_name}'")
            cluster["suggested_service"] = new_name
        else:
            seen[name] = 1

    return updated

#Extract source code via AST
def get_function_source(source: str, func_name: str) -> str | None:
    tree  = ast.parse(source)
    lines = source.splitlines(keepends=True)
    parts = func_name.split(".")

    def find_in_body(body, parts):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == parts[0]:
                    if len(parts) == 1:
                        start = node.lineno - 1
                        end   = node.end_lineno
                        return "".join(lines[start:end])
                    else:
                        return find_in_body(node.body, parts[1:])
        return None

    return find_in_body(tree.body, parts)


def collect_source_for_cluster(cluster: dict, repo_root: str) -> dict[str, str]:
    root      = Path(repo_root)
    collected = {}

    for member in cluster["members"]:
        qualified = member["function"]
        module    = member["module"]

        rel_path   = Path(*module.split(".")).with_suffix(".py")
        candidates = [root / rel_path, root / "src" / rel_path]

        source_file = next((p for p in candidates if p.exists()), None)
        if not source_file:
            print(f"  [WARN] Could not find file for module '{module}' — skipping")
            continue

        source    = source_file.read_text(encoding="utf-8", errors="replace")
        func_name = qualified[len(module) + 1:]
        code      = get_function_source(source, func_name)

        if code:
            collected[qualified] = code
        else:
            print(f"  [WARN] Could not extract '{qualified}' — skipping")

    return collected

#Build the prompt
def build_prompt(cluster_name: str, service_name: str, sources: dict[str, str]) -> str:
    functions_block = "\n\n".join(
        f"# --- {name} ---\n{code}"
        for name, code in sources.items()
    )

    return textwrap.dedent(f"""
        You are an expert software architect specializing in migrating legacy Python
        monoliths to microservices.

        Below is the source code for the '{service_name}' module extracted from a
        legacy monolith. Rewrite this into a standalone FastAPI microservice.

        You MUST follow these rules:
        1. Create a complete main.py with a FastAPI app and one POST endpoint per function.
        2. Create Pydantic request/response models for every endpoint payload.
        3. Create logic.py containing the original functions with core logic EXACTLY as-is.
        4. Create requirements.txt with fastapi, uvicorn, and any other needed packages.
        5. Create a Dockerfile that runs the service on port 8000.
        6. Return ONLY file contents separated by headers exactly like this:
           ### main.py
           ### logic.py
           ### requirements.txt
           ### Dockerfile

        Here is the extracted source code:

        {functions_block}
    """).strip()

#Call Claude API
def call_claude(prompt: str) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to your .env file and restart the terminal."
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print("  Sending to Claude API...", end="", flush=True)
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    print(" done.")
    return message.content[0].text

#Parse and save generated files
def parse_generated_files(response: str) -> dict[str, str]:
    files         = {}
    current_file  = None
    current_lines = []

    for line in response.splitlines():
        stripped = line.strip()
        if stripped.startswith("###"):
            candidate = stripped.lstrip("# ").strip()
            if any(candidate.endswith(ext) for ext in
                   [".py", ".txt", ".yml", ".yaml"]) or candidate == "Dockerfile":
                if current_file:
                    files[current_file] = "\n".join(current_lines).strip()
                current_file  = candidate
                current_lines = []
                continue
        if current_file:
            if stripped in ("```python", "```", "```dockerfile", "```txt"):
                continue
            current_lines.append(line)

    if current_file:
        files[current_file] = "\n".join(current_lines).strip()

    return files


def save_service(service_dir_name: str, files: dict[str, str], output_dir: str):
    service_dir = Path(output_dir) / service_dir_name
    service_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in files.items():
        file_path = service_dir / filename
        file_path.write_text(content, encoding="utf-8")
        print(f"    Wrote {file_path}")

    print(f"  Service saved to {service_dir}\n")

#Main pipeline
def main():
    parser = argparse.ArgumentParser(
        description="Phase 3: Generate FastAPI microservices using Claude API."
    )
    parser.add_argument("--clusters", default="../import/clusters.json")
    parser.add_argument("--repo",     required=True, help="Path to the original repo")
    parser.add_argument("--output",   default="../services")
    parser.add_argument("--only",     help="Only process this cluster (e.g. cluster_0)")
    args = parser.parse_args()

    # Load .env manually
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    global ANTHROPIC_API_KEY
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env file.")
        print("Add this line to your .env file:")
        print("  ANTHROPIC_API_KEY=sk-ant-your-key-here")
        return

    clusters = load_clusters(args.clusters)
    clusters = dedup_service_names(clusters)
    total    = len(clusters)

    print(f"\nFound {total} clusters in {args.clusters}")
    print(f"Repo:   {args.repo}")
    print(f"Output: {args.output}\n")
    print("=" * 55)

    for cluster_name, cluster_data in clusters.items():
        if args.only and cluster_name != args.only:
            continue

        service_name = cluster_data["suggested_service"]
        size         = cluster_data["size"]

        print(f"\n[{cluster_name}] '{service_name}' — {size} functions")

        sources = collect_source_for_cluster(cluster_data, args.repo)
        if not sources:
            print("  No source found — skipping.")
            continue

        print(f"  Extracted {len(sources)} function(s):")
        for name in sources:
            print(f"    • {name}")

        prompt = build_prompt(cluster_name, service_name, sources)

        try:
            response = call_claude(prompt)
        except Exception as e:
            print(f"  [ERROR] Claude call failed: {e}")
            continue

        files = parse_generated_files(response)
        if not files:
            raw_path = Path(args.output) / f"{cluster_name}_raw.txt"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(response, encoding="utf-8")
            print(f"  Raw response saved to {raw_path}")
            continue

        save_service(f"{cluster_name}_{service_name}", files, args.output)

        if total > 1:
            time.sleep(1)

    print("=" * 55)
    print("Phase 3 complete.")
    print(f"Generated services are in: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
