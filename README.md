# M.A.C.E. - Legacy Refactoring Agent

M.A.C.E. is an AI-assisted migration tool that analyzes a legacy Python monolith, identifies service boundaries, and generates deployable FastAPI microservices. It combines static code analysis, graph clustering, LLM-guided planning, and shadow testing so teams can modernize a codebase with measurable confidence instead of manually guessing where to split services.

## What It Does

- Parses a Python monolith and builds dependency graphs from imports, functions, classes, and call relationships.
- Uses graph-based clustering to propose microservice boundaries.
- Generates FastAPI service scaffolds with route, schema, and dependency separation.
- Runs shadow tests to compare generated service behavior against the original monolith.
- Provides a web interface for reviewing decomposition plans and generated services.
- Supports containerized local development and production-style deployment.

## Why It Matters

Refactoring legacy systems into microservices is risky because hidden dependencies and behavior changes are easy to miss. This project focuses on making that process more observable:

- Architecture recommendations are based on code structure, not only manual review.
- Generated services can be validated against the original implementation.
- The workflow gives engineers a repeatable migration path from analysis to deployment.

## Tech Stack

- **Backend:** Python, FastAPI, Pydantic
- **AI / agents:** Claude API, LangChain-style agent workflows
- **Analysis:** static code analysis, graph clustering, dependency mapping
- **Frontend:** React / TypeScript
- **Infrastructure:** Docker, Docker Compose, Caddy
- **Testing:** pytest, shadow-testing workflow

## Architecture

```text
legacy codebase
    |
    v
static analyzer -> dependency graph -> service clustering
    |                                      |
    v                                      v
LLM planning ----------------------> generated FastAPI services
    |                                      |
    v                                      v
review UI -------------------------> shadow test validation
```

## Local Development

```powershell
git clone https://github.com/Pranay847/legacy_refactoring_agent.git
cd legacy_refactoring_agent

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
docker compose up --build
```

Check `.env.example` for required provider keys and local service configuration.

## Demo

Live demo: https://legacy-refactoring-agent-bay.vercel.app

## Project Status

This project is an active prototype focused on validating the full migration workflow: analysis, decomposition, service generation, and behavioral verification. The strongest current use case is evaluating small-to-medium Python monoliths and producing a reviewable migration plan.

## Resume Highlights

- Built an AI-powered pipeline for decomposing legacy Python monoliths into FastAPI microservices.
- Combined static analysis, graph clustering, and LLM planning to identify service boundaries.
- Added shadow testing to compare generated microservice behavior against the original monolith.
- Containerized the workflow for repeatable local and deployment environments.
