// k6 load test for the Legacy Refactoring Agent API.
// ---------------------------------------------------------------------------
// Targets the read-heavy, cacheable endpoints so you can validate throughput,
// p95 latency, and the Redis cache under load. The expensive/mutating endpoints
// (scan, cluster, generate*) are intentionally NOT hammered here — they cost
// money/CPU and mutate state; see README.md for how to test those deliberately.
//
// Usage:
//   k6 run loadtest/k6_smoke.js
//   BASE_URL=https://api.example.com/api AUTH_TOKEN=<clerk-jwt> k6 run loadtest/k6_smoke.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000/api";
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";

const appErrors = new Rate("app_errors");

export const options = {
  scenarios: {
    reads: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 20 },
        { duration: "1m", target: 50 },
        { duration: "30s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
    app_errors: ["rate<0.05"],
  },
};

function headers() {
  return AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {};
}

export default function () {
  const h = headers();

  const status = http.get(`${BASE_URL}/status`, { headers: h });
  if (!check(status, { "status is 200": (r) => r.status === 200 })) {
    appErrors.add(1);
  }

  // 404 is acceptable before any pipeline run; both paths exercise the cache.
  const clusters = http.get(`${BASE_URL}/clusters`, { headers: h });
  if (!check(clusters, { "clusters 200/404": (r) => r.status === 200 || r.status === 404 })) {
    appErrors.add(1);
  }

  const graph = http.get(`${BASE_URL}/graph`, { headers: h });
  if (!check(graph, { "graph 200/404": (r) => r.status === 200 || r.status === 404 })) {
    appErrors.add(1);
  }

  sleep(1);
}
