from __future__ import annotations

import pytest

from mcp.client import Client


@pytest.mark.asyncio
async def test_auth0_management_tools_are_registered_but_not_publicly_authorized():
    """Auth0 tools may exist, but `conduit:read` must not authorize them.

    The capability boundary is enforced at invocation time with the dedicated
    `conduit:admin` scope. This keeps the Management API credential separate
    from the ordinary public Conduit capability.
    """
    from conduit.server import mcp as server

    async with Client(server) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}

    assert "auth0_list_applications" in names
    assert "auth0_get_application" in names
