import os
import ast
import re
import json
import argparse
import textwrap
import time
from pathlib import Path
import anthropic

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("API_KEY")
MODEL             = "claude-sonnet-4-5"
FAST_MODEL        = "claude-haiku-4-5"
SMALL_CLUSTER_THRESHOLD = 6  # clusters at or below this many functions use FAST_MODEL
MAX_TOKENS        = 8192   # higher cap: services now carry real models, not stubs

# --- Provider selection -----------------------------------------------------
# LLM_PROVIDER = "anthropic" (default, paid API) or "ollama" (local, free).
# When "ollama", the Anthropic model arg is ignored and OLLAMA_MODEL is used.
LLM_PROVIDER    = (os.getenv("LLM_PROVIDER") or "anthropic").strip().lower()
OLLAMA_BASE_URL = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL") or "qwen2.5-coder:7b"


def model_for_cluster_size(size: int) -> str:
    if LLM_PROVIDER == "ollama":
        return OLLAMA_MODEL
    return FAST_MODEL if size <= SMALL_CLUSTER_THRESHOLD else MODEL

#Load clusters
def load_clusters(clusters_path: str) -> dict:
    with open(clusters_path, encoding="utf-8") as f:
        return json.load(f)


def dedup_service_names(clusters: dict) -> dict:
    """
    Detect duplicate 'suggested_service' values across clusters and
    disambiguate them by appending _2, _3, etc.

    Example:
        cluster_0 -> "utils", cluster_1 -> "utils", cluster_8 -> "utils"
        becomes:
        cluster_0 -> "utils", cluster_1 -> "utils_2", cluster_8 -> "utils_3"
    """
    seen: dict[str, int] = {}  # service_name -> count of occurrences so far
    updated = dict(clusters)   # shallow copy so we don't mutate input

    for cluster_key in sorted(updated.keys()):
        cluster = updated[cluster_key]
        name = cluster["suggested_service"]

        if name in seen:
            seen[name] += 1
            new_name = f"{name}_{seen[name]}"
            print(f"  [WARN] Service name collision: '{name}' already used - "
                  f"renaming {cluster_key} to '{new_name}'")
            cluster["suggested_service"] = new_name
        else:
            seen[name] = 1

    return updated

#Extract source code via AST (Python) or regex (other languages)
def get_function_source_python(source: str, func_name: str) -> str | None:
    try:
        tree  = ast.parse(source)
    except SyntaxError:
        return None
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


def get_function_source_generic(source: str, func_name: str) -> str | None:
    """Extract a function by finding its definition and matching braces."""
    pattern = re.compile(
        r"^[^\n]*?\b" + re.escape(func_name) + r"\s*\(", re.MULTILINE
    )
    match = pattern.search(source)
    if not match:
        return None

    start_pos = match.start()
    brace_pos = source.find("{", match.end())
    if brace_pos != -1:
        depth = 0
        i = brace_pos
        while i < len(source):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    return source[start_pos:i + 1]
            i += 1

    # Fallback: grab 50 lines from definition
    lines = source.splitlines(keepends=True)
    start_line = source[:start_pos].count("\n")
    end_line = min(start_line + 50, len(lines))
    return "".join(lines[start_line:end_line])


ALL_EXTENSIONS = [
    ".py", ".js", ".jsx", ".mjs", ".ts", ".tsx",
    ".java", ".go", ".rs", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",
    ".cs", ".rb", ".php", ".kt", ".kts", ".swift", ".scala", ".dart", ".lua",
    ".r", ".R",
]


def resolve_module_file(repo_root: Path, module: str) -> Path | None:
    """Locate the source file for a dotted module name under a repo root."""
    module_parts = module.split(".")
    candidates: list[Path] = []

    for ext in ALL_EXTENSIONS:
        dotted = Path(*module_parts).with_suffix(ext)
        candidates.extend([
            repo_root / dotted,
            repo_root / "src" / dotted,
        ])
        if len(module_parts) > 1:
            short = Path(*module_parts[1:]).with_suffix(ext)
            candidates.extend([
                repo_root / short,
                repo_root / "src" / short,
            ])
        candidates.append(repo_root / f"{module_parts[-1]}{ext}")

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate

    # Last resort: shallowest file match by module basename (e.g. test_api.py).
    for ext in ALL_EXTENSIONS:
        matches = sorted(
            repo_root.rglob(f"{module_parts[-1]}{ext}"),
            key=lambda path: len(path.parts),
        )
        if matches:
            return matches[0]

    return None


