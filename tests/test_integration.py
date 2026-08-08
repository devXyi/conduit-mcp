"""End-to-end tests that speak real MCP: an in-process client for fast checks
on tool/prompt wiring, a real stdio subprocess for the stdio transport, and a
real HTTP round trip for the Streamable HTTP transport. If these pass, an
actual MCP client (Claude Desktop, Claude Code, a custom agent) can talk to
Conduit exactly as tested here.

Marked `integration`: the GitHub-backed cases need network, and the
transport tests spawn real subprocesses. Run everything with `pytest`, or
skip these with `pytest -m "not integration"`.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from mcp.client import Client
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {
    "read_file",
    "write_file",
    "list_directory",
    "search_files",
    "github_repo_info",
    "github_search_repos",
    "github_user_profile",
    "research_repo",
    "index_workspace",
}
EXPECTED_PROMPTS = {"summarize_workspace_file", "repo_health_check", "find_and_explain"}


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# In-process — exercises the real tool/prompt registrations without paying
# for a subprocess or a socket on every test
# ---------------------------------------------------------------------------


async def test_in_process_lists_expected_tools_and_prompts():
    from conduit.server import mcp as server

    async with Client(server) as client:
        tools = await client.list_tools()
        assert EXPECTED_TOOLS <= {t.name for t in tools.tools}

        prompts = await client.list_prompts()
        assert EXPECTED_PROMPTS <= {p.name for p in prompts.prompts}


async def test_in_process_file_round_trip_via_tool_calls():
    from conduit.server import mcp as server
    from conduit.server import workspace

    marker = "e2e-roundtrip-test"
    rel_path = "_pytest_tmp/roundtrip.txt"
    try:
        async with Client(server) as client:
            write_result = await client.call_tool("write_file", {"path": rel_path, "content": marker, "overwrite": True})
            assert not write_result.is_error, write_result.content

            read_result = await client.call_tool("read_file", {"path": rel_path})
            assert not read_result.is_error, read_result.content
            text = "".join(block.text for block in read_result.content if hasattr(block, "text"))
            assert marker in text
    finally:
        (workspace.root / rel_path).unlink(missing_ok=True)


async def test_in_process_path_escape_surfaces_as_tool_error():
    from conduit.server import mcp as server

    async with Client(server) as client:
        result = await client.call_tool("read_file", {"path": "../../etc/passwd"})
        assert result.is_error


async def test_in_process_github_tool_call_hits_live_api():
    # Uses search rather than repo/user lookups: GitHub tracks the search
    # endpoint's rate limit separately from the core one, so this stays
    # green even when other traffic on a shared IP has used up the core quota.
    from conduit.server import mcp as server

    async with Client(server) as client:
        result = await client.call_tool("github_search_repos", {"query": "mcp server language:python", "limit": 3})
        assert not result.is_error, result.content


async def test_in_process_prompt_renders_with_arguments():
    from conduit.server import mcp as server

    async with Client(server) as client:
        rendered = await client.get_prompt("repo_health_check", {"owner": "anthropics", "repo": "mcp"})
        assert len(rendered.messages) >= 1


# ---------------------------------------------------------------------------
# stdio transport — the path Claude Desktop / Claude Code actually use
# ---------------------------------------------------------------------------


async def test_stdio_transport_end_to_end():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "conduit", "--transport", "stdio"],
        cwd=str(PROJECT_ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            assert EXPECTED_TOOLS <= {t.name for t in tools.tools}

            result = await session.call_tool("list_directory", {"path": "."})
            assert not result.is_error


# ---------------------------------------------------------------------------
# Streamable HTTP transport — the path a network-reachable agent uses
# ---------------------------------------------------------------------------


async def test_streamable_http_transport_end_to_end():
    port = _free_port()
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "conduit",
        "--transport",
        "http",
        "--port",
        str(port),
        cwd=str(PROJECT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        last_error: Exception | None = None
        for _ in range(50):  # up to ~5s for uvicorn to bind and start serving
            await asyncio.sleep(0.1)
            try:
                async with Client(url) as client:
                    tools = await client.list_tools()
                    assert EXPECTED_TOOLS <= {t.name for t in tools.tools}
                    result = await client.call_tool("list_directory", {"path": "."})
                    assert not result.is_error
                break
            except Exception as exc:  # noqa: BLE001 - retry loop against a starting server
                last_error = exc
        else:
            pytest.fail(f"HTTP server did not become ready in time: {last_error}")
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


# ---------------------------------------------------------------------------
# OAuth over the real running server — not just JWKSTokenVerifier in
# isolation (see test_auth.py for that), but Conduit's actual HTTP process,
# actually rejecting and actually accepting real requests.
# ---------------------------------------------------------------------------


async def test_http_transport_enforces_oauth_end_to_end(auth_server):
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
        sys.executable,
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

        # Wait for readiness the same way the no-auth test does, but via a
        # plain request: an authenticated client can't be used as the probe
        # here since proving it's *rejected* pre-token is part of the point.
        last_error: Exception | None = None
        for _ in range(50):
            await asyncio.sleep(0.1)
            try:
                async with httpx.AsyncClient() as probe:
                    resp = await probe.post(mcp_url, json={"jsonrpc": "2.0", "id": 0, "method": "ping"})
                    if resp.status_code in (200, 401, 406):
                        break
            except httpx.TransportError as exc:
                last_error = exc
        else:
            pytest.fail(f"HTTP server did not become ready in time: {last_error}")

        # 1. No token at all -> 401, with a WWW-Authenticate pointing at
        #    RFC 9728 protected-resource metadata (proves auth is actually on,
        #    not just configured and silently ignored).
        async with httpx.AsyncClient() as anon:
            resp = await anon.post(
                mcp_url,
                headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert resp.status_code == 401
            assert "resource_metadata=" in resp.headers.get("www-authenticate", "")

        # 2. A token minted for a *different* audience -> still 401. This is
        #    the RFC 8707 confused-deputy check, now proven through the real
        #    HTTP stack rather than just JWKSTokenVerifier.verify_token().
        wrong_aud_token = mock_as.mint_token(audience="https://a-different-server.example.test/mcp")
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {wrong_aud_token}"}) as bad:
            resp = await bad.post(
                mcp_url,
                headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert resp.status_code == 401

        # 3. A correctly-scoped, correctly-audienced token -> a full, real MCP
        #    session: initialize, list tools, call one. Not just "got a 200."
        good_token = mock_as.mint_token(audience=audience, scopes=["conduit:read"])
        authed_http_client = httpx.AsyncClient(headers={"Authorization": f"Bearer {good_token}"})
        async with streamable_http_client(mcp_url, http_client=authed_http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert EXPECTED_TOOLS <= {t.name for t in tools.tools}
                result = await session.call_tool("list_directory", {"path": "."})
                assert not result.is_error
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
