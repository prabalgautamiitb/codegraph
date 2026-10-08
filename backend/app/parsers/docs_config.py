from __future__ import annotations

import re
import tomllib
from hashlib import sha256
from pathlib import Path

from backend.app.domain.model import (
    Declaration,
    Edge,
    EdgeKind,
    Evidence,
    FileAnalysis,
    NodeKind,
    SourceSpan,
    stable_logical_id,
)


MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def parse_markdown(root: Path, path: Path, all_relative_paths: set[str]) -> FileAnalysis:
    rel_path = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    file_hash = sha256(text.encode("utf-8")).hexdigest()
    file_id = stable_logical_id(rel_path, NodeKind.FILE, rel_path)
    doc_id = stable_logical_id(rel_path, NodeKind.DOCUMENT, rel_path)
    span = _whole_file_span(text)
    analysis = FileAnalysis(path=rel_path, language="markdown", file_hash=file_hash)
    analysis.declarations.append(
        Declaration(rel_path, NodeKind.DOCUMENT, Path(rel_path).name, rel_path, "", file_id, span, doc_id)
    )
    analysis.contains_edges.append(
        Edge(EdgeKind.CONTAINS, file_id, doc_id, Evidence(rel_path, span, "markdown.document"))
    )

    for match in MARKDOWN_LINK.finditer(text):
        target = match.group(1).split("#", 1)[0].strip()
        if not target or _is_external_link(target):
            continue
        resolved = (Path(rel_path).parent / target).as_posix()
        normalized = Path(resolved).as_posix()
        if normalized in all_relative_paths:
            target_id = stable_logical_id(normalized, NodeKind.FILE, normalized)
            link_span = SourceSpan.from_offsets(text, len(text[: match.start()].encode("utf-8")), len(text[: match.end()].encode("utf-8")))
            analysis.contains_edges.append(
                Edge(EdgeKind.REFERENCES, doc_id, target_id, Evidence(rel_path, link_span, "markdown.relative_link"))
            )
    return analysis


def parse_pyproject(root: Path, path: Path) -> FileAnalysis:
    rel_path = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    file_hash = sha256(text.encode("utf-8")).hexdigest()
    file_id = stable_logical_id(rel_path, NodeKind.FILE, rel_path)
    config_id = stable_logical_id(rel_path, NodeKind.CONFIG, rel_path)
    span = _whole_file_span(text)
    analysis = FileAnalysis(path=rel_path, language="toml", file_hash=file_hash)
    analysis.declarations.append(
        Declaration(rel_path, NodeKind.CONFIG, Path(rel_path).name, rel_path, "", file_id, span, config_id)
    )
    analysis.contains_edges.append(
        Edge(EdgeKind.CONTAINS, file_id, config_id, Evidence(rel_path, span, "toml.config"))
    )

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        analysis.diagnostics.append(f"toml_parse_error:{exc.lineno}")
        return analysis

    dependencies = _pyproject_dependencies(data)
    for raw_dep in dependencies:
        dep_name = _dependency_name(raw_dep)
        if not dep_name:
            continue
        dep_id = stable_logical_id(rel_path, NodeKind.DEPENDENCY, dep_name.lower())
        dep_span = _line_span_for_text(text, raw_dep)
        analysis.declarations.append(
            Declaration(rel_path, NodeKind.DEPENDENCY, dep_name, dep_name.lower(), "", config_id, dep_span, dep_id)
        )
        analysis.contains_edges.append(
            Edge(EdgeKind.DECLARES_DEPENDENCY, config_id, dep_id, Evidence(rel_path, dep_span, "pyproject.dependency"))
        )
    return analysis


def _pyproject_dependencies(data: dict) -> list[str]:
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    deps = list(project.get("dependencies") or [])
    optional = project.get("optional-dependencies") or {}
    if isinstance(optional, dict):
        for group_deps in optional.values():
            deps.extend(group_deps or [])
    poetry = data.get("tool", {}).get("poetry", {}) if isinstance(data.get("tool"), dict) else {}
    poetry_deps = poetry.get("dependencies") if isinstance(poetry, dict) else {}
    if isinstance(poetry_deps, dict):
        deps.extend(name for name in poetry_deps if name.lower() != "python")
    return [dep for dep in deps if isinstance(dep, str)]


def _dependency_name(raw: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", raw)
    return match.group(1) if match else ""


def _line_span_for_text(source: str, needle: str) -> SourceSpan:
    char_start = source.find(needle)
    if char_start < 0:
        return _whole_file_span(source)
    start_byte = len(source[:char_start].encode("utf-8"))
    end_byte = start_byte + len(needle.encode("utf-8"))
    return SourceSpan.from_offsets(source, start_byte, end_byte)


def _whole_file_span(source: str) -> SourceSpan:
    encoded = source.encode("utf-8")
    return SourceSpan.from_offsets(source, 0, len(encoded))


def _is_external_link(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#"))
