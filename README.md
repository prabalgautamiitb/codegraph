# CodeGraph

CodeGraph is a local-first codebase knowledge graph explorer. The current milestone is a Python extraction and conservative resolution CLI that emits JSON facts with source evidence.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the Python demo

```bash
python3 -m backend.app.ingestion.cli fixtures/python_demo --pretty
```

## Run the API locally

```bash
python3 -m backend.app.api
```

Backend settings are loaded from `.env`. Mutating requests require the token in `CODEGRAPH_API_TOKEN`.

Run the worker in a second terminal:

```bash
python3 -m backend.app.jobs.worker
```

Run the frontend in a third terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend settings are loaded from `frontend/.env.local`.

## Test

```bash
pytest
```

## Current Scope

Implemented: Python file discovery, Markdown relative links, `pyproject.toml` dependencies, public GitHub HTTPS import, Tree-sitter parsing, declarations, imports, call sites, explicit inheritance, containment edges, conservative direct-call resolution, unresolved reference reasons, parse diagnostics, JSON CLI output, SQLite snapshots, durable job records, worker process, initial FastAPI endpoints, and a React/vis-network explorer.

Not implemented yet: incremental extraction reuse, Maven config extraction, and Java parsing.
