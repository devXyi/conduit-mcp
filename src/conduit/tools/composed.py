"""Composed tools: server-side orchestration across more than one backend.

Everything in files.py and github.py does exactly one thing. This module is
where more than one of those gets combined into a single tool call — the
interesting part isn't the combining (that's a function call), it's doing it
*well*: running independent lookups concurrently instead of serially, and
degrading gracefully when one leg fails instead of taking the whole result
down with it. Contrast this with an MCP *prompt* like `repo_health_check`,
which just tells the agent which tools to call in what order — the
orchestration there happens client-side, one round trip per step. This
happens server-side, in one round trip, with real concurrency.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .files import Workspace, WorkspaceError
from .github import GitHubClient, GitHubError


async def research_repo(github: GitHubClient, workspace: Workspace, owner: str, repo: str) -> dict[str, Any]:
    """Repo metadata + comparable repos + any workspace notes that already mention it.

    `repo_info` runs first because the other two legs either need its
    result (the language, to search for comparable projects) or simply
    don't depend on it (the workspace search) and have no reason to wait
    for it anyway once it's kicked off. Either second-stage leg failing
    doesn't take the whole call down — `errors` reports what broke, and
    `repo_info` still comes back if it's the piece that succeeded.
    """
    errors: dict[str, str] = {}

    try:
        repo_info = await github.repo_info(owner, repo)
    except GitHubError as exc:
        return {"repo_info": None, "similar_repos": [], "workspace_mentions": [], "errors": {"repo_info": str(exc)}}

    language = repo_info.get("language")
    similar_query = f"{repo} language:{language}" if language else repo

    async def _similar() -> list[dict]:
        try:
            results = await github.search_repos(similar_query, limit=5)
            return [r for r in results if r["full_name"].lower() != f"{owner}/{repo}".lower()]
        except GitHubError as exc:
            errors["similar_repos"] = str(exc)
            return []

    async def _mentions() -> list[dict]:
        try:
            return workspace.search(repo)
        except WorkspaceError as exc:
            errors["workspace_mentions"] = str(exc)
            return []

    similar_repos, workspace_mentions = await asyncio.gather(_similar(), _mentions())

    return {
        "repo_info": repo_info,
        "similar_repos": similar_repos,
        "workspace_mentions": workspace_mentions,
        "errors": errors,
    }
