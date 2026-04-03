import ast
import csv
import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from ingester import (
    CallGraphVisitor,
    FunctionNode,
    module_name_from_path,
    scan_file,
    scan_repo,
    write_edges_csv,
    write_nodes_csv,
    write_graph_json,
)


def parse_source(source: str, module: str = "test_module") -> CallGraphVisitor:
    """Parse a source string and return the visitor (with .functions populated)."""
    source = textwrap.dedent(source)
    tree = ast.parse(source)
    visitor = CallGraphVisitor(module)
    visitor.visit(tree)
    return visitor


def edges_of(visitor: CallGraphVisitor) -> set[tuple[str, str]]:
    """Return {(caller_qualified, callee)} pairs from a visitor."""
    return {
        (fn.qualified, callee)
        for fn in visitor.functions
        for callee in fn.calls
    }


def fn_names(visitor: CallGraphVisitor) -> list[str]:
    return [fn.qualified for fn in visitor.functions]

class TestFunctionDiscovery:

    def test_single_function_detected(self):
        v = parse_source("def foo(): pass")
        assert "test_module.foo" in fn_names(v)

    def test_multiple_functions_detected(self):
        v = parse_source("""
            def foo(): pass
            def bar(): pass
            def baz(): pass
        """)
        names = fn_names(v)
        assert "test_module.foo" in names
        assert "test_module.bar" in names
        assert "test_module.baz" in names

    def test_async_function_detected(self):
        v = parse_source("async def fetch(): pass")
        assert "test_module.fetch" in fn_names(v)

    def test_nested_function_gets_dotted_name(self):
        v = parse_source("""
            def outer():
                def inner():
                    pass
        """)
        assert "test_module.outer.inner" in fn_names(v)

    def test_no_functions_returns_empty(self):
        v = parse_source("x = 1 + 2")
        assert v.functions == []


class TestCallResolution:

    def test_bare_call(self):
        v = parse_source("""
            def foo():
                bar()
        """)
        assert ("test_module.foo", "bar") in edges_of(v)

    def test_attribute_call(self):
        v = parse_source("""
            def foo():
                obj.method()
        """)
        assert ("test_module.foo", "obj.method") in edges_of(v)

    def test_chained_attribute_call(self):
        v = parse_source("""
            def foo():
                datetime.date.today()
        """)
        assert ("test_module.foo", "datetime.date.today") in edges_of(v)

    def test_multiple_calls_in_one_function(self):
        v = parse_source("""
            def foo():
                bar()
                baz()
                qux.method()
        """)
        e = edges_of(v)
        assert ("test_module.foo", "bar") in e
        assert ("test_module.foo", "baz") in e
        assert ("test_module.foo", "qux.method") in e

    def test_no_calls_means_no_edges(self):
        v = parse_source("""
            def foo():
                x = 1 + 2
                return x
        """)
        assert edges_of(v) == set()

    def test_calls_only_recorded_inside_function(self):
        """Module-level calls (outside any def) should not be recorded."""
        v = parse_source("""
            orphan_call()   # module level — not inside a def

            def foo():
                bar()
        """)
        e = edges_of(v)
        assert ("test_module.foo", "bar") in e
        callees = {callee for _, callee in e}
        assert "orphan_call" not in callees

    def test_call_in_nested_function(self):
        v = parse_source("""
            def outer():
                def inner():
                    helper()
        """)
        assert ("test_module.outer.inner", "helper") in edges_of(v)

    def test_calls_not_confused_across_functions(self):
        v = parse_source("""
            def foo():
                alpha()

            def bar():
                beta()
        """)
        e = edges_of(v)
        assert ("test_module.foo", "alpha") in e
        assert ("test_module.bar", "beta") in e
        assert ("test_module.foo", "beta") not in e
        assert ("test_module.bar", "alpha") not in e


class TestModuleNaming:

    def test_simple_file(self):
        root = Path("/repo")
        assert module_name_from_path(root, Path("/repo/app.py")) == "app"

    def test_nested_file(self):
        root = Path("/repo")
        assert module_name_from_path(root, Path("/repo/billing/invoices.py")) == "billing.invoices"

    def test_init_file_drops_init(self):
        root = Path("/repo")
        assert module_name_from_path(root, Path("/repo/billing/__init__.py")) == "billing"

    def test_deep_nesting(self):
        root = Path("/repo")
        assert module_name_from_path(root, Path("/repo/a/b/c/d.py")) == "a.b.c.d"

