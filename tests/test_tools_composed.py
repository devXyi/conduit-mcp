"""Tests for conduit.tools.composed.research_repo — concurrency and
partial-failure behavior, with GitHub mocked so every failure mode is
reachable on demand rather than waiting for the real API to misbehave.
"""

from __future__ import annotations

import httpx
import pytest

from conduit.tools.composed import research_repo
from conduit.tools.files import Workspace, WorkspaceError
from conduit.tools.github import GitHubClient


def _github(handler) -> GitHubClient:
    return GitHubClient(transport=httpx.MockTransport(handler))


def _ok_repo_info(owner: str, repo: str, language: str = "Python") -> dict:
    return {
        "full_name": f"{owner}/{repo}",
        "stargazers_count": 10,
        "forks_count": 2,
        "open_issues_count": 1,
        "language": language,
        "default_branch": "main",
        "html_url": f"https://github.com/{owner}/{repo}",
    }


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "workspace")


async def test_happy_path_runs_both_legs_and_reports_no_errors(workspace):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/anthropics/mcp":
            return httpx.Response(200, json=_ok_repo_info("anthropics", "mcp"))
        if request.url.path == "/search/repositories":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"full_name": "anthropics/mcp", "stargazers_count": 10, "html_url": "x"},  # self — filtered
                        {"full_name": "other/similar-project", "stargazers_count": 5, "html_url": "y"},
                    ]
                },
            )
        return httpx.Response(404, json={})

    workspace.write_file("notes/mcp.md", "Notes about anthropics/mcp integration.")
    github = _github(handler)
    try:
        result = await research_repo(github, workspace, "anthropics", "mcp")
    finally:
        await github.aclose()

    assert result["repo_info"]["full_name"] == "anthropics/mcp"
    assert [r["full_name"] for r in result["similar_repos"]] == ["other/similar-project"]  # self excluded
    assert len(result["workspace_mentions"]) == 1
    assert result["errors"] == {}


async def test_repo_info_failure_short_circuits_with_a_clear_error(workspace):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    github = _github(handler)
    try:
        result = await research_repo(github, workspace, "nobody", "nothing")
    finally:
        await github.aclose()

    assert result["repo_info"] is None
    assert result["similar_repos"] == []
    assert result["workspace_mentions"] == []
    assert "repo_info" in result["errors"]


async def test_similar_repos_failure_still_returns_repo_info_and_mentions(workspace):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/anthropics/mcp":
            return httpx.Response(200, json=_ok_repo_info("anthropics", "mcp"))
        if request.url.path == "/search/repositories":
            return httpx.Response(403, json={"message": "rate limit exceeded"})
        return httpx.Response(404, json={})

    workspace.write_file("notes/mcp.md", "mcp is great")
    github = _github(handler)
    try:
        result = await research_repo(github, workspace, "anthropics", "mcp")
    finally:
        await github.aclose()

    assert result["repo_info"] is not None  # the leg that succeeded still comes back
    assert result["similar_repos"] == []  # the leg that failed degrades to empty, not an exception
    assert len(result["workspace_mentions"]) == 1  # unrelated leg is unaffected
    assert "similar_repos" in result["errors"]
    assert "workspace_mentions" not in result["errors"]


async def test_both_second_stage_legs_can_fail_independently(workspace, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/anthropics/mcp":
            return httpx.Response(200, json=_ok_repo_info("anthropics", "mcp"))
        return httpx.Response(403, json={"message": "rate limit exceeded"})

    def _broken_search(*args, **kwargs):
        raise WorkspaceError("simulated workspace failure")

    monkeypatch.setattr(workspace, "search", _broken_search)
    github = _github(handler)
    try:
        result = await research_repo(github, workspace, "anthropics", "mcp")
    finally:
        await github.aclose()

    assert result["repo_info"] is not None  # the one leg with no failure injected still comes back
    assert result["similar_repos"] == []
    assert result["workspace_mentions"] == []
    assert "similar_repos" in result["errors"]
    assert "workspace_mentions" in result["errors"]


async def test_query_includes_language_when_known(workspace):
    seen_queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/anthropics/mcp":
            return httpx.Response(200, json=_ok_repo_info("anthropics", "mcp", language="Rust"))
        if request.url.path == "/search/repositories":
            seen_queries.append(request.url.params["q"])
            return httpx.Response(200, json={"items": []})
        return httpx.Response(404, json={})

    github = _github(handler)
    try:
        await research_repo(github, workspace, "anthropics", "mcp")
    finally:
        await github.aclose()

    assert seen_queries == ["mcp language:Rust"]
