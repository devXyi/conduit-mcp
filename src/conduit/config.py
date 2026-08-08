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
class ConduitConfig:
    workspace_root: Path
    github_token: str | None
    host: str
    port: int
    auth: AuthConfig | None


def _load_auth_config(host: str, port: int) -> AuthConfig | None:
    issuer = os.environ.get("CONDUIT_AUTH_ISSUER")
    if not issuer:
        return None
    jwks_url = os.environ.get("CONDUIT_AUTH_JWKS_URL") or f"{issuer.rstrip('/')}/.well-known/jwks.json"
    audience = os.environ.get("CONDUIT_AUTH_AUDIENCE") or f"http://{host}:{port}/mcp"
    scopes_raw = os.environ.get("CONDUIT_AUTH_REQUIRED_SCOPES", "")
    required_scopes = scopes_raw.split() if scopes_raw else []
    return AuthConfig(issuer=issuer, audience=audience, jwks_url=jwks_url, required_scopes=required_scopes)


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
    )
