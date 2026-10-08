import pytest

from backend.app.ingestion.github import normalize_public_github_url


def test_normalize_public_github_url_accepts_repo_root():
    normalized, owner, repo = normalize_public_github_url("https://github.com/openai/openai-python")

    assert normalized == "https://github.com/openai/openai-python.git"
    assert owner == "openai"
    assert repo == "openai-python"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/openai/openai-python",
        "https://example.com/openai/openai-python",
        "https://token@github.com/openai/openai-python",
        "https://github.com/openai/openai-python/issues",
        "https://github.com/openai/openai-python?tab=readme",
    ],
)
def test_normalize_public_github_url_rejects_unsafe_or_non_repo_urls(url):
    with pytest.raises(ValueError):
        normalize_public_github_url(url)
