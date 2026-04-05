"""
Shadow Tester — Parity Testing Middleware
==========================================
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
