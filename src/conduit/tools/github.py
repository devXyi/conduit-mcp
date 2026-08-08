"""A small async client for the slice of the public GitHub REST API Conduit exposes.

Unauthenticated requests share GitHub's 60-requests/hour rate limit for your
IP. Set GITHUB_TOKEN (a token with no scopes is enough for public data) to
raise that to 5,000/hour — see https://github.com/settings/tokens.
"""

from __future__ import annotations

import httpx

API_BASE = "https://api.github.com"


class GitHubError(Exception):
    """Raised when the GitHub API can't be reached or returns an error response."""


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        base_url: str = API_BASE,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "conduit-mcp",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # `transport` is an injection point for tests (httpx.MockTransport) so the
        # JSON-mapping logic below can be verified without hitting the real API.
        self._client = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            resp = await self._client.get(path, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 404:
                raise GitHubError(f"GitHub returned 404 for {path} — check the spelling") from exc
            if status == 403:
                raise GitHubError(
                    "GitHub rate-limited this request (60/hour unauthenticated). "
                    "Set GITHUB_TOKEN to raise the limit."
                ) from exc
            raise GitHubError(f"GitHub API error {status} for {path}") from exc
        except httpx.RequestError as exc:
            raise GitHubError(f"Could not reach the GitHub API: {exc}") from exc
        return resp.json()

    async def repo_info(self, owner: str, repo: str) -> dict:
        data = await self._get(f"/repos/{owner}/{repo}")
        return {
            "full_name": data["full_name"],
            "description": data.get("description"),
            "stars": data["stargazers_count"],
            "forks": data["forks_count"],
            "open_issues": data["open_issues_count"],
            "language": data.get("language"),
            "default_branch": data.get("default_branch"),
            "pushed_at": data.get("pushed_at"),
            "url": data["html_url"],
        }

    async def search_repos(self, query: str, limit: int = 5) -> list[dict]:
        if not query:
            raise GitHubError("Search query cannot be empty")
        data = await self._get("/search/repositories", params={"q": query, "per_page": max(1, min(limit, 20))})
        return [
            {
                "full_name": item["full_name"],
                "description": item.get("description"),
                "stars": item["stargazers_count"],
                "url": item["html_url"],
            }
            for item in data.get("items", [])
        ]

    async def user_profile(self, username: str) -> dict:
        data = await self._get(f"/users/{username}")
        return {
            "login": data["login"],
            "name": data.get("name"),
            "bio": data.get("bio"),
            "public_repos": data["public_repos"],
            "followers": data["followers"],
            "company": data.get("company"),
            "location": data.get("location"),
            "url": data["html_url"],
        }
