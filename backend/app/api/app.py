from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import load_local_env
from backend.app.api.schemas import (
    Direction,
    GraphResponse,
    IndexJobResponse,
    JobResponse,
    NodeResponse,
    RepositoryCreateRequest,
    RepositoryCreateResponse,
    SummaryResponse,
    SymbolsResponse,
)
from backend.app.ingestion.github import clone_public_github_repo
from backend.app.storage.sqlite import (
    bounded_graph,
    connect,
    create_job,
    current_snapshot_id,
    get_job,
    get_node,
    register_repository,
    repository_root,
    repository_summary,
    search_symbols,
)


load_local_env()

DEFAULT_DB_PATH = Path(os.environ.get("CODEGRAPH_DB", ".codegraph/codegraph.db"))
DEFAULT_TOKEN = os.environ.get("CODEGRAPH_API_TOKEN", "dev-local-token")
DEFAULT_ALLOWED_ROOTS = os.environ.get("CODEGRAPH_ALLOWED_ROOTS", str(Path.cwd()))
DEFAULT_CORS_ORIGINS = os.environ.get("CODEGRAPH_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
DEFAULT_IMPORTS_ROOT = Path(os.environ.get("CODEGRAPH_IMPORTS_ROOT", ".codegraph/imports"))


def create_app(
    db_path: Path = DEFAULT_DB_PATH,
    api_token: str = DEFAULT_TOKEN,
    allowed_roots: list[Path] | None = None,
    cors_origins: list[str] | None = None,
    run_jobs_inline: bool = False,
    imports_root: Path = DEFAULT_IMPORTS_ROOT,
) -> FastAPI:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    roots = [p.resolve() for p in (allowed_roots or [Path(p) for p in DEFAULT_ALLOWED_ROOTS.split(os.pathsep) if p])]
    origins = cors_origins or [origin for origin in DEFAULT_CORS_ORIGINS.split(",") if origin]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            app.state.conn.close()

    app = FastAPI(title="CodeGraph API", version="0.1.0", lifespan=lifespan)
    app.state.conn = conn
    app.state.api_token = api_token
    app.state.allowed_roots = roots
    app.state.run_jobs_inline = run_jobs_inline
    app.state.imports_root = imports_root
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/repositories", response_model=RepositoryCreateResponse)
    def create_repository(
        request: RepositoryCreateRequest,
        _: Annotated[None, Depends(require_token)],
    ) -> RepositoryCreateResponse:
        if request.github_url:
            try:
                root = clone_public_github_repo(request.github_url, app.state.imports_root)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"GitHub clone failed: {exc}") from exc
        else:
            root = _validate_allowed_root(Path(request.local_path or ""), app.state.allowed_roots)
        repo_id = register_repository(app.state.conn, root)
        return RepositoryCreateResponse(id=repo_id, root=str(root))

    @app.post("/api/repositories/{repo_id}/index", response_model=IndexJobResponse, status_code=status.HTTP_202_ACCEPTED)
    def index_repository(
        repo_id: int,
        _: Annotated[None, Depends(require_token)],
    ) -> IndexJobResponse:
        try:
            repository_root(app.state.conn, repo_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        job_id = create_job(app.state.conn, repo_id)
        return IndexJobResponse(job_id=job_id, status=get_job(app.state.conn, job_id)["status"])

    @app.get("/api/jobs/{job_id}", response_model=JobResponse)
    def read_job(job_id: int) -> JobResponse:
        try:
            return JobResponse(**get_job(app.state.conn, job_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/repositories/{repo_id}/summary", response_model=SummaryResponse)
    def summary(repo_id: int) -> SummaryResponse:
        try:
            return SummaryResponse(**repository_summary(app.state.conn, repo_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/repositories/{repo_id}/symbols", response_model=SymbolsResponse)
    def symbols(
        repo_id: int,
        q: str = "",
        limit: int = Query(default=20, ge=1, le=100),
    ) -> SymbolsResponse:
        try:
            return SymbolsResponse(snapshot_id=current_snapshot_id(app.state.conn, repo_id), symbols=search_symbols(app.state.conn, repo_id, q, limit))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/repositories/{repo_id}/graph", response_model=GraphResponse)
    def graph(
        repo_id: int,
        seed_node_id: str,
        edge_types: str = "CALLS,INHERITS,IMPORTS,CONTAINS",
        direction: Direction = "outgoing",
        depth: int = Query(default=1, ge=1, le=3),
        node_budget: int = Query(default=300, ge=1, le=300),
        edge_budget: int = Query(default=1000, ge=1, le=1000),
    ) -> GraphResponse:
        kinds = {part.strip().upper() for part in edge_types.split(",") if part.strip()}
        if not kinds:
            raise HTTPException(status_code=422, detail="edge_types must include at least one edge kind")
        try:
            return GraphResponse(**bounded_graph(app.state.conn, repo_id, seed_node_id, kinds, direction, depth, node_budget, edge_budget))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/repositories/{repo_id}/nodes/{node_id}", response_model=NodeResponse)
    def node(repo_id: int, node_id: str) -> NodeResponse:
        try:
            return NodeResponse(**get_node(app.state.conn, repo_id, node_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


def require_token(request: Request, authorization: Annotated[str | None, Header()] = None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, request.app.state.api_token):
        raise HTTPException(status_code=403, detail="Invalid bearer token")


def _validate_allowed_root(path: Path, allowed_roots: list[Path]) -> Path:
    root = path.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="local_path must be an existing directory")
    if root.is_symlink():
        raise HTTPException(status_code=400, detail="local_path must not be a symlink")
    if not any(root == allowed or root.is_relative_to(allowed) for allowed in allowed_roots):
        raise HTTPException(status_code=403, detail="local_path is outside configured allowed roots")
    return root


app = create_app()
