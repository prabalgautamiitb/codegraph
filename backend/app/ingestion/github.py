from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


GITHUB_REPO = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


def normalize_public_github_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("Only public https://github.com/owner/repository URLs are supported")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("GitHub URL must not contain credentials, query parameters or fragments")
    match = GITHUB_REPO.match(parsed.path)
    if not match:
        raise ValueError("GitHub URL must point to a repository root")
    owner, repo = match.groups()
    normalized = f"https://github.com/{owner}/{repo}.git"
    return normalized, owner, repo


def clone_public_github_repo(url: str, imports_root: Path, timeout_seconds: int = 60) -> Path:
    normalized, owner, repo = normalize_public_github_url(url)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    destination = (imports_root / f"{owner}_{repo}_{digest}").resolve()
    imports_root.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)

    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_LFS_SKIP_SMUDGE": "1",
    }
    command = [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "protocol.file.allow=never",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--no-tags",
        "--recurse-submodules=no",
        normalized,
        str(destination),
    ]
    try:
        subprocess.run(command, check=True, env=env, timeout=timeout_seconds, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        raise
    return destination
