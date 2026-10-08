from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha1
from pathlib import Path
from typing import Any


ANALYZER_VERSION = "0.1.0"


class NodeKind(StrEnum):
    REPOSITORY = "Repository"
    FILE = "File"
    CLASS = "Class"
    FUNCTION = "Function"
    METHOD = "Method"
    DOCUMENT = "Document"
    CONFIG = "Config"
    DEPENDENCY = "Dependency"


class EdgeKind(StrEnum):
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    INHERITS = "INHERITS"
    DECLARES_DEPENDENCY = "DECLARES_DEPENDENCY"
    REFERENCES = "REFERENCES"


class ImportKind(StrEnum):
    IMPORT = "import"
    FROM_IMPORT = "from_import"
    DYNAMIC = "dynamic"


@dataclass(frozen=True)
class SourceSpan:
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    start_col: int
    end_col: int

    @classmethod
    def from_node(cls, node: Any) -> "SourceSpan":
        return cls(
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_col=node.start_point[1],
            end_col=node.end_point[1],
        )

    @classmethod
    def from_offsets(
        cls,
        source: str,
        start_byte: int,
        end_byte: int,
    ) -> "SourceSpan":
        prefix = source.encode("utf-8")[:start_byte].decode("utf-8", errors="ignore")
        selected_prefix = source.encode("utf-8")[:end_byte].decode("utf-8", errors="ignore")
        start_line = prefix.count("\n") + 1
        end_line = selected_prefix.count("\n") + 1
        start_col = len(prefix.rsplit("\n", 1)[-1].encode("utf-8"))
        end_col = len(selected_prefix.rsplit("\n", 1)[-1].encode("utf-8"))
        return cls(start_byte, end_byte, start_line, end_line, start_col, end_col)


@dataclass(frozen=True)
class Evidence:
    path: str
    span: SourceSpan
    rule: str
    status: str = "resolved"


@dataclass(frozen=True)
class Declaration:
    path: str
    kind: NodeKind
    name: str
    qualified_name: str
    signature: str
    enclosing_scope: str | None
    span: SourceSpan
    logical_id: str


@dataclass(frozen=True)
class ImportFact:
    path: str
    kind: ImportKind
    module: str
    name: str | None
    alias: str | None
    level: int
    span: SourceSpan
    raw: str

    @property
    def binding_name(self) -> str:
        if self.alias:
            return self.alias
        if self.kind == ImportKind.IMPORT:
            return self.module.split(".", 1)[0]
        return self.name or self.module.rsplit(".", 1)[-1]


@dataclass(frozen=True)
class CallSite:
    path: str
    caller_logical_id: str | None
    expression: str
    function_name: str
    receiver: str | None
    span: SourceSpan


@dataclass(frozen=True)
class InheritanceSite:
    path: str
    subclass_logical_id: str
    parent_name: str
    span: SourceSpan


@dataclass(frozen=True)
class Edge:
    kind: EdgeKind
    source_id: str
    target_id: str
    evidence: Evidence


@dataclass(frozen=True)
class UnresolvedReference:
    path: str
    kind: str
    expression: str
    reason: str
    span: SourceSpan


@dataclass
class FileAnalysis:
    path: str
    language: str
    file_hash: str
    declarations: list[Declaration] = field(default_factory=list)
    imports: list[ImportFact] = field(default_factory=list)
    call_sites: list[CallSite] = field(default_factory=list)
    inheritance_sites: list[InheritanceSite] = field(default_factory=list)
    contains_edges: list[Edge] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class RepositoryAnalysis:
    root: str
    analyzer_version: str
    files: list[FileAnalysis]
    edges: list[Edge]
    unresolved_references: list[UnresolvedReference]
    counts: dict[str, int]


def stable_logical_id(path: str, kind: NodeKind, qualified_name: str, signature: str = "") -> str:
    key = f"{Path(path).as_posix()}::{kind.value}::{qualified_name}::{signature}"
    return sha1(key.encode("utf-8")).hexdigest()
