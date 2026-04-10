"""
Shadow Tester — Step 5
Fires identical requests at the monolith and a generated microservice,
diffs the responses, and writes results to verification_results.json
(consumed by GET /api/verification on the monolith).

Usage
-----
    python shadow_tester.py [config.json]

If no config file is given it looks for shadow_config.json in the same
directory.  See shadow_config.example.json for the format.

Output
------
Writes  <IMPORT_DIR>/verification_results.json  (same path the monolith
reads at /api/verification).

The file looks like:
{
  "results": [
    {
      "id":           "scan_repo",
      "description":  "POST /api/scan  →  POST /api/scan",
      "monolith_url": "http://localhost:8000/api/scan",
      "service_url":  "http://localhost:9000/api/scan",
      "payload":      { "repo_path": "/tmp/demo" },
      "monolith_status":  200,
      "service_status":   200,
      "monolith_response": { ... },
      "service_response":  { ... },
      "diff":         [],          ← list of mismatched field paths
      "passed":       true,
      "latency_monolith_ms": 42,
      "latency_service_ms":  38,
      "timestamp":    "2025-06-15T14:23:01Z"
    },
    ...
  ],
  "summary": {
    "total": 3,
    "passed": 3,
    "failed": 0,
    "run_at": "2025-06-15T14:23:05Z"
  }
}
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx  # pip install httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _deep_diff(a: Any, b: Any, path: str = "") -> list[str]:
    """Return a list of dotted paths where a and b differ."""
    diffs: list[str] = []

    if type(a) != type(b):
        diffs.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
        return diffs

    if isinstance(a, dict):
        all_keys = set(a) | set(b)
        for k in sorted(all_keys):
            child = f"{path}.{k}" if path else k
            if k not in a:
                diffs.append(f"{child}: missing in monolith")
            elif k not in b:
                diffs.append(f"{child}: missing in microservice")
            else:
                diffs.extend(_deep_diff(a[k], b[k], child))

    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"{path}: list length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(_deep_diff(x, y, f"{path}[{i}]"))

    else:
        if a != b:
            diffs.append(f"{path}: {a!r} != {b!r}")

    return diffs


def _pick(response_json: Any, keys: list[str] | None) -> Any:
    """If `keys` is set, compare only those top-level keys."""
    if keys is None or not isinstance(response_json, dict):
        return response_json
    return {k: response_json[k] for k in keys if k in response_json}


# ---------------------------------------------------------------------------
# Core shadow request
# ---------------------------------------------------------------------------

async def _fire(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    payload: Any,
    timeout: float,
) -> tuple[int, Any, float]:
    """Send one request; return (status, body_as_python, latency_ms)."""
    t0 = time.perf_counter()
    try:
        req_kwargs: dict[str, Any] = {"timeout": timeout}
        method = method.upper()
        if method in ("POST", "PUT", "PATCH"):
            req_kwargs["json"] = payload
        elif method == "GET" and payload:
            req_kwargs["params"] = payload

        resp = await client.request(method, url, **req_kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body, round(latency_ms, 2)
    except httpx.RequestError as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        return -1, {"error": str(exc)}, round(latency_ms, 2)


async def run_shadow_test(
    test: dict[str, Any],
    monolith_base: str,
    service_base: str,
    timeout: float,
    compare_keys: list[str] | None,
) -> dict[str, Any]:
    """Run a single shadow test case; return a result dict."""
    method      = test.get("method", "POST").upper()
    endpoint    = test["endpoint"]
    payload     = test.get("payload", {})
    description = test.get("description", f"{method} {endpoint}")
    test_id     = test.get("id", endpoint.replace("/", "_").strip("_"))

    # Allow per-test override of compare_keys
    effective_keys = test.get("compare_keys", compare_keys)

    monolith_url = monolith_base.rstrip("/") + "/" + endpoint.lstrip("/")
    service_url  = service_base.rstrip("/")  + "/" + endpoint.lstrip("/")

    async with httpx.AsyncClient() as client:
        mono_task    = _fire(client, method, monolith_url, payload, timeout)
        service_task = _fire(client, method, service_url,  payload, timeout)
        (mono_status, mono_body, mono_ms), (svc_status, svc_body, svc_ms) = \
            await asyncio.gather(mono_task, service_task)

    mono_cmp = _pick(mono_body, effective_keys)
    svc_cmp  = _pick(svc_body,  effective_keys)
    diff     = _deep_diff(mono_cmp, svc_cmp)
    passed   = (mono_status == svc_status) and (len(diff) == 0)

    result = {
        "id":                   test_id,
        "description":          description,
        "monolith_url":         monolith_url,
        "service_url":          service_url,
        "method":               method,
        "payload":              payload,
        "monolith_status":      mono_status,
        "service_status":       svc_status,
        "monolith_response":    mono_body,
        "service_response":     svc_body,
        "compared_keys":        effective_keys,
        "diff":                 diff,
        "passed":               passed,
        "latency_monolith_ms":  mono_ms,
        "latency_service_ms":   svc_ms,
        "timestamp":            _now_iso(),
    }

    # Print inline progress
    icon = "✅" if passed else "❌"
    print(f"  {icon}  [{test_id}]  mono={mono_status}  svc={svc_status}  "
          f"diff={len(diff)} fields  ({mono_ms:.0f}ms / {svc_ms:.0f}ms)")
    if diff:
        for d in diff[:10]:
            print(f"       ↳  {d}")
        if len(diff) > 10:
            print(f"       ↳  … and {len(diff) - 10} more")

    return result


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def main(config_path: Path) -> None:
    if not config_path.exists():
        print(f"[shadow_tester] Config not found: {config_path}")
        print("Create a shadow_config.json  — see shadow_config.example.json for format.")
        sys.exit(1)

    cfg: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))

    monolith_base  = cfg.get("monolith_base",  "http://localhost:8000")
    service_base   = cfg.get("service_base",   "http://localhost:9000")
    output_path    = Path(cfg.get("output_path", "import_data/verification_results.json"))
    timeout        = float(cfg.get("timeout_seconds", 10.0))
    compare_keys   = cfg.get("compare_keys")          # None ⇒ full diff
    tests: list[dict] = cfg.get("tests", [])

    if not tests:
        print("[shadow_tester] No tests defined in config.")
        sys.exit(0)

    print(f"\n{'='*60}")
    print(f"  Shadow Tester")
    print(f"  Monolith : {monolith_base}")
    print(f"  Service  : {service_base}")
    print(f"  Tests    : {len(tests)}")
    print(f"{'='*60}\n")

    results: list[dict] = []
    for test in tests:
        result = await run_shadow_test(
            test, monolith_base, service_base, timeout, compare_keys
        )
        results.append(result)

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    summary = {
        "total":   len(results),
        "passed":  passed,
        "failed":  failed,
        "run_at":  _now_iso(),
    }

    output = {"results": results, "summary": summary}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  Results  : {passed}/{len(results)} passed")
    print(f"  Output   : {output_path}")
    print(f"{'='*60}\n")

    if failed:
        sys.exit(1)


def _cli() -> None:
    config_arg = sys.argv[1] if len(sys.argv) > 1 else "shadow_config.json"
    asyncio.run(main(Path(config_arg)))


if __name__ == "__main__":
    _cli()
Shadow Tester — Parity Testing Middleware
Intercepts requests destined for the monolith, duplicates them asynchronously
to a new microservice, compares the responses, and writes results to
import/verification_results.json.

Usage:
    python shadow_tester.py \\
        --monolith http://localhost:5000 \\
        --shadow   http://localhost:8001 \\
        --port     9000

Then route your test traffic through http://localhost:9000 instead of
directly to the monolith.

Install deps:
    pip install flask requests deepdiff
"""