def collect_source_for_cluster(cluster: dict, repo_root: str) -> dict[str, str]:
    root      = Path(repo_root)
    collected = {}

    for member in cluster["members"]:
        qualified = member["function"]
        module    = member["module"]

        source_file = resolve_module_file(root, module)

        if not source_file:
            print(f"  [WARN] Could not find file for module '{module}' - skipping")
            continue

        source    = source_file.read_text(encoding="utf-8", errors="replace")
        func_name = qualified[len(module) + 1:]

        if source_file.suffix == ".py":
            code = get_function_source_python(source, func_name)
        else:
            code = get_function_source_generic(source, func_name)

        if code:
            collected[qualified] = code
        else:
            print(f"  [WARN] Could not extract '{qualified}' - skipping")

    return collected

# ---------------------------------------------------------------------------
# Dependency-closure context
# ---------------------------------------------------------------------------
# A cluster contains only FUNCTIONS, so the supporting definitions a function
# leans on (imports, data models, DB sessions, helper globals) are never
# extracted — which is why the model otherwise invents mocks for them. The
# closure below walks each member function's AST, resolves the module-level
# names it references, and returns their real source so the model can reproduce
# them faithfully instead of stubbing. Python-only (uses the AST).

MAX_CONTEXT_CHARS = 12000  # cap supporting context so a huge graph can't blow up the prompt


def _free_names(node: ast.AST) -> set:
    """Every bare identifier referenced anywhere inside an AST node."""
    names = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            names.add(n.id)
        elif isinstance(n, ast.Attribute):
            cur = n
            while isinstance(cur, ast.Attribute):
                cur = cur.value
            if isinstance(cur, ast.Name):
                names.add(cur.id)
    return names


