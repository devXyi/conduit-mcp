from __future__ import annotations

import httpx
import pytest

from conduit.auth0_admin import Auth0AdminClient
from conduit.config import Auth0AdminConfig


class FakeAsyncClient:
    def __init__(self, transport: httpx.AsyncBaseTransport, timeout: float = 10.0):
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._client.aclose()

    async def post(self, *args, **kwargs):
        return await self._client.post(*args, **kwargs)

    async def request(self, *args, **kwargs):
        return await self._client.request(*args, **kwargs)


@pytest.mark.asyncio
async def test_management_token_is_cached(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": 3600})
        return httpx.Response(200, json=[{"client_id": "abc", "name": "Example"}])

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "conduit.auth0_admin.httpx.AsyncClient",
        lambda timeout=10.0: FakeAsyncClient(transport, timeout=timeout),
    )

    client = Auth0AdminClient(
        Auth0AdminConfig(
            domain="tenant.eu.auth0.com",
            client_id="id",
            client_secret="secret",
            audience="https://tenant.eu.auth0.com/api/v2/",
        )
    )

    first = await client.list_clients()
    second = await client.list_clients()

    assert first == second == [{"client_id": "abc", "name": "Example"}]
    assert [path for method, path in calls if path.endswith("/oauth/token")] == [
        "https://tenant.eu.auth0.com/oauth/token"
    ]
    assert len([path for method, path in calls if path.endswith("/api/v2/clients")]) == 2


@pytest.mark.asyncio
async def test_management_api_401_refreshes_token(monkeypatch):
    token_calls = 0
    api_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, api_calls
        if request.url.path == "/oauth/token":
            token_calls += 1
            return httpx.Response(200, json={"access_token": f"token-{token_calls}", "expires_in": 3600})
        api_calls += 1
        if api_calls == 1:
            return httpx.Response(401, json={"error": "invalid_token"})
        return httpx.Response(200, json=[{"client_id": "abc"}])

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "conduit.auth0_admin.httpx.AsyncClient",
        lambda timeout=10.0: FakeAsyncClient(transport, timeout=timeout),
    )

    client = Auth0AdminClient(
        Auth0AdminConfig(
            domain="tenant.eu.auth0.com",
            client_id="id",
            client_secret="secret",
            audience="https://tenant.eu.auth0.com/api/v2/",
        )
    )

    assert await client.list_clients() == [{"client_id": "abc"}]
    assert token_calls == 2
    assert api_calls == 2