import argparse
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from deepdiff import DeepDiff
from flask import Flask, Response, request as flask_request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_PATH = BASE_DIR / "import" / "verification_results.json"

# Fields to ignore when comparing responses (timestamps, trace ids, etc.)
IGNORE_FIELDS = {
    "timestamp", "created_at", "updated_at", "request_id",
    "trace_id", "correlation_id", "server_time",
}

app = Flask(__name__)

# Runtime config (set in main)
MONOLITH_URL = ""
SHADOW_URL = ""
_results_lock = threading.Lock()


def _load_results() -> dict:
    if RESULTS_PATH.exists():
        try:
            return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"results": [], "summary": {"total": 0, "passed": 0, "failed": 0}}


def _save_results(data: dict):
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _append_result(entry: dict):
    with _results_lock:
        data = _load_results()
        data["results"].append(entry)
        data["summary"]["total"] += 1
        if entry["passed"]:
            data["summary"]["passed"] += 1
        else:
            data["summary"]["failed"] += 1
        _save_results(data)


def _normalize(body: bytes) -> object:
    """Try to parse JSON body for deep comparison; fall back to raw string."""
    try:
        return json.loads(body)
    except Exception:
        return body.decode("utf-8", errors="replace")


def _compare(monolith_resp: requests.Response, shadow_resp: requests.Response) -> list:
    """Return list of diff strings (empty = identical)."""
    mono_body = _normalize(monolith_resp.content)
    shadow_body = _normalize(shadow_resp.content)

    diff = DeepDiff(
        mono_body,
        shadow_body,
        ignore_order=True,
        exclude_paths=[f"root['{f}']" for f in IGNORE_FIELDS],
        verbose_level=0,
    )
    return list(diff.to_dict().items()) if diff else []