class TestOutputWriters:

    @pytest.fixture
    def sample_functions(self) -> list[FunctionNode]:
        fn = FunctionNode(
            module="billing.invoices",
            name="calculate_invoice",
            qualified="billing.invoices.calculate_invoice",
            lineno=10,
            calls=["get_user", "get_cart_total", "apply_tax"],
        )
        return [fn]

    def test_edges_csv_headers(self, sample_functions, tmp_path):
        out = str(tmp_path / "edges.csv")
        write_edges_csv(sample_functions, out)
        with open(out) as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == ["caller_module", "caller_function", "callee_function"]

    def test_edges_csv_row_count(self, sample_functions, tmp_path):
        out = str(tmp_path / "edges.csv")
        write_edges_csv(sample_functions, out)
        with open(out) as f:
            rows = list(csv.reader(f))
        assert len(rows) == 1 + 3  # header + 3 callees

    def test_edges_csv_content(self, sample_functions, tmp_path):
        out = str(tmp_path / "edges.csv")
        write_edges_csv(sample_functions, out)
        with open(out) as f:
            rows = list(csv.DictReader(f))
        callees = {r["callee_function"] for r in rows}
        assert callees == {"get_user", "get_cart_total", "apply_tax"}
        for row in rows:
            assert row["caller_module"] == "billing.invoices"
            assert row["caller_function"] == "billing.invoices.calculate_invoice"

    def test_nodes_csv_headers(self, sample_functions, tmp_path):
        out = str(tmp_path / "nodes.csv")
        write_nodes_csv(sample_functions, out)
        with open(out) as f:
            headers = next(csv.reader(f))
        assert "qualified_name" in headers
        assert "call_count" in headers

    def test_graph_json_is_valid_json(self, sample_functions, tmp_path):
        out = str(tmp_path / "graph.json")
        write_graph_json(sample_functions, out)
        with open(out) as f:
            data = json.load(f)
        assert "billing.invoices.calculate_invoice" in data

    def test_empty_functions_writes_header_only(self, tmp_path):
        out = str(tmp_path / "edges.csv")
        write_edges_csv([], out)
        with open(out) as f:
            rows = list(csv.reader(f))
        assert rows == [["caller_module", "caller_function", "callee_function"]]

@pytest.fixture(scope="module")
def mini_monolith(tmp_path_factory) -> Path:
    """
    Creates the mini-monolith fixture on disk (same structure as the
    one built during development) and returns its root path.
    """
    root = tmp_path_factory.mktemp("mini_monolith")

    (root / "billing").mkdir()
    (root / "orders").mkdir()
    (root / "users").mkdir()

    (root / "billing" / "invoices.py").write_text(textwrap.dedent("""
        import datetime
        from users.profile import get_user
        from orders.cart import get_cart_total

        TAX_RATE = 0.08

        def calculate_invoice(user_id):
            user = get_user(user_id)
            total = get_cart_total(user_id)
            tax = apply_tax(total)
            return build_invoice_dict(user, total, tax)

        def apply_tax(amount):
            return round(amount * TAX_RATE, 2)

        def build_invoice_dict(user, subtotal, tax):
            return {"issued_at": datetime.date.today().isoformat()}

        def send_invoice_email(user_id):
            invoice = calculate_invoice(user_id)
            body = format_email_body(invoice)
            dispatch_email(invoice["user"], body)

        def format_email_body(invoice):
            return f"Dear {invoice['user']}"

        def dispatch_email(recipient, body):
            print(f"Sending to {recipient}")
    """))

    (root / "orders" / "cart.py").write_text(textwrap.dedent("""
        from orders.products import get_product_price

        _carts = {}

        def add_to_cart(user_id, product_id, qty):
            cart = _carts.setdefault(user_id, [])
            cart.append({"product_id": product_id, "qty": qty})

        def get_cart_total(user_id):
            cart = _carts.get(user_id, [])
            return sum(get_product_price(item["product_id"]) * item["qty"] for item in cart)

        def clear_cart(user_id):
            _carts.pop(user_id, None)

        def checkout(user_id):
            total = get_cart_total(user_id)
            clear_cart(user_id)
            return total
    """))

    (root / "orders" / "products.py").write_text(textwrap.dedent("""
        _prices = {"p1": 9.99}

        def get_product_price(product_id):
            return _prices.get(product_id, 0.0)

        def update_price(product_id, new_price):
            _prices[product_id] = new_price
            notify_price_change(product_id, new_price)

        def notify_price_change(product_id, price):
            print(f"price changed")
    """))

    (root / "users" / "profile.py").write_text(textwrap.dedent("""
        _users = {}

        def get_user(user_id):
            return _users.get(user_id, {})

        def create_user(user_id, name, email):
            _users[user_id] = {"name": name, "email": email}
            log_user_event("created", user_id)

        def log_user_event(event, user_id):
            print(f"{event}: {user_id}")
    """))

    (root / "app.py").write_text(textwrap.dedent("""
        from billing.invoices import calculate_invoice, send_invoice_email
        from orders.cart import add_to_cart, checkout
        from users.profile import create_user

        def run_demo():
            create_user("u1", "Alice", "alice@example.com")
            add_to_cart("u1", "p1", 2)
            invoice = calculate_invoice("u1")
            send_invoice_email("u1")
            return checkout("u1")
    """))

    return root


