import ast
import os
import csv
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class FunctionNode:
    module: str          
    name: str            
    qualified: str      
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
        - bare calls:        foo()          → "foo"
        - attribute calls:   obj.bar()      → "obj.bar"
        - chained:           a.b.c()        → "a.b.c"
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
    """Convert /repo/app/billing/views.py  →  app.billing.views"""
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


def scan_repo(repo_root: str) -> list[FunctionNode]:
    root = Path(repo_root).resolve()
    all_functions: list[FunctionNode] = []

    py_files = sorted(root.rglob("*.py"))
    print(f"Found {len(py_files)} Python files under {root}\n")

    for py_file in py_files:
        if any(part in py_file.parts for part in
            ("__pycache__", ".venv", "venv", "env", "node_modules", ".git", "migrations")):
            continue
        fns = scan_file(root, py_file)
        all_functions.extend(fns)

    return all_functions

def write_edges_csv(functions: list[FunctionNode], output_path: str):
    """
    edges.csv schema:
        caller_module, caller_function, callee_function
    One row per (caller → callee) edge.
    """
    rows_written = 0
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["caller_module", "caller_function", "callee_function"])
        for fn in functions:
            for callee in fn.calls:
                writer.writerow([fn.module, fn.qualified, callee])
                rows_written += 1
    print(f"edges.csv  → {rows_written} edges written to {output_path}")


def write_nodes_csv(functions: list[FunctionNode], output_path: str):
    """
    nodes.csv schema:
        module, function, qualified_name, lineno, call_count
    One row per function definition — useful for Neo4j node import.
    """
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["module", "function", "qualified_name", "lineno", "call_count"])
        for fn in functions:
            writer.writerow([fn.module, fn.name, fn.qualified, fn.lineno, len(fn.calls)])
    print(f"nodes.csv  → {len(functions)} nodes written to {output_path}")


def write_graph_json(functions: list[FunctionNode], output_path: str):
    """
    graph.json — full adjacency list, handy for quick D3 / vis debugging.
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
    print(f"graph.json → {len(graph)} nodes written to {output_path}")

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
        print(f"    {fn.qualified:<55} → {len(fn.calls)} calls")
    print("=" * 55 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1: Build a call-graph from a Python codebase."
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
