"""
Shadow Tester — Step 5
======================
Two modes:

  1. RUNNER MODE (default)
     Fires canned test payloads at both servers concurrently, diffs the
     responses, writes import_data/verification_results.json, which the
     monolith's GET /api/verification picks up automatically.

         python shadow_tester.py [shadow_config.json]

  2. MIDDLEWARE MODE
     Mounts a live shadow proxy on the monolith.  Every real request that
     hits the monolith is also forwarded asynchronously to the microservice.
     Results accumulate in verification_results.json in real time.

         python shadow_tester.py --middleware [shadow_config.json]
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx  # pip install httpx


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CONFIG   = "shadow_config.json"
DEFAULT_OUTPUT   = "import_data/verification_results.json"
DEFAULT_MONOLITH = "http://localhost:8000"
DEFAULT_SERVICE  = "http://localhost:9000"
MAX_RETRIES      = 3
RETRY_BACKOFF    = 1.5
FLOAT_TOLERANCE  = 1e-6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _floats_close(a: float, b: float) -> bool:
    if math.isnan(a) and math.isnan(b):
        return True
    return math.isclose(a, b, rel_tol=FLOAT_TOLERANCE, abs_tol=FLOAT_TOLERANCE)


def _deep_diff(a: Any, b: Any, path: str = "") -> list[str]:
    """
    Recursively diff two JSON-decoded values.
    Floats compared with epsilon so 105.5 == 105.50000000001.
    """
    diffs: list[str] = []

    a_num = isinstance(a, (int, float)) and not isinstance(a, bool)
    b_num = isinstance(b, (int, float)) and not isinstance(b, bool)

    if a_num and b_num:
        if not _floats_close(float(a), float(b)):
            diffs.append(f"{path}: {a!r} != {b!r}  (Δ={abs(float(a)-float(b)):.2e})")
        return diffs

    if type(a) != type(b):
        diffs.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
        return diffs

    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            child = f"{path}.{k}" if path else k
            if k not in a:
                diffs.append(f"{child}: missing in monolith response")
            elif k not in b:
                diffs.append(f"{child}: missing in microservice response")
            else:
                diffs.extend(_deep_diff(a[k], b[k], child))
        return diffs

    if isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"{path}: list length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(_deep_diff(x, y, f"{path}[{i}]"))
        return diffs

    if a != b:
        diffs.append(f"{path}: {a!r} != {b!r}")
    return diffs


def _pick(data: Any, keys: list[str] | None) -> Any:
    if keys is None or not isinstance(data, dict):
        return data
    return {k: data[k] for k in keys if k in data}


def _write_results(results: list[dict], output_path: Path) -> None:
    passed = sum(1 for r in results if r["passed"])
    payload = {
        "results": results,
        "summary": {
            "total":  len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "run_at": _now_iso(),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# HTTP fire + retry
# ---------------------------------------------------------------------------

async def _fire(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    payload: Any,
    timeout: float,
) -> tuple[int, Any, float]:
    t0 = time.perf_counter()
    kwargs: dict[str, Any] = {"timeout": timeout}
    if method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = payload
    elif method == "GET" and payload:
        kwargs["params"] = payload
    try:
        resp = await client.request(method, url, **kwargs)
        ms   = (time.perf_counter() - t0) * 1000
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body, round(ms, 2)
    except httpx.RequestError as exc:
        ms = (time.perf_counter() - t0) * 1000
        return -1, {"error": str(exc)}, round(ms, 2)


async def _fire_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    payload: Any,
    timeout: float,
) -> tuple[int, Any, float]:
    delay = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        status, body, ms = await _fire(client, method, url, payload, timeout)
        if status != -1:
            return status, body, ms
        if attempt < MAX_RETRIES:
            print(f"    ↻  Retry {attempt}/{MAX_RETRIES} for {url} in {delay:.1f}s …")
            await asyncio.sleep(delay)
            delay *= 2
    return status, body, ms


async def preflight_check(monolith_base: str, service_base: str, timeout: float) -> bool:
    print("  Pre-flight check …")
    ok = True
    async with httpx.AsyncClient() as client:
        for label, base in [("Monolith", monolith_base), ("Microservice", service_base)]:
            for probe in ["/api/status", "/", "/health"]:
                url = base.rstrip("/") + probe
                try:
                    r = await client.get(url, timeout=timeout)
                    print(f"    ✅  {label} reachable at {base}  (HTTP {r.status_code})")
                    break
                except httpx.RequestError:
                    continue
            else:
                print(f"    ❌  {label} NOT reachable at {base}")
                ok = False
    print()
    return ok


# ---------------------------------------------------------------------------
# Runner mode
# ---------------------------------------------------------------------------

async def run_one_test(
    test: dict[str, Any],
    monolith_base: str,
    service_base: str,
    timeout: float,
    global_compare_keys: list[str] | None,
) -> dict[str, Any]:
    method      = test.get("method", "POST").upper()
    endpoint    = test["endpoint"]
    payload     = test.get("payload", {})
    description = test.get("description", f"{method} {endpoint}")
    test_id     = test.get("id", endpoint.replace("/", "_").strip("_"))
    eff_keys    = test.get("compare_keys", global_compare_keys)

    mono_url = monolith_base.rstrip("/") + "/" + endpoint.lstrip("/")
    svc_url  = service_base.rstrip("/")  + "/" + endpoint.lstrip("/")

    async with httpx.AsyncClient() as client:
        (mono_status, mono_body, mono_ms), (svc_status, svc_body, svc_ms) = \
            await asyncio.gather(
                _fire_with_retry(client, method, mono_url, payload, timeout),
                _fire_with_retry(client, method, svc_url,  payload, timeout),
            )

    diff   = _deep_diff(_pick(mono_body, eff_keys), _pick(svc_body, eff_keys))
    passed = (mono_status == svc_status) and not diff

    icon = "✅" if passed else "❌"
    print(f"  {icon}  [{test_id}]  mono={mono_status}  svc={svc_status}  "
          f"Δfields={len(diff)}  ({mono_ms:.0f}ms / {svc_ms:.0f}ms)")
    for d in diff[:10]:
        print(f"       ↳  {d}")
    if len(diff) > 10:
        print(f"       ↳  … and {len(diff) - 10} more")

    return {
        "id":                  test_id,
        "description":         description,
        "monolith_url":        mono_url,
        "service_url":         svc_url,
        "method":              method,
        "payload":             payload,
        "monolith_status":     mono_status,
        "service_status":      svc_status,
        "monolith_response":   mono_body,
        "service_response":    svc_body,
        "compared_keys":       eff_keys,
        "diff":                diff,
        "passed":              passed,
        "latency_monolith_ms": mono_ms,
        "latency_service_ms":  svc_ms,
        "timestamp":           _now_iso(),
    }


async def runner_main(cfg: dict[str, Any], output_path: Path) -> None:
    monolith_base = cfg.get("monolith_base", DEFAULT_MONOLITH)
    service_base  = cfg.get("service_base",  DEFAULT_SERVICE)
    timeout       = float(cfg.get("timeout_seconds", 10.0))
    compare_keys  = cfg.get("compare_keys")
    tests         = cfg.get("tests", [])

    print(f"\n{'='*60}")
    print(f"  Shadow Tester  —  RUNNER MODE")
    print(f"  Monolith : {monolith_base}")
    print(f"  Service  : {service_base}")
    print(f"  Tests    : {len(tests)}")
    print(f"{'='*60}\n")

    if not await preflight_check(monolith_base, service_base, timeout):
        print("[shadow_tester] Aborting — one or both servers unreachable.")
        sys.exit(1)

    if not tests:
        print("[shadow_tester] No tests defined in config.")
        sys.exit(0)

    results: list[dict] = []
    for test in tests:
        result = await run_one_test(
            test, monolith_base, service_base, timeout, compare_keys
        )
        results.append(result)
        _write_results(results, output_path)  # live updates after each test

    passed = sum(1 for r in results if r["passed"])
    print(f"\n{'='*60}")
    print(f"  Results : {passed}/{len(results)} passed")
    print(f"  Output  : {output_path}")
    print(f"{'='*60}\n")

    if passed < len(results):
        sys.exit(1)


# ---------------------------------------------------------------------------
# Middleware mode — live shadow proxy
# ---------------------------------------------------------------------------

async def _shadow_and_log(
    method: str,
    path: str,
    raw_body: bytes,
    query_params: dict,
    mono_resp,
    mono_ms: float,
    service_base: str,
    timeout: float,
    compare_keys: list[str] | None,
    results: list[dict],
    lock: asyncio.Lock,
    output_path: Path,
) -> None:
    svc_url = service_base.rstrip("/") + path
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient() as c:
            svc_resp = await c.request(
                method, svc_url,
                content=raw_body,
                params=query_params,
                timeout=timeout,
            )
        svc_ms     = round((time.perf_counter() - t0) * 1000, 2)
        svc_status = svc_resp.status_code
        try:
            svc_body = svc_resp.json()
        except Exception:
            svc_body = svc_resp.text
    except httpx.RequestError as exc:
        svc_ms     = round((time.perf_counter() - t0) * 1000, 2)
        svc_status = -1
        svc_body   = {"error": str(exc)}

    try:
        mono_body = mono_resp.json()
    except Exception:
        mono_body = mono_resp.text

    diff   = _deep_diff(_pick(mono_body, compare_keys), _pick(svc_body, compare_keys))
    passed = (mono_resp.status_code == svc_status) and not diff

    entry = {
        "id":                  f"{method}_{path.replace('/', '_').strip('_')}_{_now_iso()}",
        "description":         f"[live] {method} {path}",
        "monolith_url":        path,
        "service_url":         svc_url,
        "method":              method,
        "payload":             raw_body.decode(errors="replace")[:500],
        "monolith_status":     mono_resp.status_code,
        "service_status":      svc_status,
        "monolith_response":   mono_body,
        "service_response":    svc_body,
        "compared_keys":       compare_keys,
        "diff":                diff,
        "passed":              passed,
        "latency_monolith_ms": mono_ms,
        "latency_service_ms":  svc_ms,
        "timestamp":           _now_iso(),
    }

    icon = "✅" if passed else "❌"
    print(f"  {icon}  [live {method} {path}]  mono={mono_resp.status_code}  "
          f"svc={svc_status}  Δ={len(diff)}")

    async with lock:
        results.append(entry)
        _write_results(results, output_path)


def build_shadow_app(cfg: dict[str, Any], output_path: Path):
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import Response
    except ImportError:
        print("[shadow_tester] FastAPI not installed. Run: pip install fastapi uvicorn")
        sys.exit(1)

    monolith_base = cfg.get("monolith_base", DEFAULT_MONOLITH)
    service_base  = cfg.get("service_base",  DEFAULT_SERVICE)
    timeout       = float(cfg.get("timeout_seconds", 10.0))
    compare_keys  = cfg.get("compare_keys")
    skip_paths    = set(cfg.get("middleware_skip_paths", [
        "/api/verification", "/docs", "/openapi.json", "/redoc",
    ]))

    results: list[dict] = []
    results_lock = asyncio.Lock()

    app = FastAPI(title="Shadow Proxy")

    @app.middleware("http")
    async def shadow_middleware(request: Request, call_next):
        path     = request.url.path
        raw_body = await request.body()

        # Forward to real monolith
        mono_url = monolith_base.rstrip("/") + path
        headers  = {k: v for k, v in request.headers.items() if k.lower() != "host"}
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient() as c:
                mono_resp = await c.request(
                    request.method, mono_url,
                    headers=headers,
                    content=raw_body,
                    params=dict(request.query_params),
                    timeout=timeout,
                )
            mono_ms = round((time.perf_counter() - t0) * 1000, 2)
        except httpx.RequestError as exc:
            return Response(content=str(exc), status_code=502)

        # Shadow fire (background, non-blocking)
        if path not in skip_paths:
            asyncio.ensure_future(_shadow_and_log(
                request.method, path, raw_body,
                dict(request.query_params),
                mono_resp, mono_ms,
                service_base, timeout, compare_keys,
                results, results_lock, output_path,
            ))

        return Response(
            content=mono_resp.content,
            status_code=mono_resp.status_code,
            headers=dict(mono_resp.headers),
        )

    return app


async def middleware_main(cfg: dict[str, Any], output_path: Path) -> None:
    try:
        import uvicorn
    except ImportError:
        print("[shadow_tester] uvicorn not installed. Run: pip install uvicorn")
        sys.exit(1)

    port          = int(cfg.get("middleware_port", 8001))
    timeout       = float(cfg.get("timeout_seconds", 10.0))
    monolith_base = cfg.get("monolith_base", DEFAULT_MONOLITH)
    service_base  = cfg.get("service_base",  DEFAULT_SERVICE)

    print(f"\n{'='*60}")
    print(f"  Shadow Tester  —  MIDDLEWARE MODE")
    print(f"  Proxy listens  : http://localhost:{port}")
    print(f"  Forwards to    : {monolith_base}")
    print(f"  Shadows to     : {service_base}")
    print(f"  Output         : {output_path}")
    print(f"{'='*60}\n")

    if not await preflight_check(monolith_base, service_base, timeout):
        print("[shadow_tester] Aborting — one or both servers unreachable.")
        sys.exit(1)

    shadow_app = build_shadow_app(cfg, output_path)
    config     = uvicorn.Config(shadow_app, host="0.0.0.0", port=port, log_level="warning")
    server     = uvicorn.Server(config)
    print(f"  Send traffic to http://localhost:{port} — results stream to {output_path}\n")
    await server.serve()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    args = sys.argv[1:]
    middleware_mode = "--middleware" in args
    if middleware_mode:
        args = [a for a in args if a != "--middleware"]

    config_path = Path(args[0] if args else DEFAULT_CONFIG)

    if not config_path.exists():
        print(f"[shadow_tester] Config not found: {config_path}")
        print("Copy shadow_config.example.json → shadow_config.json and edit it.")
        sys.exit(1)

    cfg         = json.loads(config_path.read_text(encoding="utf-8"))
    output_path = Path(cfg.get("output_path", DEFAULT_OUTPUT))

    if middleware_mode:
        asyncio.run(middleware_main(cfg, output_path))
    else:
        asyncio.run(runner_main(cfg, output_path))


if __name__ == "__main__":
    _cli()
