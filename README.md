# M.A.C.E. — Monolith Analysis & Clustering Engine

M.A.C.E. is an AI-assisted migration tool that analyzes a legacy Python monolith, identifies service boundaries from its call graph, and generates deployable FastAPI microservices — turning "where do we even split this?" into a reviewable plan backed by static analysis rather than guesswork.

**Live demo:** https://legacy-refactoring-agent-yti3.vercel.app

---

## Features

- **Static call-graph analysis** — Parses Python source with the `ast` module to map functions, modules, and call relationships. No execution required.
- **Automatic service boundaries** — Louvain community detection groups tightly-coupled functions into candidate microservices.
- **Database-free by default** — Clustering runs in-process via NetworkX, so no Neo4j instance is needed. Neo4j + Graph Data Science remains available for larger graphs.
- **AI service generation** — Claude generates a FastAPI scaffold per cluster: routes, logic, `requirements.txt`, and `Dockerfile`.
- **Shadow testing** — Compares generated service behaviour against the original monolith to catch regressions.
- **Codebase chat** — Ask questions about the analyzed code; answers are grounded in the actual cluster data.
- **Optional integrations** — Supabase, Clerk, Stripe, and Redis each activate only when their keys are present.
- **Deploy anywhere** — Vercel + Render on free tiers, a single Docker host, or AWS EC2 via Terraform.

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12, FastAPI, Uvicorn, Pydantic |
| **Frontend** | React 19, Vite 8, Tailwind CSS 4 (JSX) |
| **Analysis** | Python `ast`, NetworkX (Louvain) |
| **Graph DB** *(optional)* | Neo4j 5.18 + Graph Data Science plugin |
| **AI** | Anthropic Claude API (`claude-sonnet-4-5`) |
| **Auth** *(optional)* | Clerk |
| **Database** *(optional)* | Supabase (Postgres, Storage, RLS) |
| **Billing** *(optional)* | Stripe |
| **Queue / cache** *(optional)* | Redis + arq |
| **CI/CD** | GitHub Actions (build & push to ECR) |
| **Hosting** | Vercel (frontend) + Render (backend) |

Every "optional" row is genuinely optional — `backend/config.py` derives feature flags from key presence, so the app boots fine with all of them unset.

---

## Quick Start

### Prerequisites

- **Python 3.12+**
- **Node.js 22+** (see `frontend/.nvmrc` — pinned to 22.22.1)
- **Anthropic API key** — required for service generation and chat
- **Docker** — only if you want the Neo4j clustering backend

### Installation

Clone the repository:

```bash
git clone https://github.com/Pranay847/legacy_refactoring_agent.git
cd legacy_refactoring_agent
```

Install backend dependencies:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend && npm install && cd ..
```

### Environment Setup

```bash
cp .env.example .env
```

At minimum, set `ANTHROPIC_API_KEY`. Everything else has a working default — `CLUSTERING_BACKEND` defaults to `networkx`, which needs no database.

### Development

Run the backend:

```bash
uvicorn backend.app:app --reload --port 8000
```

Run the frontend in a second terminal:

```bash
cd frontend && npm run dev
```

Visit **http://localhost:5173**. Interactive API docs are at **http://localhost:8000/docs**.

### Production Build

```bash
cd frontend && npm run build       # static output in frontend/dist
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

---

## Repository Structure

```
legacy_refactoring_agent/
├── backend/
│   ├── app.py                  # FastAPI entrypoint — all HTTP routes
│   ├── config.py               # Central config; every env var is read here
│   ├── ingester.py             # AST parser -> nodes.csv + edges.csv
│   ├── graph_clustering.py     # Louvain via NetworkX (default, no database)
│   ├── graph_loader.py         # Louvain via Neo4j + GDS (optional backend)
│   ├── pipeline_runner.py      # Orchestrates steps 1-5, dispatches backends
│   ├── generate_services.py    # Claude prompts -> microservice source
│   ├── shadow_tester.py        # Parity checks vs. the original monolith
│   ├── validators.py           # Schema validation for clusters.json
│   ├── worker.py, jobs.py      # arq background jobs (needs Redis)
│   ├── auth.py, billing.py     # Clerk and Stripe integrations
│   └── test_*.py               # pytest suites
│
├── frontend/
│   ├── src/
│   │   ├── app/App.jsx         # Root component and layout
│   │   ├── components/         # UploadPanel, ResultsPanel, ChatWindow, Sidebar
│   │   ├── hooks/              # useSessionStore — client-side session state
│   │   ├── auth/AuthGate.jsx   # Clerk wrapper
│   │   └── api.js              # Backend client; reads VITE_API_BASE_URL
│   ├── vercel.json             # Pins the static Vite build
│   └── package.json
│
├── deploy/
│   ├── README-aws.md           # EC2 and managed-service deployment guide
│   └── terraform/              # One-box EC2 provisioning
│
├── supabase/migrations/        # Postgres schema
├── Dockerfile                  # Backend image (also runs the worker)
├── docker-compose.prod.yml     # Full stack: API + worker + Neo4j + Redis
├── render.yaml                 # Render Blueprint for the backend
└── requirements.txt
```

