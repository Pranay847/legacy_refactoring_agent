import ast
import os
import re
import csv
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class FunctionNode:
    module: str          # e.g. "app.billing.views"
    name: str            # e.g. "calculate_invoice"
    qualified: str       # module + "." + name
    lineno: int
    calls: list[str] = field(default_factory=list)

class CallGraphVisitor(ast.NodeVisitor):
    """
    Walks a module's AST and records every function definition
    together with the functions it calls.
    """

    def __init__(self, module_name: str):
        self.module_name = module_name
        self.functions: list[FunctionNode] = []
        self._scope_stack: list[FunctionNode] = []

    def _current_scope(self) -> Optional[FunctionNode]:
        return self._scope_stack[-1] if self._scope_stack else None

    def _resolve_call(self, node: ast.Call) -> Optional[str]:
        """
        Try to turn a Call node into a readable name.
        Handles:
        - bare calls:        foo()          -> "foo"
        - attribute calls:   obj.bar()      -> "obj.bar"
        - chained:           a.b.c()        -> "a.b.c"
        """
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            parts = []
            cur = func
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            return ".".join(reversed(parts))
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        scope = self._current_scope()
        if scope:
            qualified_name = f"{scope.name}.{node.name}"
        else:
            qualified_name = node.name

        fn = FunctionNode(
            module=self.module_name,
            name=qualified_name,
            qualified=f"{self.module_name}.{qualified_name}",
            lineno=node.lineno,
        )
        self.functions.append(fn)
        self._scope_stack.append(fn)
        self.generic_visit(node)
        self._scope_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call):
        scope = self._current_scope()
        if scope:
            callee = self._resolve_call(node)
            if callee:
                scope.calls.append(callee)
        self.generic_visit(node)

def module_name_from_path(repo_root: Path, file_path: Path) -> str:
    """Convert /repo/app/billing/views.py  ->  app.billing.views"""
    rel = file_path.relative_to(repo_root)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else file_path.stem

def scan_file(repo_root: Path, file_path: Path) -> list[FunctionNode]:
    module = module_name_from_path(repo_root, file_path)
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        print(f"  [WARN] Syntax error in {file_path}: {e}")
        return []

    visitor = CallGraphVisitor(module)
    visitor.visit(tree)
    return visitor.functions


# ---------------------------------------------------------------------------
# Multi-language support via regex-based scanning
# ---------------------------------------------------------------------------

# Map file extensions to language identifiers
EXTENSION_TO_LANG: dict[str, str] = {
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".kt": "kotlin", ".kts": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".dart": "dart",
    ".lua": "lua",
    ".r": "r", ".R": "r",
}

