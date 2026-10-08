from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.app.domain.model import Declaration, Edge, RepositoryAnalysis, stable_logical_id, NodeKind


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS repositories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  root TEXT NOT NULL UNIQUE,
  current_snapshot_id INTEGER
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_id INTEGER NOT NULL,
  status TEXT NOT NULL,
  analyzer_version TEXT NOT NULL,
  counts_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS files (
  id TEXT NOT NULL,
  repo_id INTEGER NOT NULL,
  snapshot_id INTEGER NOT NULL,
  path TEXT NOT NULL,
  language TEXT NOT NULL,
  file_hash TEXT NOT NULL,
  diagnostics_json TEXT NOT NULL,
  PRIMARY KEY (repo_id, snapshot_id, id)
);

CREATE TABLE IF NOT EXISTS nodes (
  id TEXT NOT NULL,
  repo_id INTEGER NOT NULL,
  snapshot_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  qualified_name TEXT NOT NULL,
  path TEXT NOT NULL,
  signature TEXT NOT NULL,
  enclosing_scope TEXT,
  span_json TEXT NOT NULL,
  PRIMARY KEY (repo_id, snapshot_id, id)
);

CREATE TABLE IF NOT EXISTS edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_id INTEGER NOT NULL,
  snapshot_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  source_id TEXT NOT NULL,
  target_id TEXT NOT NULL,
  evidence_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS unresolved_references (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_id INTEGER NOT NULL,
  snapshot_id INTEGER NOT NULL,
  path TEXT NOT NULL,
  kind TEXT NOT NULL,
  expression TEXT NOT NULL,
  reason TEXT NOT NULL,
  span_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_id INTEGER NOT NULL,
  status TEXT NOT NULL,
  stage TEXT NOT NULL,
  counts_json TEXT NOT NULL DEFAULT '{}',
  diagnostics_json TEXT NOT NULL DEFAULT '[]',
  failure_reason TEXT,
  snapshot_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nodes_search ON nodes(repo_id, snapshot_id, name, qualified_name);
CREATE INDEX IF NOT EXISTS idx_edges_out ON edges(repo_id, snapshot_id, source_id, kind);
CREATE INDEX IF NOT EXISTS idx_edges_in ON edges(repo_id, snapshot_id, target_id, kind);
CREATE INDEX IF NOT EXISTS idx_jobs_repo ON jobs(repo_id, status, created_at);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def publish_analysis(conn: sqlite3.Connection, analysis: RepositoryAnalysis) -> tuple[int, int]:
    with conn:
        repo_id = _repository_id(conn, analysis.root)
        cur = conn.execute(
            "INSERT INTO snapshots(repo_id, status, analyzer_version, counts_json) VALUES (?, ?, ?, ?)",
            (repo_id, "staging", analysis.analyzer_version, json.dumps(analysis.counts, sort_keys=True)),
        )
        snapshot_id = int(cur.lastrowid)
        for file in analysis.files:
            file_id = stable_logical_id(file.path, NodeKind.FILE, file.path)
            conn.execute(
                """
                INSERT INTO files(id, repo_id, snapshot_id, path, language, file_hash, diagnostics_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (file_id, repo_id, snapshot_id, file.path, file.language, file.file_hash, json.dumps(file.diagnostics)),
            )
            conn.execute(
                """
                INSERT INTO nodes(id, repo_id, snapshot_id, kind, name, qualified_name, path, signature, enclosing_scope, span_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (file_id, repo_id, snapshot_id, NodeKind.FILE.value, Path(file.path).name, file.path, file.path, "", None, "{}"),
            )
            for decl in file.declarations:
                _insert_node(conn, repo_id, snapshot_id, decl)
        for edge in analysis.edges:
            conn.execute(
                "INSERT INTO edges(repo_id, snapshot_id, kind, source_id, target_id, evidence_json) VALUES (?, ?, ?, ?, ?, ?)",
                (repo_id, snapshot_id, edge.kind.value, edge.source_id, edge.target_id, json.dumps(_asdict(edge.evidence), sort_keys=True)),
            )
        for ref in analysis.unresolved_references:
            conn.execute(
                """
                INSERT INTO unresolved_references(repo_id, snapshot_id, path, kind, expression, reason, span_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (repo_id, snapshot_id, ref.path, ref.kind, ref.expression, ref.reason, json.dumps(_asdict(ref.span), sort_keys=True)),
            )
        conn.execute("UPDATE snapshots SET status = ? WHERE id = ?", ("completed", snapshot_id))
        conn.execute("UPDATE repositories SET current_snapshot_id = ? WHERE id = ?", (snapshot_id, repo_id))
    return repo_id, snapshot_id


def register_repository(conn: sqlite3.Connection, root: Path) -> int:
    root_text = str(root.resolve())
    with conn:
        return _repository_id(conn, root_text)


def repository_root(conn: sqlite3.Connection, repo_id: int) -> Path:
    row = conn.execute("SELECT root FROM repositories WHERE id = ?", (repo_id,)).fetchone()
    if not row:
        raise ValueError(f"Repository {repo_id} was not found")
    return Path(row["root"])


def create_job(conn: sqlite3.Connection, repo_id: int) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO jobs(repo_id, status, stage) VALUES (?, ?, ?)",
            (repo_id, "queued", "queued"),
        )
        return int(cur.lastrowid)


def claim_next_queued_job(conn: sqlite3.Connection) -> dict | None:
    with conn:
        row = conn.execute(
            """
            SELECT id
            FROM jobs
            WHERE status = ?
            ORDER BY created_at, id
            LIMIT 1
            """,
            ("queued",),
        ).fetchone()
        if not row:
            return None
        job_id = int(row["id"])
        updated = conn.execute(
            """
            UPDATE jobs
            SET status = ?, stage = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = ?
            """,
            ("running", "indexing", job_id, "queued"),
        ).rowcount
        if updated != 1:
            return None
    return get_job(conn, job_id)


def mark_interrupted_jobs(conn: sqlite3.Connection) -> int:
    with conn:
        cur = conn.execute(
            """
            UPDATE jobs
            SET status = ?, stage = ?, failure_reason = COALESCE(failure_reason, ?), updated_at = CURRENT_TIMESTAMP
            WHERE status = ?
            """,
            ("interrupted", "interrupted", "Worker stopped before completing this job", "running"),
        )
        return int(cur.rowcount)


def mark_job_running(conn: sqlite3.Connection, job_id: int, stage: str = "indexing") -> None:
    with conn:
        conn.execute(
            "UPDATE jobs SET status = ?, stage = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            ("running", stage, job_id),
        )


def mark_job_succeeded(conn: sqlite3.Connection, job_id: int, snapshot_id: int, counts: dict, diagnostics: list[str]) -> None:
    with conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, stage = ?, snapshot_id = ?, counts_json = ?, diagnostics_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            ("succeeded", "completed", snapshot_id, json.dumps(counts, sort_keys=True), json.dumps(diagnostics), job_id),
        )


def mark_job_failed(conn: sqlite3.Connection, job_id: int, reason: str) -> None:
    with conn:
        conn.execute(
            "UPDATE jobs SET status = ?, stage = ?, failure_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            ("failed", "failed", reason, job_id),
        )


def get_job(conn: sqlite3.Connection, job_id: int) -> dict:
    row = conn.execute(
        """
        SELECT id, repo_id, status, stage, counts_json, diagnostics_json, failure_reason, snapshot_id, created_at, updated_at
        FROM jobs
        WHERE id = ?
        """,
        (job_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Job {job_id} was not found")
    result = dict(row)
    result["counts"] = json.loads(result.pop("counts_json"))
    result["diagnostics"] = json.loads(result.pop("diagnostics_json"))
    return result


def repository_summary(conn: sqlite3.Connection, repo_id: int) -> dict:
    snapshot_id = current_snapshot_id(conn, repo_id)
    snapshot = conn.execute(
        "SELECT id, analyzer_version, counts_json, created_at FROM snapshots WHERE id = ? AND repo_id = ?",
        (snapshot_id, repo_id),
    ).fetchone()
    if not snapshot:
        raise ValueError(f"Snapshot {snapshot_id} was not found")
    languages = [
        dict(row)
        for row in conn.execute(
            """
            SELECT language, COUNT(*) AS file_count
            FROM files
            WHERE repo_id = ? AND snapshot_id = ?
            GROUP BY language
            ORDER BY language
            """,
            (repo_id, snapshot_id),
        ).fetchall()
    ]
    edge_counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT kind, COUNT(*) AS count
            FROM edges
            WHERE repo_id = ? AND snapshot_id = ?
            GROUP BY kind
            ORDER BY kind
            """,
            (repo_id, snapshot_id),
        ).fetchall()
    ]
    return {
        "repo_id": repo_id,
        "snapshot_id": snapshot_id,
        "analyzer_version": snapshot["analyzer_version"],
        "created_at": snapshot["created_at"],
        "counts": json.loads(snapshot["counts_json"]),
        "languages": languages,
        "edge_counts": edge_counts,
    }


def get_node(conn: sqlite3.Connection, repo_id: int, node_id: str) -> dict:
    snapshot_id = current_snapshot_id(conn, repo_id)
    row = conn.execute(
        """
        SELECT id, kind, name, qualified_name, path, signature, enclosing_scope, span_json
        FROM nodes
        WHERE repo_id = ? AND snapshot_id = ? AND id = ?
        """,
        (repo_id, snapshot_id, node_id),
    ).fetchone()
    if not row:
        raise ValueError(f"Node {node_id} was not found")
    result = dict(row)
    result["span"] = json.loads(result.pop("span_json"))
    result["snapshot_id"] = snapshot_id
    result["snippet"] = _source_snippet(repository_root(conn, repo_id), result["path"], result["span"])
    return result


def search_symbols(conn: sqlite3.Connection, repo_id: int, query: str, limit: int = 20) -> list[dict]:
    snapshot_id = current_snapshot_id(conn, repo_id)
    rows = conn.execute(
        """
        SELECT id, kind, name, qualified_name, path, signature
        FROM nodes
        WHERE repo_id = ? AND snapshot_id = ? AND kind != ? AND (name = ? OR name LIKE ? OR qualified_name LIKE ?)
        ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, qualified_name
        LIMIT ?
        """,
        (repo_id, snapshot_id, NodeKind.FILE.value, query, f"{query}%", f"%{query}%", query, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def bounded_graph(
    conn: sqlite3.Connection,
    repo_id: int,
    seed_id: str,
    edge_kinds: set[str],
    direction: str = "outgoing",
    depth: int = 1,
    node_budget: int = 300,
    edge_budget: int = 1000,
) -> dict:
    snapshot_id = current_snapshot_id(conn, repo_id)
    seen = {seed_id: 0}
    frontier = [seed_id]
    witness_edges: list[dict] = []
    truncated = False
    for current_depth in range(1, depth + 1):
        next_frontier: list[str] = []
        for node_id in frontier:
            for edge in _neighbor_edges(conn, repo_id, snapshot_id, node_id, edge_kinds, direction):
                if len(witness_edges) >= edge_budget:
                    truncated = True
                    break
                witness_edges.append(edge)
                other = edge["target_id"] if edge["source_id"] == node_id else edge["source_id"]
                if other not in seen:
                    if len(seen) >= node_budget:
                        truncated = True
                        continue
                    seen[other] = current_depth
                    next_frontier.append(other)
            if truncated:
                break
        frontier = next_frontier
        if not frontier or truncated:
            break
    placeholders = ",".join("?" for _ in seen)
    nodes = []
    if placeholders:
        rows = conn.execute(
            f"SELECT id, kind, name, qualified_name, path FROM nodes WHERE repo_id = ? AND snapshot_id = ? AND id IN ({placeholders})",
            (repo_id, snapshot_id, *seen.keys()),
        ).fetchall()
        nodes = [{**dict(row), "depth": seen[row["id"]]} for row in rows]
    return {
        "snapshot_id": snapshot_id,
        "nodes": nodes,
        "edges": witness_edges,
        "visited_count": len(seen),
        "truncated": truncated,
        "truncation_reason": "budget" if truncated else None,
    }


def current_snapshot_id(conn: sqlite3.Connection, repo_id: int) -> int:
    row = conn.execute("SELECT current_snapshot_id FROM repositories WHERE id = ?", (repo_id,)).fetchone()
    if not row or row["current_snapshot_id"] is None:
        raise ValueError(f"Repository {repo_id} has no completed snapshot")
    return int(row["current_snapshot_id"])


def run_index_job(conn: sqlite3.Connection, job_id: int) -> None:
    from backend.app.ingestion.analyze import analyze_repository

    job = get_job(conn, job_id)
    if job["status"] != "running":
        mark_job_running(conn, job_id)
    try:
        root = repository_root(conn, job["repo_id"])
        analysis = analyze_repository(root)
        _, snapshot_id = publish_analysis(conn, analysis)
        diagnostics = [f"{file.path}: {diag}" for file in analysis.files for diag in file.diagnostics]
        mark_job_succeeded(conn, job_id, snapshot_id, analysis.counts, diagnostics)
    except Exception as exc:  # jobs must persist failure state for polling clients
        mark_job_failed(conn, job_id, str(exc))
        raise


def _repository_id(conn: sqlite3.Connection, root: str) -> int:
    row = conn.execute("SELECT id FROM repositories WHERE root = ?", (root,)).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute("INSERT INTO repositories(root) VALUES (?)", (root,))
    return int(cur.lastrowid)


def _insert_node(conn: sqlite3.Connection, repo_id: int, snapshot_id: int, decl: Declaration) -> None:
    conn.execute(
        """
        INSERT INTO nodes(id, repo_id, snapshot_id, kind, name, qualified_name, path, signature, enclosing_scope, span_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decl.logical_id,
            repo_id,
            snapshot_id,
            decl.kind.value,
            decl.name,
            decl.qualified_name,
            decl.path,
            decl.signature,
            decl.enclosing_scope,
            json.dumps(_asdict(decl.span), sort_keys=True),
        ),
    )


def _neighbor_edges(conn, repo_id: int, snapshot_id: int, node_id: str, edge_kinds: set[str], direction: str) -> list[dict]:
    params = [repo_id, snapshot_id, *sorted(edge_kinds)]
    kind_placeholders = ",".join("?" for _ in edge_kinds)
    clauses = []
    if direction in {"outgoing", "both"}:
        clauses.append(f"source_id = ?")
    if direction in {"incoming", "both"}:
        clauses.append(f"target_id = ?")
    params.extend([node_id] * len(clauses))
    rows = conn.execute(
        f"""
        SELECT kind, source_id, target_id, evidence_json
        FROM edges
        WHERE repo_id = ? AND snapshot_id = ? AND kind IN ({kind_placeholders}) AND ({' OR '.join(clauses)})
        ORDER BY kind, source_id, target_id
        """,
        tuple(params),
    ).fetchall()
    return [{**dict(row), "evidence": json.loads(row["evidence_json"])} for row in rows]


def _asdict(value) -> dict:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _asdict(getattr(value, key)) for key in value.__dataclass_fields__}
    return value


def _source_snippet(root: Path, rel_path: str, span: dict, context: int = 2) -> dict:
    path = (root / rel_path).resolve()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"start_line": None, "end_line": None, "lines": []}
    start_line = max(1, int(span.get("start_line") or 1) - context)
    end_line = min(len(lines), int(span.get("end_line") or 1) + context)
    return {
        "start_line": start_line,
        "end_line": end_line,
        "lines": [
            {"line": number, "text": lines[number - 1]}
            for number in range(start_line, end_line + 1)
        ],
    }
