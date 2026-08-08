"""A minimal local Authorization Server, used only by the test suite.

Conduit never talks to this in production — real deployments point
`JWKSTokenVerifier` at a real IdP (Auth0, Okta, WorkOS, Keycloak, ...). This
exists so the test suite can exercise real code paths end to end without a
live external dependency: real RS256 signatures, a real JWKS HTTP endpoint,
and real key rotation with an overlapping grace period — which is how
production IdPs actually rotate keys, so it's the case worth testing
against rather than a single JWK that never changes.

Deliberately NOT included: `/oauth/token` and `/introspect`. Building those
correctly means a real grant flow (authorization codes, PKCE, client
registration) — a second project, and not one Conduit's resource-server
role needs, since Conduit only ever verifies tokens, never issues them.
`mint_token()` below is this file's stand-in for "a token an AS issued."
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from dataclasses import dataclass, field

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


def _b64url_uint(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _generate_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class _SigningKey:
    kid: str
    private_key: rsa.RSAPrivateKey
    retired_at: float | None = None  # time.time() this stopped being current; None = still current

    def jwk(self) -> dict:
        numbers = self.private_key.public_key().public_numbers()
        return {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": self.kid,
            "n": _b64url_uint(numbers.n),
            "e": _b64url_uint(numbers.e),
        }


@dataclass
class MockAuthServer:
    issuer: str
    kid: str = "test-key-1"
    grace_period_seconds: float = 300.0
    _keys: dict[str, _SigningKey] = field(init=False, repr=False)
    _current_kid: str = field(init=False, repr=False)
    _lock: asyncio.Lock = field(init=False, repr=False)
    app: Starlette = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()
        first = _SigningKey(kid=self.kid, private_key=_generate_rsa_key())
        self._keys = {first.kid: first}
        self._current_kid = first.kid
        self.app = Starlette(
            routes=[
                Route("/jwks.json", self._jwks_endpoint, methods=["GET"]),
                Route("/.well-known/openid-configuration", self._openid_configuration, methods=["GET"]),
            ]
        )

    async def rotate_key(self, *, new_kid: str | None = None, keep_previous: bool = True) -> str:
        """Generate a new signing key and make it current.

        With `keep_previous` (the default), the outgoing key stays published
        in `/jwks.json` — tokens it already signed keep verifying — until
        `sweep_expired_keys()` drops it once `grace_period_seconds` has
        passed. That overlap is the entire point: it's what lets a fleet of
        already-running clients keep working through a rotation instead of
        every in-flight token failing the instant the key changes.
        """
        async with self._lock:
            new_kid = new_kid or f"test-key-{uuid.uuid4().hex[:8]}"
            if new_kid in self._keys:
                raise ValueError(f"kid {new_kid!r} already exists")

            previous = self._keys[self._current_kid]
            if keep_previous:
                previous.retired_at = time.time()
            else:
                del self._keys[previous.kid]

            self._keys[new_kid] = _SigningKey(kid=new_kid, private_key=_generate_rsa_key())
            self._current_kid = new_kid
            return new_kid

    async def sweep_expired_keys(self, *, grace_period_seconds: float | None = None) -> list[str]:
        """Drop retired keys whose grace period has elapsed; returns the dropped kids.

        Takes an optional override so tests can force an immediate sweep
        (`grace_period_seconds=0`) instead of sleeping in real time to prove
        expiry works.
        """
        grace = self.grace_period_seconds if grace_period_seconds is None else grace_period_seconds
        async with self._lock:
            now = time.time()
            expired = [
                k.kid for k in self._keys.values() if k.retired_at is not None and (now - k.retired_at) > grace
            ]
            for kid in expired:
                del self._keys[kid]
            return expired

    async def _jwks_endpoint(self, request: Request) -> JSONResponse:
        async with self._lock:
            keys = [k.jwk() for k in self._keys.values()]
        return JSONResponse({"keys": keys})

    async def _openid_configuration(self, request: Request) -> JSONResponse:
        base = self.issuer.rstrip("/")
        return JSONResponse(
            {
                "issuer": self.issuer,
                "jwks_uri": f"{base}/jwks.json",
                "id_token_signing_alg_values_supported": ["RS256"],
            }
        )

    def mint_token(
        self,
        *,
        audience: str,
        subject: str = "test-user",
        scopes: list[str] | None = None,
        expires_in: int = 300,
        issuer: str | None = None,
        kid: str | None = None,
        extra_claims: dict | None = None,
    ) -> str:
        """Mint an RS256 JWT signed by the *current* key.

        `kid` overrides only the token header's `kid` claim, independent of
        which key actually signs it (still always the current one) — that's
        what lets `test_unknown_kid_is_rejected` simulate a token whose
        header points at a kid the JWKS never published, which is a
        different failure mode than an actually-wrong signature.
        To test the rotation grace period, mint a token *before* calling
        `rotate_key()` and keep it — no special parameter needed, the
        previous key stays valid exactly because it's still published.
        """
        now = int(time.time())
        payload = {
            "iss": issuer if issuer is not None else self.issuer,
            "aud": audience,
            "sub": subject,
            "iat": now,
            "exp": now + expires_in,
            "scope": " ".join(scopes if scopes is not None else ["conduit:read"]),
            "client_id": "test-client",
            **(extra_claims or {}),
        }
        signing_key = self._keys[self._current_kid]
        header_kid = kid if kid is not None else signing_key.kid
        return jwt.encode(payload, signing_key.private_key, algorithm="RS256", headers={"kid": header_kid})
