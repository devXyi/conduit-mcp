from __future__ import annotations

from types import SimpleNamespace

import pytest

from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver import Context

from conduit.auth import InsufficientScopeError, require_scope
from conduit.server import auth0_get_application


def _context_with_scopes(*scopes: str) -> Context:
    token = AccessToken(
        token="test-token",
        client_id="test-client",
        scopes=list(scopes),
        expires_at=2_000_000_000,
        claims={"iss": "https://issuer.example.test/"},
    )
    request = SimpleNamespace(user=SimpleNamespace(access_token=token))
    request_context = SimpleNamespace(request=request)
    return Context(request_context=request_context)


def test_conduit_read_does_not_satisfy_admin_scope():
    ctx = _context_with_scopes("conduit:read")
    with pytest.raises(InsufficientScopeError, match="conduit:admin"):
        require_scope(ctx, "conduit:admin")


def test_conduit_admin_satisfies_admin_scope():
    ctx = _context_with_scopes("conduit:read", "conduit:admin")
    token = require_scope(ctx, "conduit:admin")
    assert "conduit:admin" in token.scopes


@pytest.mark.asyncio
async def test_auth0_get_application_rejects_read_only_caller_before_management_api():
    ctx = _context_with_scopes("conduit:read")
    with pytest.raises(InsufficientScopeError, match="conduit:admin"):
        await auth0_get_application("any-client-id", ctx)