---

## Architecture Overview

The pipeline runs in five steps, each exposed as an endpoint:

```
Python monolith
      │
      ▼
1. Scan ──────────► nodes.csv + edges.csv        (ast, no execution)
      │
      ▼
2. Load graph ────► NetworkX in-memory  ─or─  Neo4j
      │
      ▼
3. Cluster ───────► Louvain communities ────────► clusters.json
      │
      ▼
4. Generate ──────► Claude ─────────────────────► services/<cluster>/
      │
      ▼
5. Verify ────────► shadow tests vs. the monolith
```

**Frontend** — Static Vite bundle on Vercel. Calls the backend directly; `VITE_API_BASE_URL` is inlined at build time.

**Backend** — FastAPI on Render. Holds pipeline state in memory and writes artifacts to `import/` and `services/`.

**Clustering backends** — `CLUSTERING_BACKEND=networkx` (default) runs Louvain in-process. `CLUSTERING_BACKEND=neo4j` uses `gds.louvain` and requires a Neo4j server with the Graph Data Science plugin.

### Supabase Tables

| Table | Purpose |
|---|---|
| `users` | User accounts |
| `projects` | Analyzed codebases |
| `pipeline_runs` | Run history and status |
| `generated_services` | Generated microservice metadata |
| `subscriptions` | Plan and payment state |
| `usage_events` | Per-endpoint metering |

---

## Example API Endpoints

### Pipeline

| Endpoint | Method | Description |
|---|---|---|
| `/api/status` | GET | Pipeline state and enabled integrations |
| `/api/ingest/` | POST | Upload files and scan them |
| `/api/cluster` | POST | Run Louvain community detection |
| `/api/clusters` | GET | Current clusters |
| `/api/generate` | POST | Generate one microservice |
| `/api/generate-all` | POST | Generate all services |
| `/api/graph` | GET | Call graph in Cytoscape format |
| `/api/verification` | GET | Shadow-test parity results |
| `/api/chat` | POST | Ask questions about the codebase |

**Example request** — cluster an uploaded project:

```bash
curl -X POST https://legacy-refactoring-agent-1tfy.onrender.com/api/cluster
```

**Example response:**

```json
{
  "status": "ok",
  "cached": false,
  "cluster_count": 2,
  "clusters": {
    "cluster_0": {
      "suggested_service": "billing",
      "size": 14,
      "community_id": 0
    },
    "cluster_1": {
      "suggested_service": "reporting",
      "size": 9,
      "community_id": 1
    }
  }
}
```

---

## Environment Variables

### Backend

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | Claude API key for generation and chat |
| `CLUSTERING_BACKEND` | No | `networkx` (default) or `neo4j` |
| `ENVIRONMENT` | No | `production` drops localhost from CORS |
| `FRONTEND_URL` | In production | The **only** allowed CORS origin when `ENVIRONMENT=production` |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | Only for `neo4j` | Must have the GDS plugin installed |
| `REDIS_URL` | No | Enables async job endpoints |
| `SUPABASE_*`, `CLERK_*`, `STRIPE_*` | No | Each feature stays off until its keys exist |

### Frontend

| Variable | Description |
|---|---|
| `VITE_API_BASE_URL` | Backend base URL, **including the `/api` suffix** |

> **Note:** Vite inlines `VITE_*` variables at **build** time. Changing one requires a rebuild — setting it at runtime has no effect.

---

## Testing

The backend uses **pytest**:

```bash
pytest backend/
```

Current coverage focuses on the analysis layer — `test_ingester.py` (AST parsing, call extraction) and `test_validators.py` (cluster schema validation).

Lint the frontend:

```bash
cd frontend && npm run lint
```

---

## Continuous Integration

`.github/workflows/build-and-push-ecr.yml` builds the backend and frontend images and pushes them to Amazon ECR on every push to `main`, authenticating via OIDC so no long-lived AWS keys are stored.