def _module_closure(member_nodes, tree, source, member_names):
    """Resolve the module-level defs/imports the member functions depend on.

    Returns (import_srcs, def_srcs): original source snippets, transitively
    closed within this module (a model that uses Base pulls Base; a session
    built from `engine` pulls `engine`; etc.).
    """
    imports = []   # (bound_names:set, src:str)
    defs = {}      # name -> ast node (class / function / assignment)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            bound = {(a.asname or a.name).split(".")[0] for a in node.names}
            imports.append((bound, ast.get_source_segment(source, node) or ""))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs[node.name] = node
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defs[t.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defs[node.target.id] = node

    work = set()
    for fn in member_nodes:
        work |= _free_names(fn)

    needed = set()
    included = []          # ast nodes, in discovery order
    seen_names = set()
    while work:
        name = work.pop()
        if name in seen_names:
            continue
        seen_names.add(name)
        needed.add(name)
        node = defs.get(name)
        if node is not None and name not in member_names:
            included.append(node)
            work |= _free_names(node)   # transitive closure

    import_srcs = [src for bound, src in imports if src and (bound & needed)]

    def_srcs, seen_ids = [], set()
    for node in sorted(included, key=lambda n: getattr(n, "lineno", 0)):
        if id(node) in seen_ids:
            continue
        seen_ids.add(id(node))
        seg = ast.get_source_segment(source, node)
        if seg:
            def_srcs.append(seg)
    return import_srcs, def_srcs


def gather_dependency_context(cluster: dict, repo_root: str) -> str:
    """Collect the real supporting definitions the cluster's functions rely on.

    Python-only; non-Python modules contribute no extra context (the regex
    scanner has no symbol table to resolve against).
    """
    root = Path(repo_root)

    members_by_module: dict[str, list[str]] = {}
    for member in cluster["members"]:
        module = member["module"]
        short  = member["function"][len(module) + 1:]
        members_by_module.setdefault(module, []).append(short)

    all_imports, all_defs = [], []
    seen = set()

    for module, member_names in members_by_module.items():
        source_file = resolve_module_file(root, module)
        if not source_file or source_file.suffix != ".py":
            continue
        try:
            source = source_file.read_text(encoding="utf-8", errors="replace")
            tree   = ast.parse(source)
        except SyntaxError:
            continue

        member_set   = set(member_names)
        member_nodes = [
            n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in member_set
        ]
        if not member_nodes:
            continue

        import_srcs, def_srcs = _module_closure(member_nodes, tree, source, member_set)
        for src in import_srcs:
            key = src.strip()
            if key and key not in seen:
                seen.add(key); all_imports.append(src)
        for src in def_srcs:
            key = src.strip()[:120]
            if key and key not in seen:
                seen.add(key); all_defs.append(src)

    parts = []
    if all_imports:
        parts.append("\n".join(all_imports))
    parts.extend(all_defs)
    context = "\n\n".join(parts).strip()

    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n# … (supporting context truncated)"
    return context


#Build the prompt
def build_prompt(cluster_name: str, service_name: str, sources: dict[str, str],
                 context: str = "") -> str:
    functions_block = "\n\n".join(
        f"# --- {name} ---\n{code}"
        for name, code in sources.items()
    )

    rules = textwrap.dedent(f"""
        You are an expert software architect specializing in migrating legacy
        monoliths to microservices.

        Below is the source code for the '{service_name}' module extracted from a
        legacy monolith. Rewrite this into a standalone FastAPI microservice.

        You MUST follow these rules:
        1. Create a complete main.py with a FastAPI app and one POST endpoint per function.
        2. Create Pydantic request/response models for every endpoint payload.
        3. Create logic.py containing the original functions with core logic EXACTLY as-is.
        4. Reproduce the SUPPORTING DEFINITIONS (imports, data models, DB sessions,
           helpers) faithfully in logic.py — do NOT replace them with mocks, stubs,
           or placeholder implementations.
        5. Create requirements.txt with fastapi, uvicorn, and any other needed packages.
        6. Create a Dockerfile that runs the service on port 8000.
        7. Return ONLY file contents separated by headers exactly like this:
           ### main.py
           ### logic.py
           ### requirements.txt
           ### Dockerfile
    """).strip()

    parts = [rules, "FUNCTIONS TO EXPOSE AS ENDPOINTS:\n\n" + functions_block]
    if context:
        parts.append(
            "SUPPORTING DEFINITIONS the functions above depend on — these come from "
            "the original codebase; reproduce them faithfully, do NOT mock them:\n\n"
            + context
        )
    return "\n\n".join(parts).strip()

#Call the LLM — Anthropic API by default, or a local Ollama model when LLM_PROVIDER=ollama
def call_claude(prompt: str, model: str = MODEL) -> str:
    if LLM_PROVIDER == "ollama":
        return _call_ollama(prompt)

    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to your .env file and restart the terminal."
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"  Sending to Claude API ({model})...", end="", flush=True)
    message = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    print(" done.")
    return message.content[0].text


def _call_ollama(prompt: str) -> str:
    """Generate with a local Ollama model (free). Uses Ollama's native /api/chat."""
    import httpx

    print(f"  Sending to Ollama ({OLLAMA_MODEL})...", end="", flush=True)
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                # Ollama defaults num_predict to 128, which would truncate the files.
                "options": {"num_predict": MAX_TOKENS},
            },
            timeout=600.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Ollama request failed: {exc}. Is the Ollama server running and is "
            f"model '{OLLAMA_MODEL}' pulled?  (ollama pull {OLLAMA_MODEL})"
        ) from exc
    print(" done.")
    return resp.json()["message"]["content"]

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
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("API_KEY")

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

        print(f"\n[{cluster_name}] '{service_name}' - {size} functions")

        sources = collect_source_for_cluster(cluster_data, args.repo)
        if not sources:
            print("  No source found — skipping.")
            continue

        print(f"  Extracted {len(sources)} function(s):")
        for name in sources:
            print(f"    - {name}")

        context = gather_dependency_context(cluster_data, args.repo)
        prompt = build_prompt(cluster_name, service_name, sources, context)

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