class TestIntegration:

    def test_scan_finds_all_files(self, mini_monolith):
        functions = scan_repo(str(mini_monolith))
        modules = {fn.module for fn in functions}
        assert "app" in modules
        assert "billing.invoices" in modules
        assert "orders.cart" in modules
        assert "orders.products" in modules
        assert "users.profile" in modules

    def test_scan_finds_expected_function_count(self, mini_monolith):
        functions = scan_repo(str(mini_monolith))
        assert len(functions) >= 15

    def test_known_edge_exists(self, mini_monolith):
        """calculate_invoice must call get_user and get_cart_total."""
        functions = scan_repo(str(mini_monolith))
        calc = next(f for f in functions if f.name == "calculate_invoice")
        assert "get_user" in calc.calls
        assert "get_cart_total" in calc.calls

    def test_cross_module_calls_captured(self, mini_monolith):
        """run_demo calls functions defined in other modules."""
        functions = scan_repo(str(mini_monolith))
        demo = next(f for f in functions if f.name == "run_demo")
        assert "create_user" in demo.calls
        assert "calculate_invoice" in demo.calls

    def test_edges_csv_written_correctly(self, mini_monolith, tmp_path):
        functions = scan_repo(str(mini_monolith))
        out = str(tmp_path / "edges.csv")
        write_edges_csv(functions, out)

        with open(out) as f:
            rows = list(csv.DictReader(f))

        assert len(rows) > 0
        for row in rows:
            assert row["caller_module"]
            assert row["caller_function"]
            assert row["callee_function"]

    def test_nodes_csv_call_counts_are_non_negative(self, mini_monolith, tmp_path):
        functions = scan_repo(str(mini_monolith))
        out = str(tmp_path / "nodes.csv")
        write_nodes_csv(functions, out)

        with open(out) as f:
            rows = list(csv.DictReader(f))

        for row in rows:
            assert int(row["call_count"]) >= 0

    def test_graph_json_adjacency_structure(self, mini_monolith, tmp_path):
        functions = scan_repo(str(mini_monolith))
        out = str(tmp_path / "graph.json")
        write_graph_json(functions, out)

        with open(out) as f:
            data = json.load(f)

        for key, val in data.items():
            assert "module" in val
            assert "calls" in val
            assert isinstance(val["calls"], list)

    def test_pycache_dirs_are_skipped(self, mini_monolith):
        """__pycache__ files must never appear as modules."""
        functions = scan_repo(str(mini_monolith))
        for fn in functions:
            assert "__pycache__" not in fn.module

    def test_syntax_error_file_is_skipped_gracefully(self, mini_monolith):
        """A file with a syntax error should not crash the whole scan."""
        bad_file = mini_monolith / "bad_syntax.py"
        bad_file.write_text("def oops(\n  # unclosed paren\n")
        try:
            functions = scan_repo(str(mini_monolith))
            assert len(functions) > 0
        finally:
            bad_file.unlink()