# Regex patterns for function definitions per language
FUNC_DEF_PATTERNS: dict[str, list[re.Pattern]] = {
    "javascript": [
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>\w+)\s*\(", re.MULTILINE),
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*(?:async\s+)?\(", re.MULTILINE),
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*(?:async\s+)?(?:\w+\s*)?\s*=>\s*", re.MULTILINE),
        re.compile(r"^\s*(?P<name>\w+)\s*\([\w\s,:.?=\[\]]*\)\s*\{", re.MULTILINE),
    ],
    "typescript": [
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>\w+)\s*[<(]", re.MULTILINE),
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*(?::\s*\w[\w<>\[\],\s|]*\s*)?=\s*(?:async\s+)?\(", re.MULTILINE),
        re.compile(r"^\s*(?:public|private|protected|static|async|\s)*\s+(?P<name>\w+)\s*\([\w\s,:.?=<>\[\]|]*\)\s*(?::\s*\w[\w<>\[\],\s|]*)?\s*\{", re.MULTILINE),
    ],
    "java": [
        re.compile(r"^\s*(?:public|private|protected|static|final|abstract|synchronized|native|\s)*\s+\w[\w<>\[\],\s]*\s+(?P<name>\w+)\s*\(", re.MULTILINE),
    ],
    "go": [
        re.compile(r"^\s*func\s+(?:\(\s*\w+\s+\*?\w+\s*\)\s+)?(?P<name>\w+)\s*\(", re.MULTILINE),
    ],
    "rust": [
        re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(?P<name>\w+)\s*[<(]", re.MULTILINE),
    ],
    "c": [
        re.compile(r"^\s*(?:static\s+)?(?:inline\s+)?(?:const\s+)?\w[\w\s\*]*\s+(?P<name>\w+)\s*\([^;]*\)\s*\{", re.MULTILINE),
    ],
    "cpp": [
        re.compile(r"^\s*(?:static\s+)?(?:inline\s+)?(?:virtual\s+)?(?:const\s+)?\w[\w\s\*:&<>]*\s+(?P<name>\w+)\s*\([^;]*\)\s*(?:const\s*)?(?:override\s*)?\{", re.MULTILINE),
    ],
    "csharp": [
        re.compile(r"^\s*(?:public|private|protected|internal|static|async|virtual|override|abstract|\s)*\s+\w[\w<>\[\],\s\?]*\s+(?P<name>\w+)\s*\(", re.MULTILINE),
    ],
    "ruby": [
        re.compile(r"^\s*def\s+(?:self\.)?(?P<name>\w+[?!]?)", re.MULTILINE),
    ],
    "php": [
        re.compile(r"^\s*(?:public|private|protected|static|\s)*\s*function\s+(?P<name>\w+)\s*\(", re.MULTILINE),
    ],
    "kotlin": [
        re.compile(r"^\s*(?:public|private|protected|internal|open|override|suspend|\s)*\s*fun\s+(?P<name>\w+)\s*[<(]", re.MULTILINE),
    ],
    "swift": [
        re.compile(r"^\s*(?:public|private|internal|open|static|class|override|\s)*\s*func\s+(?P<name>\w+)\s*[<(]", re.MULTILINE),
    ],
    "scala": [
        re.compile(r"^\s*(?:private|protected|override|\s)*\s*def\s+(?P<name>\w+)\s*[(\[]", re.MULTILINE),
    ],
    "dart": [
        re.compile(r"^\s*(?:static\s+)?(?:Future\s*<[\w<>]*>\s+)?(?:\w+\s+)?(?P<name>\w+)\s*\(", re.MULTILINE),
    ],
    "lua": [
        re.compile(r"^\s*(?:local\s+)?function\s+(?:[\w.:]*)\.?(?P<name>\w+)\s*\(", re.MULTILINE),
    ],
    "r": [
        re.compile(r"^\s*(?P<name>\w+)\s*<-\s*function\s*\(", re.MULTILINE),
    ],
}

# Generic call pattern: identifier followed by opening paren
CALL_PATTERN = re.compile(r"(?<!\w)(?P<name>\w+)\s*\(")

# Keywords to exclude from function call detection per language
LANG_KEYWORDS: dict[str, set[str]] = {
    "javascript": {"if", "else", "for", "while", "switch", "case", "return", "new", "typeof",
                   "instanceof", "delete", "void", "throw", "catch", "import", "export", "from",
                   "class", "extends", "super", "yield", "await", "try", "finally"},
    "typescript": {"if", "else", "for", "while", "switch", "case", "return", "new", "typeof",
                   "instanceof", "delete", "void", "throw", "catch", "import", "export", "from",
                   "class", "extends", "super", "yield", "await", "try", "finally", "type",
                   "interface", "enum", "namespace", "as", "keyof"},
    "java": {"if", "else", "for", "while", "switch", "case", "return", "new", "throw",
             "catch", "import", "class", "extends", "implements", "try", "finally",
             "package", "instanceof", "super", "this", "assert"},
    "go": {"if", "else", "for", "switch", "case", "return", "go", "defer", "select",
           "range", "import", "package", "type", "struct", "interface", "map", "chan"},
    "rust": {"if", "else", "for", "while", "loop", "match", "return", "use", "mod",
             "pub", "fn", "let", "mut", "impl", "struct", "enum", "trait", "type",
             "where", "async", "await", "move", "unsafe", "extern"},
    "c": {"if", "else", "for", "while", "switch", "case", "return", "sizeof",
          "typedef", "struct", "enum", "union", "goto", "break", "continue"},
    "cpp": {"if", "else", "for", "while", "switch", "case", "return", "sizeof",
            "typedef", "struct", "enum", "union", "goto", "break", "continue",
            "class", "template", "namespace", "new", "delete", "throw", "catch",
            "try", "dynamic_cast", "static_cast", "reinterpret_cast", "const_cast"},
    "csharp": {"if", "else", "for", "foreach", "while", "switch", "case", "return",
               "new", "throw", "catch", "try", "finally", "class", "struct", "enum",
               "interface", "namespace", "using", "typeof", "sizeof", "is", "as",
               "await", "async", "yield", "lock"},
    "ruby": {"if", "elsif", "else", "unless", "while", "until", "for", "do", "return",
             "class", "module", "begin", "rescue", "ensure", "raise", "yield", "require",
             "include", "extend", "attr_reader", "attr_writer", "attr_accessor"},
    "php": {"if", "else", "elseif", "for", "foreach", "while", "switch", "case", "return",
            "new", "throw", "catch", "try", "finally", "class", "interface", "trait",
            "namespace", "use", "echo", "print", "include", "require", "isset", "unset",
            "empty", "array", "list"},
    "kotlin": {"if", "else", "for", "while", "when", "return", "throw", "try", "catch",
               "finally", "class", "object", "interface", "fun", "val", "var", "import",
               "package", "is", "as", "in", "super", "this"},
    "swift": {"if", "else", "for", "while", "switch", "case", "return", "throw", "try",
              "catch", "class", "struct", "enum", "protocol", "import", "guard", "defer",
              "repeat", "break", "continue", "where", "is", "as", "super", "self"},
    "scala": {"if", "else", "for", "while", "match", "case", "return", "throw", "try",
              "catch", "finally", "class", "object", "trait", "import", "package",
              "new", "yield", "super", "this", "type", "val", "var", "def"},
    "dart": {"if", "else", "for", "while", "switch", "case", "return", "throw", "try",
             "catch", "finally", "class", "extends", "implements", "import", "new",
             "await", "async", "yield", "super", "this", "is", "as"},
    "lua": {"if", "then", "else", "elseif", "end", "for", "while", "do", "repeat",
            "until", "return", "local", "function", "require", "type", "pairs", "ipairs",
            "next", "select", "unpack", "error", "pcall", "xpcall"},
    "r": {"if", "else", "for", "while", "repeat", "return", "function", "library",
          "require", "source", "print", "cat", "paste", "class", "is", "as"},
}


def scan_file_generic(repo_root: Path, file_path: Path, lang: str) -> list[FunctionNode]:
    """Scan a non-Python source file using regex patterns."""
    module = module_name_from_path(repo_root, file_path)
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] Could not read {file_path}: {e}")
        return []

    lines = source.split("\n")
    patterns = FUNC_DEF_PATTERNS.get(lang, [])
    keywords = LANG_KEYWORDS.get(lang, set())

    # Find all function definitions
    functions: list[FunctionNode] = []

    for pattern in patterns:
        for match in pattern.finditer(source):
            name = match.group("n")
            if name in keywords or name.startswith("__"):
                continue
            lineno = source[:match.start()].count("\n") + 1
            fn = FunctionNode(
                module=module,
                name=name,
                qualified=f"{module}.{name}",
                lineno=lineno,
            )
            functions.append(fn)

    # Deduplicate by (name, lineno)
    seen = set()
    unique_functions = []
    for fn in functions:
        key = (fn.name, fn.lineno)
        if key not in seen:
            seen.add(key)
            unique_functions.append(fn)
    functions = unique_functions

    # Sort by line number
    functions.sort(key=lambda f: f.lineno)

    # Assign line ranges for call extraction
    func_ranges: list[tuple[int, int, FunctionNode]] = []
    for i, fn in enumerate(functions):
        start = fn.lineno
        end = functions[i + 1].lineno - 1 if i + 1 < len(functions) else len(lines)
        func_ranges.append((start, end, fn))

    # Extract calls within each function body
    for start, end, fn in func_ranges:
        body = "\n".join(lines[start:end])
        for call_match in CALL_PATTERN.finditer(body):
            callee = call_match.group("n")
            if callee not in keywords and callee != fn.name:
                fn.calls.append(callee)

    return functions


SUPPORTED_EXTENSIONS = {".py"} | set(EXTENSION_TO_LANG.keys())

SKIP_DIRS = {"__pycache__", ".venv", "venv", "env", "node_modules", ".git",
             "migrations", ".next", "dist", "build", ".tox", ".mypy_cache",
             ".pytest_cache", "vendor", "target", "bin", "obj", ".gradle",
             "site-packages", ".eggs", "egg-info"}


def scan_repo(repo_root: str) -> list[FunctionNode]:
    root = Path(repo_root).resolve()
    all_functions: list[FunctionNode] = []

    # Collect all supported source files
    source_files: list[tuple[Path, str]] = []  # (path, ext)
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        ext = f.suffix.lower()
        if ext in SUPPORTED_EXTENSIONS:
            source_files.append((f, ext))

    # Group by language for summary
    lang_counts: dict[str, int] = {}
    for _, ext in source_files:
        lang = EXTENSION_TO_LANG.get(ext, "python") if ext != ".py" else "python"
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    total = len(source_files)
    breakdown = ", ".join(f"{count} {lang}" for lang, count in sorted(lang_counts.items()))
    print(f"Found {total} source files under {root} ({breakdown})\n")

    for file_path, ext in source_files:
        if ext == ".py":
            fns = scan_file(root, file_path)
        else:
            lang = EXTENSION_TO_LANG[ext]
            fns = scan_file_generic(root, file_path, lang)
        all_functions.extend(fns)

    return all_functions

def write_edges_csv(functions: list[FunctionNode], output_path: str):
    """
    edges.csv schema:
        caller_module, caller_function, callee_function
    One row per (caller -> callee) edge.
    """
    rows_written = 0
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["caller_module", "caller_function", "callee_function"])
        for fn in functions:
            for callee in fn.calls:
                writer.writerow([fn.module, fn.qualified, callee])
                rows_written += 1
    print(f"edges.csv  -> {rows_written} edges written to {output_path}")


def write_nodes_csv(functions: list[FunctionNode], output_path: str):
    """
    nodes.csv schema:
        module, function, qualified_name, lineno, call_count
    One row per function definition.
    """
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["module", "function", "qualified_name", "lineno", "call_count"])
        for fn in functions:
            writer.writerow([fn.module, fn.name, fn.qualified, fn.lineno, len(fn.calls)])
    print(f"nodes.csv  -> {len(functions)} nodes written to {output_path}")


