from pathlib import Path
from shutil import copytree

from backend.app.domain.model import EdgeKind
from backend.app.ingestion.analyze import analyze_repository
from backend.app.storage.sqlite import (
    bounded_graph,
    claim_next_queued_job,
    connect,
    create_job,
    get_job,
    mark_interrupted_jobs,
    publish_analysis,
    register_repository,
    search_symbols,
)


def test_publish_search_and_bounded_graph(tmp_path):
    conn = connect(tmp_path / "codegraph.db")
    analysis = analyze_repository(Path("fixtures/python_demo"))
    repo_id, snapshot_id = publish_analysis(conn, analysis)

    matches = search_symbols(conn, repo_id, "store")

    assert snapshot_id == 1
    assert matches[0]["qualified_name"] == "store"

    graph = bounded_graph(conn, repo_id, matches[0]["id"], {EdgeKind.CALLS.value}, direction="incoming", depth=3)

    assert graph["snapshot_id"] == snapshot_id
    assert any(node["qualified_name"] == "store" for node in graph["nodes"])
    assert graph["truncated"] is False


def test_bounded_graph_depth_three_excludes_fourth_hop(tmp_path):
    conn = connect(tmp_path / "codegraph.db")
    analysis = analyze_repository(Path("fixtures/python_demo"))
    repo_id, _ = publish_analysis(conn, analysis)
    nodes = {row["qualified_name"]: row["id"] for row in search_symbols(conn, repo_id, "", limit=50)}

    graph = bounded_graph(conn, repo_id, nodes["OrderService.submit"], {EdgeKind.CALLS.value}, depth=1)
    qualified = {node["qualified_name"] for node in graph["nodes"]}

    assert "OrderService.submit" in qualified
    assert "validate" in qualified
    assert "store" in qualified
    assert "place_order" not in qualified


def test_jobs_can_be_claimed_and_marked_interrupted(tmp_path):
    conn = connect(tmp_path / "codegraph.db")
    repo_id = register_repository(conn, Path("fixtures/python_demo"))
    job_id = create_job(conn, repo_id)

    claimed = claim_next_queued_job(conn)
    assert claimed["id"] == job_id
    assert get_job(conn, job_id)["status"] == "running"

    assert mark_interrupted_jobs(conn) == 1
    assert get_job(conn, job_id)["status"] == "interrupted"


def test_reindex_publishes_new_snapshot_without_stale_current_nodes(tmp_path):
    repo = tmp_path / "repo"
    copytree(Path("fixtures/python_demo"), repo)
    conn = connect(tmp_path / "codegraph.db")

    first = analyze_repository(repo)
    repo_id, first_snapshot = publish_analysis(conn, first)
    assert search_symbols(conn, repo_id, "requests")

    pyproject = repo / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('  "requests>=2",\n', ""), encoding="utf-8")
    second = analyze_repository(repo)
    _, second_snapshot = publish_analysis(conn, second)

    assert second_snapshot > first_snapshot
    assert search_symbols(conn, repo_id, "requests") == []
