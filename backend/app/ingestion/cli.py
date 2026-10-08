from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from backend.app.ingestion.analyze import analyze_repository


def encode(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"Cannot encode {type(value)!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a repository and emit CodeGraph facts as JSON.")
    parser.add_argument("root", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = analyze_repository(args.root)
    print(json.dumps(result, default=encode, indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
