from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.jobs.worker import run_worker_once


def auth(token: str = "test-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_api_primary_local_repository_journey(tmp_path):
    fixture = Path("fixtures/python_demo").resolve()
    db_path = tmp_path / "codegraph.db"
    app = create_app(
        db_path=db_path,
        api_token="test-token",
        allowed_roots=[fixture.parent],
        cors_origins=[],
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/repositories",
            json={"local_path": str(fixture)},
            headers=auth(),
        )
        assert create_response.status_code == 200
        repo_id = create_response.json()["id"]

        index_response = client.post(f"/api/repositories/{repo_id}/index", headers=auth())
        assert index_response.status_code == 202
        job_id = index_response.json()["job_id"]
        assert index_response.json()["status"] == "queued"

        job_response = client.get(f"/api/jobs/{job_id}")
        assert job_response.status_code == 200
        assert job_response.json()["status"] == "queued"

        processed = run_worker_once(db_path)
        assert processed["id"] == job_id

        job_response = client.get(f"/api/jobs/{job_id}")
        assert job_response.status_code == 200
        assert job_response.json()["status"] == "succeeded"
        assert job_response.json()["counts"]["declarations"] >= 8

        summary_response = client.get(f"/api/repositories/{repo_id}/summary")
        assert summary_response.status_code == 200
        assert summary_response.json()["counts"]["parse_errors"] == 1

        symbols_response = client.get(f"/api/repositories/{repo_id}/symbols", params={"q": "store"})
        assert symbols_response.status_code == 200
        store = symbols_response.json()["symbols"][0]
        assert store["qualified_name"] == "store"

        graph_response = client.get(
            f"/api/repositories/{repo_id}/graph",
            params={"seed_node_id": store["id"], "edge_types": "CALLS", "direction": "incoming", "depth": 3},
        )
        assert graph_response.status_code == 200
        assert graph_response.json()["visited_count"] >= 2

        node_response = client.get(f"/api/repositories/{repo_id}/nodes/{store['id']}")
        assert node_response.status_code == 200
        assert node_response.json()["snippet"]["lines"]


def test_api_rejects_missing_token_for_mutation(tmp_path):
    fixture = Path("fixtures/python_demo").resolve()
    app = create_app(db_path=tmp_path / "codegraph.db", api_token="test-token", allowed_roots=[fixture.parent], cors_origins=[])

    with TestClient(app) as client:
        response = client.post("/api/repositories", json={"local_path": str(fixture)})

    assert response.status_code == 401


def test_api_rejects_unallowlisted_local_path(tmp_path):
    fixture = Path("fixtures/python_demo").resolve()
    app = create_app(db_path=tmp_path / "codegraph.db", api_token="test-token", allowed_roots=[tmp_path], cors_origins=[])

    with TestClient(app) as client:
        response = client.post("/api/repositories", json={"local_path": str(fixture)}, headers=auth())

    assert response.status_code == 403


def test_api_rejects_non_github_import_url(tmp_path):
    fixture = Path("fixtures/python_demo").resolve()
    app = create_app(db_path=tmp_path / "codegraph.db", api_token="test-token", allowed_roots=[fixture.parent], cors_origins=[])

    with TestClient(app) as client:
        response = client.post("/api/repositories", json={"github_url": "https://example.com/not/a-repo"}, headers=auth())

    assert response.status_code == 400
