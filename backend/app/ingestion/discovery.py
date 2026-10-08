from __future__ import annotations

from pathlib import Path


DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
}


def discover_supported_files(root: Path) -> tuple[dict[str, list[Path]], dict[str, int], set[str]]:
    root = root.resolve()
    supported: dict[str, list[Path]] = {"python": [], "markdown": [], "pyproject": []}
    counts = {"supported": 0, "unsupported": 0, "excluded": 0}
    all_relative_paths: set[str] = set()
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if path.is_symlink() or any(part in DEFAULT_EXCLUDES for part in rel_parts):
            counts["excluded"] += 1
            continue
        if path.is_dir():
            continue
        rel_path = path.relative_to(root).as_posix()
        all_relative_paths.add(rel_path)
        if path.suffix == ".py":
            supported["python"].append(path)
            counts["supported"] += 1
        elif path.suffix.lower() == ".md":
            supported["markdown"].append(path)
            counts["supported"] += 1
        elif path.name == "pyproject.toml":
            supported["pyproject"].append(path)
            counts["supported"] += 1
        else:
            counts["unsupported"] += 1
    return supported, counts, all_relative_paths


def discover_python_files(root: Path) -> tuple[list[Path], dict[str, int]]:
    supported, counts, _ = discover_supported_files(root)
    return supported["python"], counts