def _fire_shadow(method: str, path: str, headers: dict, data: bytes, params: dict):
    """Send shadow request and compare; runs in a background thread."""
    try:
        shadow_resp = requests.request(
            method=method,
            url=SHADOW_URL.rstrip("/") + path,
            headers=headers,
            data=data,
            params=params,
            timeout=10,
            allow_redirects=False,
        )
        return shadow_resp
    except Exception as exc:
        logger.warning("Shadow request failed: %s", exc)
        return None


@app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.route("/", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def proxy(path=""):
    full_path = "/" + path
    method = flask_request.method
    body = flask_request.get_data()
    params = flask_request.args.to_dict(flat=False)

    # Forward-safe headers (strip host)
    headers = {
        k: v for k, v in flask_request.headers
        if k.lower() not in ("host", "content-length")
    }

    # --- Send to monolith (blocking) ---
    mono_resp = requests.request(
        method=method,
        url=MONOLITH_URL.rstrip("/") + full_path,
        headers=headers,
        data=body,
        params=params,
        timeout=30,
        allow_redirects=False,
    )

    # --- Send to shadow (async) ---
    shadow_future = {"resp": None}

    def _shadow():
        shadow_future["resp"] = _fire_shadow(method, full_path, headers, body, params)

    t = threading.Thread(target=_shadow, daemon=True)
    t.start()
    t.join(timeout=12)  # wait up to 12 s for shadow

    shadow_resp = shadow_future["resp"]
    if shadow_resp is not None:
        diffs = _compare(mono_resp, shadow_resp)
        passed = len(diffs) == 0
        _append_result({
            "method": method,
            "path": full_path,
            "passed": passed,
            "mono_status": mono_resp.status_code,
            "shadow_status": shadow_resp.status_code,
            "diffs": diffs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(
            "%s %s -> mono=%d shadow=%d %s",
            method,
            full_path,
            mono_resp.status_code,
            shadow_resp.status_code,
            "PASS" if passed else f"FAIL ({len(diffs)} diffs)",
        )
    else:
        logger.warning("No shadow response for %s %s", method, full_path)

    # --- Return monolith response verbatim ---
    excluded = {"content-encoding", "content-length", "transfer-encoding", "connection"}
    resp_headers = {k: v for k, v in mono_resp.headers.items() if k.lower() not in excluded}
    return Response(
        mono_resp.content,
        status=mono_resp.status_code,
        headers=resp_headers,
    )


def main():
    global MONOLITH_URL, SHADOW_URL

    parser = argparse.ArgumentParser(description="Shadow Tester — parity middleware")
    parser.add_argument("--monolith", default="http://localhost:5000", help="Monolith base URL")
    parser.add_argument("--shadow", default="http://localhost:8001", help="Microservice base URL")
    parser.add_argument("--port", type=int, default=9000, help="Port for this proxy")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    args = parser.parse_args()

    MONOLITH_URL = args.monolith
    SHADOW_URL = args.shadow

    logger.info("Shadow tester starting on http://%s:%d", args.host, args.port)
    logger.info("  Monolith -> %s", MONOLITH_URL)
    logger.info("  Shadow   -> %s", SHADOW_URL)
    logger.info("  Results  -> %s", RESULTS_PATH)

    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
