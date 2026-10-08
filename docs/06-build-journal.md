# Build Journal

## Milestone 1: Observable Python Facts

Purpose: make extraction inspectable before building the API or UI.

Files changed: project metadata, backend domain/parser/ingestion/resolution modules, Python demo fixtures, tests and initial docs.

Decision: use Tree-sitter for parsing even though Python's `ast` module could handle this first slice. The trade-off is a little dependency complexity now in exchange for a consistent adapter shape when Java support is added.

Alternative: start with FastAPI and placeholder graph data. Rejected because it would make the UI look useful before the facts are trustworthy.

Checks: `pytest` should pass after installing development dependencies.

Exercise: rename the nested `submit` callback in `api.py` and observe how direct local resolution changes.

## Milestone 3 Start: SQLite Snapshots

Purpose: make analyzed facts durable and queryable without introducing the API yet.

Decision: use explicit SQLite statements for the first storage slice. SQLAlchemy is still available for later ORM-style modules, but direct SQL keeps the snapshot and traversal behavior transparent while the schema is still small.

Implemented behavior: publishing an analysis creates a staging snapshot, inserts files, nodes, edges and unresolved references, marks the snapshot completed, then updates the repository pointer. Bounded graph traversal enforces repo and snapshot filters on every query.

Checks: `tests/test_sqlite_graph.py` covers publish, symbol search and bounded traversal.

## Milestone 4 Start: FastAPI Surface

Purpose: expose the working analyzer and SQLite snapshots through typed HTTP endpoints.

Implemented behavior: local repository registration with allowlisted roots, bearer-token protection on mutating routes, inline indexing jobs with persistent status, summary, symbol search, bounded graph and node evidence endpoints.

Trade-off: the API queues work and a separate worker process claims it, matching the project contract without adding Redis or a message broker. SQLite is enough for one active indexing job; higher concurrency would need stricter lease/heartbeat handling.

Checks: `tests/test_api.py` covers the primary local repository journey and basic local safety checks.

## Worker Split

Purpose: keep CPU-heavy indexing out of the API event loop and make job progress durable.

Implemented behavior: `POST /api/repositories/{id}/index` creates a queued job. `python3 -m backend.app.jobs.worker` claims queued jobs, marks them running, indexes the repository, publishes a completed snapshot, then marks the job succeeded. On startup, the worker marks leftover running jobs as interrupted so clients can see that recovery is needed.

## Milestone 5: React Explorer

Purpose: make the analyzer usable from a browser without loading an entire repository graph at once.

Implemented behavior: the frontend registers an allowlisted local path, enqueues indexing, polls job state, searches symbols, requests bounded graph neighborhoods and renders source snippets for selected nodes.

Decision: use vis-network through a lifecycle-managed React component. The component creates a `Network` instance when graph data changes and destroys it on unmount so repeated graph loads do not leak canvas state.

Checks: `npm run build` verifies TypeScript and the production bundle. Automated browser smoke tests are still pending.

## Ingestion Expansion

Purpose: import more realistic repositories and capture non-code facts without implying runtime behavior.

Implemented behavior: repository registration accepts either an allowlisted local path or a public `https://github.com/owner/repository` URL. GitHub imports are cloned with bounded subprocess arguments, disabled prompts, disabled hooks and no submodules. Markdown relative links create `REFERENCES` edges only when the exact target path exists. `pyproject.toml` dependencies create `Dependency` nodes and `DECLARES_DEPENDENCY` edges.

Trade-off: reindexing still performs a full rebuild and publishes a new snapshot. File hashes are stored and current-snapshot queries drop stale nodes after a successful reindex, but unchanged extracted facts are not reused yet.
