# CodeGraph Progress

## Completed

- Inspected the workspace and build prompt.
- Created the initial Python project structure.
- Added a Tree-sitter Python analyzer CLI.
- Added parser-independent domain records for declarations, imports, call sites, edges, evidence and unresolved references.
- Added a small Python demo fixture with classes, methods, nested functions, imports, receiver calls, Unicode text and a syntax error.
- Added pytest coverage for extraction, evidence spans, conservative receiver handling, imports and inheritance.
- Added a first SQLite snapshot store with atomic publish, symbol search and bounded graph traversal.
- Added durable job records and initial FastAPI endpoints for repository registration, indexing, job polling, summary, symbol search, graph traversal and node evidence.
- Added a separate worker command that claims queued jobs, runs indexing, records success/failure and marks interrupted running jobs on worker startup.
- Added a React/Vite/TypeScript frontend with repository registration, job status, symbol search, graph controls, vis-network rendering and source evidence inspection.
- Added public GitHub HTTPS import, Markdown relative-link extraction, `pyproject.toml` dependency extraction and a reindex stale-node regression test.

## Current Milestone

Milestone 7 start: public import and docs/config extraction.

## Run Commands

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python3 -m backend.app.ingestion.cli fixtures/python_demo --pretty
python3 -m backend.app.api
python3 -m backend.app.jobs.worker
cd frontend && npm install && npm run dev
```

## Known Issues

- Only Python source files are analyzed.
- Import extraction currently handles one import target per statement.
- Receiver calls such as `svc.submit()` are intentionally unresolved.
- SQLite storage does not yet include Alembic migrations, FTS5 or dedicated imports/call_sites tables.
- Worker concurrency is intentionally one active indexing job; there is no retry endpoint yet.
- There is no automated browser smoke test yet; frontend build is verified with `npm run build`.
- Reindexing is still a full rebuild; file hashes are stored but unchanged fact reuse is pending.
- GitHub import has no private authentication and no measured disk/time quota enforcement beyond clone timeout.
- Local development settings are loaded from `.env` and `frontend/.env.local`; keep token values in sync.

## Next Task

Add the bounded Java adapter, language support matrix and negative resolution tests.
