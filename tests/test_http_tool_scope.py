from __future__ import annotations

import asyncio
import os
import socket
from contextlib import closing
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_read_scope_cannot_invoke_auth0_admin_tool(auth_server):
    mock_as, jwks_url = auth_server
    port = _free_port()
    audience = f"http://127.0.0.1:{port}/mcp"
    env = {
        **os.environ,
        "CONDUIT_AUTH_ISSUER": mock_as.issuer,
        "CONDUIT_AUTH_JWKS_URL": jwks_url,
        "CONDUIT_AUTH_AUDIENCE": audience,
    }

    proc = await asyncio.create_subprocess_exec(
        __import__("sys").executable,
        "-m",
        "conduit",
        "--transport",
        "http",
        "--port",
        str(port),
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        mcp_url = f"http://127.0.0.1:{port}/mcp"
        token = mock_as.mint_token(audience=audience, scopes=["conduit:read"])
        last_error: Exception | None = None

        for _ in range(50):
            await asyncio.sleep(0.1)
            try:
                async with streamable_http_client(
                    mcp_url,
                    headers={"Authorization": f"Bearer {token}"},
                ) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            "auth0_get_application",
                            {"client_id": "not-used"},
                        )
                        assert result.is_error
                        text = " ".join(
                            block.text for block in result.content if hasattr(block, "text")
                        )
                        assert "conduit:admin" in text
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc

        pytest.fail(f"HTTP server did not become ready in time: {last_error}")
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
