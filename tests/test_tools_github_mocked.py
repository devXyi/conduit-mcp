"""Deterministic tests for conduit.tools.github's response-mapping and error
handling, using httpx.MockTransport instead of the real network.

These complement test_tools_github.py: that file proves the client works
against the real API (and is at the mercy of GitHub's rate limit), this file
proves the field-mapping and error logic is correct regardless of network
conditions, quota, or GitHub being reachable at all.
"""

from __future__ import annotations

import httpx
import pytest

from conduit.tools.github import GitHubClient, GitHubError


def _client(handler) -> GitHubClient:
    return GitHubClient(transport=httpx.MockTransport(handler))


async def test_repo_info_maps_expected_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/anthropics/mcp"
        return httpx.Response(
            200,
            json={
                "full_name": "anthropics/mcp",
                "description": "The Model Context Protocol",
                "stargazers_count": 1000,
                "forks_count": 100,
                "open_issues_count": 12,
                "language": "Python",
                "default_branch": "main",
                "pushed_at": "2026-08-01T00:00:00Z",
                "html_url": "https://github.com/anthropics/mcp",
            },
        )

    client = _client(handler)
    try:
        info = await client.repo_info("anthropics", "mcp")
        assert info == {
            "full_name": "anthropics/mcp",
            "description": "The Model Context Protocol",
            "stars": 1000,
            "forks": 100,
            "open_issues": 12,
            "language": "Python",
            "default_branch": "main",
            "pushed_at": "2026-08-01T00:00:00Z",
            "url": "https://github.com/anthropics/mcp",
        }
    finally:
        await client.aclose()


async def test_repo_info_404_raises_github_error_with_helpful_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    client = _client(handler)
    try:
        with pytest.raises(GitHubError, match="404"):
            await client.repo_info("nobody", "nothing")
    finally:
        await client.aclose()


async def test_repo_info_403_raises_rate_limit_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "rate limit exceeded"})

    client = _client(handler)
    try:
        with pytest.raises(GitHubError, match="rate-limited"):
            await client.repo_info("anthropics", "mcp")
    finally:
        await client.aclose()


async def test_search_repos_maps_result_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search/repositories"
        assert request.url.params["q"] == "mcp server"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "full_name": "a/one",
                        "description": "first",
                        "stargazers_count": 5,
                        "html_url": "https://github.com/a/one",
                    },
                    {
                        "full_name": "b/two",
                        "description": None,
                        "stargazers_count": 2,
                        "html_url": "https://github.com/b/two",
                    },
                ]
            },
        )

    client = _client(handler)
    try:
        results = await client.search_repos("mcp server", limit=5)
        assert [r["full_name"] for r in results] == ["a/one", "b/two"]
        assert results[1]["description"] is None
    finally:
        await client.aclose()


async def test_search_repos_limit_is_clamped_into_1_to_20():
    seen_per_page = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_per_page["value"] = request.url.params["per_page"]
        return httpx.Response(200, json={"items": []})

    client = _client(handler)
    try:
        await client.search_repos("query", limit=999)
        assert seen_per_page["value"] == "20"

        await client.search_repos("query", limit=0)
        assert seen_per_page["value"] == "1"
    finally:
        await client.aclose()


async def test_user_profile_maps_expected_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/users/torvalds"
        return httpx.Response(
            200,
            json={
                "login": "torvalds",
                "name": "Linus Torvalds",
                "bio": None,
                "public_repos": 10,
                "followers": 200000,
                "company": None,
                "location": "Portland, OR",
                "html_url": "https://github.com/torvalds",
            },
        )

    client = _client(handler)
    try:
        profile = await client.user_profile("torvalds")
        assert profile["login"] == "torvalds"
        assert profile["followers"] == 200000
        assert profile["location"] == "Portland, OR"
    finally:
        await client.aclose()


async def test_unreachable_host_raises_github_error_not_httpx_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    client = _client(handler)
    try:
        with pytest.raises(GitHubError, match="Could not reach"):
            await client.repo_info("anthropics", "mcp")
    finally:
        await client.aclose()
