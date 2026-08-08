"""Integration tests for conduit.tools.github — these hit the real GitHub API.

Marked `integration` since they need network access and share GitHub's
unauthenticated rate limit (60 requests/hour) with everything else on your IP.
Run everything with `pytest`, or skip these with `pytest -m "not integration"`.
"""

import pytest

from conduit.tools.github import GitHubClient, GitHubError

pytestmark = pytest.mark.integration


@pytest.fixture
async def client():
    c = GitHubClient()
    yield c
    await c.aclose()


async def test_repo_info_for_known_repo(client):
    info = await client.repo_info("anthropics", "anthropic-sdk-python")
    assert info["full_name"].lower() == "anthropics/anthropic-sdk-python"
    assert info["stars"] >= 0
    assert info["url"].startswith("https://github.com/")


async def test_repo_info_for_missing_repo_raises(client):
    with pytest.raises(GitHubError):
        await client.repo_info("anthropics", "this-repo-should-not-exist-xyz123")


async def test_search_repos_returns_bounded_results(client):
    results = await client.search_repos("mcp server language:python", limit=3)
    assert 0 < len(results) <= 3
    assert all("full_name" in r for r in results)


async def test_search_repos_empty_query_rejected(client):
    with pytest.raises(GitHubError):
        await client.search_repos("")


async def test_user_profile_for_known_user(client):
    profile = await client.user_profile("torvalds")
    assert profile["login"] == "torvalds"
    assert profile["public_repos"] >= 0