def write_graph_json(functions: list[FunctionNode], output_path: str):
    """
    graph.json - full adjacency list, handy for quick D3 / vis debugging.
    """
    graph = {
        fn.qualified: {
            "module": fn.module,
            "lineno": fn.lineno,
            "calls": fn.calls,
        }
        for fn in functions
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
    print(f"graph.json -> {len(graph)} nodes written to {output_path}")

def print_summary(functions: list[FunctionNode]):
    total_edges = sum(len(fn.calls) for fn in functions)
    modules = {fn.module for fn in functions}

    top = sorted(functions, key=lambda fn: len(fn.calls), reverse=True)[:10]

    print("\n" + "=" * 55)
    print("  CALL GRAPH SUMMARY")
    print("=" * 55)
    print(f"  Modules scanned  : {len(modules)}")
    print(f"  Functions found  : {len(functions)}")
    print(f"  Call edges       : {total_edges}")
    print(f"  Avg calls/fn     : {total_edges / max(len(functions), 1):.1f}")
    print()
    print("  Top 10 callers (most outgoing calls):")
    for fn in top:
        print(f"    {fn.qualified:<55} -> {len(fn.calls)} calls")
    print("=" * 55 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1: Build a call-graph from a source codebase."
    )
    parser.add_argument("repo", help="Path to the repository root")
    parser.add_argument("--output-dir", default=".", help="Directory for output files (default: cwd)")
    parser.add_argument("--json", action="store_true", help="Also emit graph.json")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"\nScanning: {args.repo}")
    functions = scan_repo(args.repo)

    write_edges_csv(functions, str(out / "edges.csv"))
    write_nodes_csv(functions, str(out / "nodes.csv"))
    if args.json:
        write_graph_json(functions, str(out / "graph.json"))

    print_summary(functions)
