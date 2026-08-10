"""OAuth 2.1 resource-server authentication for Conduit's HTTP transport."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context

from .config import AuthConfig

DEFAULT_ALGORITHMS = ["RS256"]


class InsufficientScopeError(PermissionError):
    """Raised when an authenticated caller lacks a tool-specific capability."""


def claims_to_access_token(token: str, claims: dict[str, Any]) -> AccessToken:
    scope_claim = claims.get("scope", "")
    scopes = scope_claim.split() if isinstance(scope_claim, str) else list(scope_claim or [])
    aud = claims.get("aud")
    resource = aud[0] if isinstance(aud, list) and aud else aud if isinstance(aud, str) else None
    return AccessToken(
        token=token,
        client_id=str(claims.get("client_id") or claims.get("azp") or claims.get("sub") or "unknown"),
        scopes=scopes,
        expires_at=claims.get("exp"),
        resource=resource,
        subject=claims.get("sub"),
        claims=claims,
    )


def require_scope(ctx: Context, required_scope: str) -> AccessToken:
    """Require a per-tool OAuth scope from the authenticated HTTP request.

    The MCP server's global `required_scopes` gate authenticates the resource
    request, while this helper enforces finer-grained capabilities at the tool
    boundary. Local/in-process calls without an authenticated request are
    denied rather than being treated as privileged.
    """
    request = getattr(ctx.request_context, "request", None)
    user = getattr(request, "user", None)
    access_token = getattr(user, "access_token", None)
    scopes = getattr(access_token, "scopes", ())
    if access_token is None or required_scope not in scopes:
        raise InsufficientScopeError(f"Required scope: {required_scope}")
    return access_token


class JWKSError(Exception):
    """Raised for JWKS fetch/parse problems."""


@dataclass
class _JWKSCache:
    url: str
    ttl_seconds: float = 300.0

    def __post_init__(self) -> None:
        self._keys_by_kid: dict[str, Any] = {}
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_key(self, kid: str) -> Any:
        async with self._lock:
            if kid not in self._keys_by_kid or self._is_stale():
                await self._refresh()
        if kid not in self._keys_by_kid:
            raise JWKSError(f"No JWKS key found for kid={kid!r} at {self.url}")
        return self._keys_by_kid[kid]

    def _is_stale(self) -> bool:
        return (time.monotonic() - self._fetched_at) > self.ttl_seconds

    async def _refresh(self) -> None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()
        try:
            jwks = resp.json()
            keys = {
                key["kid"]: RSAAlgorithm.from_jwk(json.dumps(key))
                for key in jwks["keys"]
                if key.get("kty") == "RSA" and "kid" in key
            }
        except (KeyError, ValueError, TypeError) as exc:
            raise JWKSError(f"Malformed JWKS document from {self.url}: {exc}") from exc
        self._keys_by_kid = keys
        self._fetched_at = time.monotonic()


@dataclass
class JWKSTokenVerifier(TokenVerifier):
    issuer: str
    audience: str
    jwks_url: str
    algorithms: list[str] = field(default_factory=lambda: list(DEFAULT_ALGORITHMS))
    leeway_seconds: int = 30

    def __post_init__(self) -> None:
        self._jwks = _JWKSCache(self.jwks_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if kid is None:
                return None
            key = await self._jwks.get_key(kid)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=self.algorithms,
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway_seconds,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except (jwt.PyJWTError, JWKSError, httpx.HTTPError):
            return None
        return claims_to_access_token(token, claims)


def build_auth(config: AuthConfig | None) -> tuple[AuthSettings | None, JWKSTokenVerifier | None]:
    if config is None:
        return None, None
    settings = AuthSettings(
        issuer_url=config.issuer,
        resource_server_url=config.audience,
        required_scopes=config.required_scopes or None,
    )
    verifier = JWKSTokenVerifier(issuer=config.issuer, audience=config.audience, jwks_url=config.jwks_url)
    return settings, verifier
