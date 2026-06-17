# Load testing & pre-launch checklist

Two equivalent scripts hit the read-heavy, cacheable endpoints so you can
validate throughput, p95 latency, and the Redis cache under load.

## Run with k6
```bash
# install: https://k6.io/docs/get-started/installation/
k6 run loadtest/k6_smoke.js

# against a deployed env, optionally authenticated
BASE_URL=https://api.example.com/api AUTH_TOKEN=<clerk-jwt> k6 run loadtest/k6_smoke.js
```
Thresholds (the run fails if breached): error rate < 1%, p95 < 500ms.

## Run with Locust
```bash
pip install locust
locust -f loadtest/locustfile.py --host http://127.0.0.1:8000
# open http://localhost:8089

# headless
AUTH_TOKEN=<clerk-jwt> locust -f loadtest/locustfile.py \
  --host https://api.example.com --headless -u 50 -r 10 -t 2m
```

## Testing the expensive / rate-limited endpoints (deliberately)
`scan`, `cluster`, `generate`, `generate-all`, and `chat` cost CPU/money and
mutate state, so they are excluded from the scripts above. To validate **rate
limiting**, set `REDIS_URL` (or `RATE_LIMIT_ENABLED=true`) on the server and
fire a tight loop at one of them with a valid token — you should see HTTP `429`
with a `Retry-After` header once the per-minute limit is hit.

To validate **async generation**, set `REDIS_URL`, run the worker
(`arq backend.worker.WorkerSettings`), then `POST /api/generate-all/async` and
poll `GET /api/jobs/{id}` until `status` is `complete`.

---

# Pre-launch checklist

### Secrets & config
- [ ] Rotate the Neo4j password — it was committed in git history (`e1d5441`) and is public. Scrub history (BFG/git-filter-repo) or confirm Neo4j is not internet-reachable.
- [ ] Real `.env` is NOT committed (`git ls-files .env` returns nothing).
- [ ] All secret keys are server-side only; the frontend has only `VITE_*` publishable/anon values.
- [ ] `ENVIRONMENT=production`, `DEBUG=false`, and `FRONTEND_URL` set to the real origin.

### Database (Supabase)
- [ ] `supabase/migrations/0001_init.sql` applied.
- [ ] RLS confirmed enabled on every table (Supabase → Auth → Policies).
- [ ] Clerk configured as a Supabase third-party auth provider.
- [ ] `SUPABASE_SERVICE_ROLE_KEY` is only on the backend.

### Auth (Clerk)
- [ ] `CLERK_SECRET_KEY` + `CLERK_ISSUER` (or `CLERK_JWKS_URL`) set on the backend; `VITE_CLERK_PUBLISHABLE_KEY` on the frontend.
- [ ] Protected `/api/*` routes return `401` without a valid token; sign-in/sign-out works.

### Billing (Stripe)
- [ ] Pro/Team products + prices created; `STRIPE_PRICE_PRO` / `STRIPE_PRICE_TEAM` set.
- [ ] Webhook endpoint points at `/api/stripe/webhook`; `STRIPE_WEBHOOK_SECRET` set.
- [ ] Test-mode checkout completes and writes a `subscriptions` row; plan limits enforced (`402` when exceeded).

### Performance & reliability
- [ ] `REDIS_URL` set; rate limiting returns `429` under load.
- [ ] `/api/graph` and `/api/clusters` are noticeably faster on the second call (cache hit).
- [ ] Worker process (`worker:`) deployed and processing jobs.
- [ ] k6/Locust run meets the latency/error thresholds.
- [ ] CORS allows only the production `FRONTEND_URL`.

### Hosting
- [ ] Both `web` and `worker` processes deployed with the full env.
- [ ] Health check hitting `GET /api/status`.
- [ ] Supabase automated backups enabled.
