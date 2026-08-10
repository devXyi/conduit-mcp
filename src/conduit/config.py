"""Runtime configuration for Conduit, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class AuthConfig:
    issuer: str
    audience: str
    jwks_url: str
    required_scopes: list[str]


@dataclass(frozen=True)
class Auth0AdminConfig:
    domain: str
    client_id: str
    client_secret: str
    audience: str


@dataclass(frozen=True)
class ConduitConfig:
    workspace_root: Path
    github_token: str | None
    host: str
    port: int
    auth: AuthConfig | None
    auth0_admin: Auth0AdminConfig | None


def _load_auth_config(host: str, port: int) -> AuthConfig | None:
    issuer = os.environ.get("CONDUIT_AUTH_ISSUER")
    if not issuer:
        return None
    jwks_url = os.environ.get("CONDUIT_AUTH_JWKS_URL") or f"{issuer.rstrip('/')}/.well-known/jwks.json"
    audience = os.environ.get("CONDUIT_AUTH_AUDIENCE") or f"http://{host}:{port}/mcp"
    scopes_raw = os.environ.get("CONDUIT_AUTH_REQUIRED_SCOPES", "")
    required_scopes = scopes_raw.split() if scopes_raw else []
    return AuthConfig(issuer=issuer, audience=audience, jwks_url=jwks_url, required_scopes=required_scopes)


def _load_auth0_admin_config() -> Auth0AdminConfig | None:
    """Load server-side Auth0 Management API credentials when fully configured."""
    domain = os.environ.get("AUTH0_DOMAIN")
    client_id = os.environ.get("AUTH0_CLIENT_ID")
    client_secret = os.environ.get("AUTH0_CLIENT_SECRET")
    audience = os.environ.get("AUTH0_AUDIENCE")
    if not all((domain, client_id, client_secret, audience)):
        return None
    return Auth0AdminConfig(
        domain=domain.rstrip("/"),
        client_id=client_id,
        client_secret=client_secret,
        audience=audience,
    )


def load_config() -> ConduitConfig:
    workspace_root = Path(os.environ.get("CONDUIT_WORKSPACE", "./workspace")).resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    host = os.environ.get("CONDUIT_HOST", "127.0.0.1")
    port = int(os.environ.get("CONDUIT_PORT", "8000"))
    return ConduitConfig(
        workspace_root=workspace_root,
        github_token=os.environ.get("GITHUB_TOKEN") or None,
        host=host,
        port=port,
        auth=_load_auth_config(host, port),
        auth0_admin=_load_auth0_admin_config(),
    )
