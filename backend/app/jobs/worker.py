from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from backend.app.config import load_local_env
from backend.app.storage.sqlite import claim_next_queued_job, connect, mark_interrupted_jobs, run_index_job


load_local_env()

DEFAULT_DB_PATH = Path(os.environ.get("CODEGRAPH_DB", ".codegraph/codegraph.db"))


def run_worker_once(db_path: Path = DEFAULT_DB_PATH) -> dict | None:
    conn = connect(db_path)
    try:
        job = claim_next_queued_job(conn)
        if not job:
            return None
        run_index_job(conn, job["id"])
        return job
    finally:
        conn.close()


def run_worker_loop(db_path: Path = DEFAULT_DB_PATH, poll_interval: float = 1.0) -> None:
    conn = connect(db_path)
    interrupted = mark_interrupted_jobs(conn)
    if interrupted:
        print(f"Marked {interrupted} interrupted job(s)")
    try:
        while True:
            job = claim_next_queued_job(conn)
            if not job:
                time.sleep(poll_interval)
                continue
            print(f"Running job {job['id']} for repository {job['repo_id']}")
            try:
                run_index_job(conn, job["id"])
                print(f"Completed job {job['id']}")
            except Exception as exc:
                print(f"Failed job {job['id']}: {exc}")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CodeGraph indexing worker.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--once", action="store_true", help="Process at most one queued job and exit.")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()

    if args.once:
        job = run_worker_once(args.db)
        if job:
            print(f"Processed job {job['id']}")
        else:
            print("No queued job")
        return
    run_worker_loop(args.db, args.poll_interval)


if __name__ == "__main__":
    main()
