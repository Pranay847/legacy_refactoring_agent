# Legacy Refactoring Agent — Project Context for Claude Code

## What This Project Does
An AI-powered tool that automatically analyzes monolithic Python codebases and
decomposes them into microservices. Called M.A.C.E. (Monolith Analysis & Clustering Engine).

## Project Structure
```
legacy_refactoring_agent/
├── extractor/                  # Backend pipeline scripts
│   ├── ingester.py             # Phase 1: AST scanner → edges.csv, nodes.csv
│   ├── load_graph.py           # Phase 2: Neo4j loader + Louvain clustering
│   ├── generate_services.py    # Phase 3: Claude API microservice generator
│   ├── generate_services_ollama.py  # Phase 3 alt: Ollama version (CPU too slow)
│   ├── api.py                  # FastAPI backend wrapping all phases
│   ├── pipeline_runner.py      # Orchestrates all phases in sequence
│   └── test_ingester.py        # 32 passing pytest tests
├── frontend/frontend/          # React + Vite frontend (teammate's repo)
│   └── src/
│       ├── api.js              # API calls to FastAPI backend
│       ├── app/App.jsx         # Main app layout
│       ├── components/
│       │   ├── UploadPanel.jsx     # NEEDS FIX: change to repo path input
│       │   ├── ChatWindow.jsx      # NEEDS FIX: no /chat endpoint exists
│       │   ├── ResultsPanel.jsx    # Shows analysis results
│       │   ├── Sidebar.jsx         # Session list
│       │   ├── SessionHeader.jsx   # Session info
│       │   └── NewSessionModal.jsx # Create session modal
│       └── hooks/useSessionStore.js
├── import/                     # Pipeline outputs
│   ├── edges.csv               # Function call edges
│   ├── nodes.csv               # Function nodes
│   ├── clusters.json           # Louvain cluster results
│   └── graph.json              # Full adjacency list
├── services/                   # Generated microservices (Claude output)
│   └── cluster_0_utils/
│       ├── main.py, logic.py, Dockerfile, requirements.txt
├── docker-compose.yml          # Neo4j + GDS plugin
├── .env                        # ANTHROPIC_API_KEY, NEO4J_PASSWORD=surgeon1234
└── requirements.txt
```

## Tech Stack
- **Backend:** Python, FastAPI, uvicorn
- **AI:** Claude API (claude-sonnet-4-5) via anthropic SDK
- **Graph DB:** Neo4j 5.18 (Docker) + Graph Data Science plugin (Louvain)
- **Frontend:** React 19, Vite, Tailwind CSS 4, lucide-react
- **Testing:** pytest (32 tests, all passing)
- **OS:** Windows, PowerShell

## Running the Project
```powershell
# Start Neo4j
docker compose up -d

# Start backend (from extractor/)
cd extractor
.venv\Scripts\activate
uvicorn api:app --reload --port 8000

# Start frontend
cd frontend\frontend
npm run dev
# Opens at http://localhost:5173
```

## API Endpoints (api.py)
- POST /api/scan          → runs ingester, returns functions + edges
- POST /api/cluster       → loads Neo4j + runs Louvain
- GET  /api/clusters      → returns clusters.json
- GET  /api/graph         → returns graph data for visualization
- POST /api/generate      → generates FastAPI microservice via Claude
- GET  /api/services      → lists generated services
- GET  /api/services/{name}/{file} → get file contents
- GET  /api/health        → health check

## Neo4j Config
- URI: bolt://localhost:7687
- User: neo4j
- Password: surgeon1234
- Browser: http://localhost:7474

## What's Done ✅
1. Phase 1: ingester.py — AST scanner, tested, 32 passing tests
2. Phase 2: load_graph.py — Neo4j + Louvain, working
3. Phase 3: generate_services.py — Claude API, working
4. api.py — FastAPI backend, all endpoints working
5. pipeline_runner.py — orchestrator

## What Needs To Be Built ⬜
1. Fix UploadPanel.jsx — replace file drag/drop with repo path text input
   - should call scanRepo() then runClustering() in sequence
   - show progress: scanning → clustering → done
   - display results: X functions found, Y clusters detected

2. Fix ChatWindow.jsx — no /chat endpoint exists
   - either remove it or add a /api/chat endpoint to api.py
   - could use Claude API to answer questions about the scanned codebase

3. Build GraphViewer component — Cytoscape.js call graph
   - fetch from GET /api/graph
   - nodes colored by cluster (communityId)
   - clicking a node shows function details
   - install: npm install cytoscape react-cytoscape

4. Build SurgeryRoom component — Monaco Editor
   - left panel: original function source code
   - right panel: generated microservice code
   - file tabs: main.py, logic.py, Dockerfile, requirements.txt
   - install: npm install @monaco-editor/react

5. Build shadow_tester.py — parity testing
   - Flask middleware that intercepts requests to monolith
   - duplicates requests to new microservice asynchronously
   - compares responses using deepdiff
   - ignores: timestamps, trace_id, request_id
   - outputs verification_results.json

6. Build ParityDashboard component
   - fetches verification_results.json
   - shows pass/fail counts
   - lists diffs for failed comparisons

7. Deploy
   - Backend: Railway or Render (needs Dockerfile)
   - Frontend: Vercel
   - Database: Neo4j Aura (free cloud tier)
   - Add VITE_API_BASE env var to frontend for production URL

## Key Files to Know
- The test subject repo used so far: C:\Users\Prana\AutoReviewer
- Frontend teammate: Aryan Bhasin (github.com/AryanBhasin1)
- The ocClick typo bug in FolderUploader.jsx line 47 needs fixing (should be onClick)

## Important Notes
- Always use python.exe -m pytest (not bare pytest) on Windows
- Virtual env is at C:\Users\Prana\legacy_refactoring_agent\.venv
- Ollama is installed but too slow on CPU — use Claude API instead
- Docker Desktop must be running before docker compose up -d
- The frontend folder structure is nested: frontend/frontend/ (cloned repo has subfolder)
