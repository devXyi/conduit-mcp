from __future__ import annotations

import pytest

from mcp.client import Client

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_auth0_management_tools_are_not_public_mcp_tools():
    """Regression test for the credential/trust-boundary issue.

    Auth0 Management API credentials are server-side operational credentials,
    not capabilities that should be delegated to arbitrary Conduit callers.
    In particular, a token carrying the broad public `conduit:read` scope must
    not discover Auth0 application-management tools.
    """
    from conduit.server import mcp as server

    async with Client(server) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}

    assert "auth0_list_applications" not in names
    assert "auth0_get_application" not in names
