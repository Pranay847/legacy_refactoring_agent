# Legacy Refactoring Agent

An AI-powered pipeline that automatically decomposes a legacy Python monolith into standalone FastAPI microservices. The system uses static code analysis, graph-based community detection, and Claude AI to identify service boundaries, generate production-ready code, and verify correctness via shadow testing.

---

## How It Works

The pipeline runs in five sequential steps:

### Step 1 — Code Ingestion (`ingester.py`)
Recursively scans every `.py` file in the target codebase using Python's built-in `ast` (Abstract Syntax Tree) library. It maps every function definition to every function it calls (bare calls, attribute calls, and chained calls) and outputs a structured `edges.csv` file:

```
caller,callee,call_count
checkout_cart,calculate_tax,12
checkout_cart,process_stripe_payment,5
update_profile,hash_password,2
```

### Step 2 — Boundary Detection (`graph_loader.py`)
Loads `edges.csv` into a local Neo4j instance (via Docker). Creates `(:Function)-[:CALLS]->(:Function)` nodes and edges, then runs the **Louvain Modularity algorithm** from Neo4j's Graph Data Science library. The algorithm clusters tightly-coupled functions into communities — each community becomes a candidate microservice.

### Step 3 — Context Assembly (`generate_services.py`)
Takes the list of functions per community and extracts their exact source code from the original codebase (via AST for Python). Bundles the source and dynamically builds a structured prompt instructing the AI to rewrite the cluster as a standalone FastAPI microservice with proper endpoints, Pydantic models, and requirements.

### Step 4 — AI Generation (`generate_services.py` + Anthropic API)
Sends the assembled prompt to **Claude** (`claude-sonnet-4-5`) using structured outputs (JSON mode). The AI returns a complete microservice package. The script writes the output to `/new_microservices/<service_name>/`, containing:
- `main.py` — FastAPI app with REST endpoints
- `models.py` — Pydantic request/response models
- `requirements.txt` — dependencies

### Step 5 — Shadow Testing (`shadow_tester.py`)
Runs both the original monolith and the generated microservice concurrently, firing identical payloads at both. Responses are compared with float-tolerance diffing. Results are written to `import_data/verification_results.json` and surfaced in the frontend UI.

Two modes are available:
- **Runner mode** — fires a set of canned test payloads and reports pass/fail
- **Middleware mode** — mounts a live proxy on the monolith that shadows every real request to the microservice in real time

---

## Project Structure

```
legacy_refactoring_agent/
├── backend/
│   ├── api.py                     # FastAPI server — HTTP endpoints for the frontend
│   ├── pipeline_runner.py         # Orchestrates all 5 steps
│   ├── ingester.py                # Step 1: AST-based call graph extraction
│   ├── graph_loader.py            # Step 2: Neo4j loader + Louvain community detection
│   ├── generate_services.py       # Steps 3 & 4: Context assembly + Claude AI generation
│   ├── shadow_tester.py           # Step 5: Shadow testing & response diffing
│   ├── validators.py              # Cluster validation utilities
│   ├── shadow_config.example.json
│   ├── test_ingester.py
│   └── test_validators.py
├── frontend/
│   ├── src/
│   │   ├── app/App.jsx            # Root app component
│   │   ├── components/
│   │   │   ├── ChatWindow.jsx     # AI chat interface
│   │   │   ├── NewSessionModal.jsx
│   │   │   ├── ResultsPanel.jsx   # Displays generated services & test results
│   │   │   ├── SessionHeader.jsx
│   │   │   ├── Sidebar.jsx        # Session management
│   │   │   └── UploadPanel.jsx    # Codebase upload
│   │   ├── hooks/
│   │   │   └── useSessionStore.js
│   │   └── api.js                 # Frontend API client
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml             # Neo4j + GDS setup
└── .env                           # API keys and config (see below)
```

---

## Prerequisites

- Python 3.10+
- Node.js 18+ (`.nvmrc` specifies the exact version)
- Docker & Docker Compose
- An [Anthropic API key](https://console.anthropic.com/)

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/AryanBhasin1/legacy_refactoring_agent.git
cd legacy_refactoring_agent
```

### 2. Set up environment variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=your_api_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=surgeon1234
```

### 3. Start Neo4j (with Graph Data Science plugin)

```bash
docker-compose up -d
```

This spins up Neo4j on:
- Browser UI: `http://localhost:7474`
- Bolt (driver): `bolt://localhost:7687`

### 4. Set up the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

### 5. Set up the frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173`.

---

## Running the Pipeline

### Via the UI
1. Open `http://localhost:5173`
2. Create a new session and upload your Python codebase (zip or folder)
3. The pipeline runs automatically through all 5 steps
4. View generated microservices and shadow test results in the Results Panel

### Via CLI (backend only)

```bash
cd backend

# Step 1 - Scan codebase
python ingester.py --input /path/to/monolith --output import_data/edges.csv

# Step 2 - Load graph + detect communities
python graph_loader.py --input import_data/edges.csv

# Steps 3 & 4 - Generate microservices
python generate_services.py --clusters import_data/clusters.json --source /path/to/monolith

# Step 5 - Shadow test
python shadow_tester.py shadow_config.json
# or in middleware mode:
python shadow_tester.py --middleware shadow_config.json
```

---

## Shadow Testing

Copy and configure the shadow config:

```bash
cp backend/shadow_config.example.json shadow_config.json
```

The config specifies the monolith URL, microservice URL, test payloads, and endpoints to test. Results are written to `import_data/verification_results.json` and displayed live in the frontend.

A test passes when both servers return identical results (floats compared within tolerance `1e-6`).

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Generation | Anthropic Claude (`claude-sonnet-4-5`) |
| Backend API | Python, FastAPI, Uvicorn |
| Code Analysis | Python `ast` (Abstract Syntax Tree) |
| Graph Database | Neo4j 5.18 (community edition) |
| Graph Algorithm | Louvain Modularity via Neo4j GDS |
| Shadow Testing | `httpx` (async HTTP) |
| Frontend | React 19, Vite, Tailwind CSS |
| Infrastructure | Docker, Docker Compose |

---

## License

[MIT](https://choosealicense.com/licenses/mit/)
