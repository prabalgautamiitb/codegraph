from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RepositoryCreateRequest(BaseModel):
    local_path: str | None = Field(default=None, min_length=1)
    github_url: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def exactly_one_source(self) -> "RepositoryCreateRequest":
        if bool(self.local_path) == bool(self.github_url):
            raise ValueError("Provide exactly one of local_path or github_url")
        return self


class RepositoryCreateResponse(BaseModel):
    id: int
    root: str


class IndexJobResponse(BaseModel):
    job_id: int
    status: str


class JobResponse(BaseModel):
    id: int
    repo_id: int
    status: str
    stage: str
    counts: dict
    diagnostics: list[str]
    failure_reason: str | None
    snapshot_id: int | None
    created_at: str
    updated_at: str


class SymbolsResponse(BaseModel):
    snapshot_id: int
    symbols: list[dict]


class GraphResponse(BaseModel):
    snapshot_id: int
    nodes: list[dict]
    edges: list[dict]
    visited_count: int
    truncated: bool
    truncation_reason: str | None


class SummaryResponse(BaseModel):
    repo_id: int
    snapshot_id: int
    analyzer_version: str
    created_at: str
    counts: dict
    languages: list[dict]
    edge_counts: list[dict]


class NodeResponse(BaseModel):
    id: str
    kind: str
    name: str
    qualified_name: str
    path: str
    signature: str
    enclosing_scope: str | None
    span: dict
    snapshot_id: int
    snippet: dict


Direction = Literal["incoming", "outgoing", "both"]