CI catches "it works on my machine" before it reaches a reviewer. If you add tests, wire them into this workflow so failures surface on the pull request.

---

## Versioning & Changelog

This project follows [Semantic Versioning](https://semver.org) — `MAJOR.MINOR.PATCH`:

- **MAJOR** — breaking API changes
- **MINOR** — new backwards-compatible features
- **PATCH** — bug fixes

Record notable changes in `CHANGELOG.md` so the project's evolution stays legible.

---

## Deployment

| Component | Platform | Notes |
|---|---|---|
| Frontend | Vercel | Root Directory `frontend`; set `VITE_API_BASE_URL` |
| Backend | Render | `render.yaml` Blueprint; set `ANTHROPIC_API_KEY` and `FRONTEND_URL` |
| Full stack | Single Docker host | `docker compose -f docker-compose.prod.yml up -d --build` |
| AWS | EC2 + Terraform | See [`deploy/README-aws.md`](deploy/README-aws.md) |

With `CLUSTERING_BACKEND=networkx` the backend needs no database, so Vercel and Render free tiers are sufficient.

**Deploying to Render:** the `Dockerfile` hardcodes `--port 8000`, but Render assigns a port via `$PORT`. Override the Docker command:

```bash
uvicorn backend.app:app --host 0.0.0.0 --port $PORT
```

Use `/openapi.json` as the health check path — it has no external dependencies.

---

## Contributing

Contributions are welcome. To contribute effectively:

1. **Fork the repository** and clone your fork.

2. **Create a feature branch:**

   ```bash
   git checkout -b feat/your-feature-name
   ```

3. **Set up your environment** following the [Quick Start](#quick-start) instructions above.

4. **Write or update tests** for your change:

   ```bash
   pytest backend/
   ```

5. **Use clear commit messages** following conventional commits:

   - `feat:` — new feature
   - `fix:` — bug fix
   - `docs:` — documentation
   - `refactor:` — restructuring without behaviour change
   - `test:` — adding or fixing tests

6. **Document your changes** — update this README or `CHANGELOG.md` when behaviour changes.

7. **Open a pull request** with a clear description, any related issue numbers (e.g. "Closes #12"), and example output or screenshots where relevant.

8. **Respond to review feedback** and iterate.

### Code of Conduct

All contributors are expected to:

- Be respectful, kind, and patient.
- Welcome feedback and engage constructively.
- Avoid discriminatory or offensive language.
- Focus on collaboration and problem-solving.
- Credit other contributors where due.
- Report concerns to the maintainers privately.

---

## Developer Checklist

Before sharing the project publicly, verify:

1. **The pipeline runs end to end** — upload a small Python project and confirm scan → cluster → generate all succeed.
2. **`/api/status` reports what you expect** — check `clustering_backend` and the `integrations` flags match your configuration.
3. **The frontend is responsive** — test on mobile and desktop widths.
4. **CORS is correct** — in production, `FRONTEND_URL` must exactly match the deployed frontend origin. A mismatch fails in the browser while `curl` still works.
5. **Tests pass** — `pytest backend/`.
6. **Documentation is current** — someone new should get running in under ten minutes using Quick Start alone.

---

## Common Pitfalls

**Hardcoding API keys.** Never commit keys. Keep them in `.env` (already gitignored) and inject them as environment variables in production.

**Forgetting that Vite inlines env vars at build time.** Setting `VITE_API_BASE_URL` after a build has no effect — you must rebuild. Symptom: the deployed app still calls `localhost`.

**CORS misconfiguration.** With `ENVIRONMENT=production`, `FRONTEND_URL` is the *only* permitted origin. Symptom: `curl` works but the browser fails.

**Expecting Neo4j to be free.** Managed Neo4j tiers generally exclude the Graph Data Science plugin, and AWS Neptune has no `gds.*` procedures at all. Use `CLUSTERING_BACKEND=networkx` unless you're self-hosting Neo4j with GDS.

**Assuming artifacts persist.** `import/`, `services/`, and in-memory pipeline state reset on restart. Platforms without a persistent disk lose generated services on every deploy.

**Skipping tests before deploying.** Run `pytest backend/` locally and let CI verify every change.

---

## License

No `LICENSE` file is currently included, which means default copyright applies and others have no explicit permission to use, modify, or distribute this code. If you intend it to be open source, add a license file — [MIT](https://choosealicense.com/licenses/mit/) is a common permissive choice.

## Contact

Issues and feature requests: [GitHub Issues](https://github.com/Pranay847/legacy_refactoring_agent/issues)

Repository: https://github.com/Pranay847/legacy_refactoring_agent
