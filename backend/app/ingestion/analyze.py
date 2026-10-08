from __future__ import annotations

from pathlib import Path

from backend.app.ingestion.discovery import discover_supported_files
from backend.app.parsers.docs_config import parse_markdown, parse_pyproject
from backend.app.parsers.python import PythonParser
from backend.app.resolution.python import resolve_python


def analyze_repository(root: Path):
    root = root.resolve()
    files, counts, all_relative_paths = discover_supported_files(root)
    parser = PythonParser()
    analyses = [parser.parse_file(root, path) for path in files["python"]]
    analyses.extend(parse_markdown(root, path, all_relative_paths) for path in files["markdown"])
    analyses.extend(parse_pyproject(root, path) for path in files["pyproject"])
    return resolve_python(root, analyses, counts)
