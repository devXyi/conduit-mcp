"""Shared fixtures for the test suite."""

from __future__ import annotations

import asyncio

import pytest
import uvicorn

from tests.mock_auth_server import MockAuthServer

AUTH_ISSUER = "https://mock-idp.example.test/"


@pytest.fixture
async def auth_server():
    """Runs MockAuthServer's Starlette app on a real localhost port for the test's duration.

    Yields (server_obj, jwks_url) — server_obj.mint_token(...) signs tokens
    a JWKSTokenVerifier pointed at jwks_url can actually verify.
    """
    server_obj = MockAuthServer(issuer=AUTH_ISSUER)
    config = uvicorn.Config(server_obj.app, host="127.0.0.1", port=0, log_level="warning")
    uv_server = uvicorn.Server(config)
    task = asyncio.create_task(uv_server.serve())
    while not uv_server.started:
        await asyncio.sleep(0.01)
    port = uv_server.servers[0].sockets[0].getsockname()[1]

    try:
        yield server_obj, f"http://127.0.0.1:{port}/jwks.json"
    finally:
        uv_server.should_exit = True
        await task
