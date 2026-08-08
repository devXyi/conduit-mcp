"""Tests for conduit.auth.

Two tiers: `claims_to_access_token` is pure (a dict in, an AccessToken out)
and tested with no I/O at all. `JWKSTokenVerifier` needs a real JWKS
endpoint to fetch from, so those tests run a real `MockAuthServer` (see
mock_auth_server.py) on a real local port and mint real RS256 JWTs against
it — proving the signature/issuer/audience/expiry checks actually work,
not just that the code compiles.
"""

from __future__ import annotations

import asyncio

import httpx
import jwt
import pytest

from conduit.auth import JWKSTokenVerifier, claims_to_access_token
from tests.conftest import AUTH_ISSUER as ISSUER


# ---------------------------------------------------------------------------
# Pure claims-mapping — no network, no JWTs, no auth server
# ---------------------------------------------------------------------------


def test_claims_to_access_token_maps_space_separated_scopes():
    token = claims_to_access_token("raw", {"scope": "conduit:read conduit:write", "sub": "u1", "aud": "r1"})
    assert token.scopes == ["conduit:read", "conduit:write"]


def test_claims_to_access_token_handles_missing_scope():
    token = claims_to_access_token("raw", {"sub": "u1", "aud": "r1"})
    assert token.scopes == []


def test_claims_to_access_token_prefers_client_id_then_azp_then_sub():
    assert claims_to_access_token("t", {"client_id": "c1", "azp": "a1", "sub": "s1"}).client_id == "c1"
    assert claims_to_access_token("t", {"azp": "a1", "sub": "s1"}).client_id == "a1"
    assert claims_to_access_token("t", {"sub": "s1"}).client_id == "s1"


def test_claims_to_access_token_takes_first_audience_from_a_list():
    token = claims_to_access_token("t", {"aud": ["resource-a", "resource-b"], "sub": "u1"})
    assert token.resource == "resource-a"


def test_claims_to_access_token_preserves_raw_claims():
    claims = {"sub": "u1", "aud": "r1", "custom_claim": "value"}
    token = claims_to_access_token("t", claims)
    assert token.claims == claims


# ---------------------------------------------------------------------------
# Real JWKS verification, over a real local HTTP server (see tests/conftest.py
# for the `auth_server` fixture — MockAuthServer + a real uvicorn instance)
# ---------------------------------------------------------------------------

AUDIENCE = "https://conduit.example.test/mcp"


async def test_valid_token_is_accepted(auth_server):
    mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url)
    token = mock_as.mint_token(audience=AUDIENCE, scopes=["conduit:read"])

    result = await verifier.verify_token(token)

    assert result is not None
    assert result.subject == "test-user"
    assert result.scopes == ["conduit:read"]
    assert result.resource == AUDIENCE


async def test_wrong_audience_is_rejected(auth_server):
    """This is the RFC 8707 check: a token minted for a different resource
    server must not authenticate against this one."""
    mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url)
    token = mock_as.mint_token(audience="https://some-other-server.example.test/mcp")

    assert await verifier.verify_token(token) is None


async def test_wrong_issuer_is_rejected(auth_server):
    mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url)
    token = mock_as.mint_token(audience=AUDIENCE, issuer="https://not-the-real-idp.example.test/")

    assert await verifier.verify_token(token) is None


async def test_expired_token_is_rejected(auth_server):
    mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url, leeway_seconds=0)
    token = mock_as.mint_token(audience=AUDIENCE, expires_in=-60)  # expired a minute ago

    assert await verifier.verify_token(token) is None


async def test_unknown_kid_is_rejected(auth_server):
    """A token signed with a key the JWKS endpoint never published."""
    mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url)
    token = mock_as.mint_token(audience=AUDIENCE, kid="a-key-nobody-published")

    assert await verifier.verify_token(token) is None


async def test_malformed_token_is_rejected(auth_server):
    _mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url)

    assert await verifier.verify_token("not.a.jwt") is None
    assert await verifier.verify_token("") is None


async def test_jwks_response_is_cached_across_calls(auth_server, monkeypatch):
    mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url)
    token = mock_as.mint_token(audience=AUDIENCE)

    assert await verifier.verify_token(token) is not None  # primes the cache

    calls = {"n": 0}
    real_refresh = verifier._jwks._refresh

    async def counting_refresh():
        calls["n"] += 1
        await real_refresh()

    monkeypatch.setattr(verifier._jwks, "_refresh", counting_refresh)
    for _ in range(5):
        assert await verifier.verify_token(token) is not None

    assert calls["n"] == 0  # still within the TTL — no re-fetch needed


# ---------------------------------------------------------------------------
# Key rotation — proves the MockAuthServer's overlap window actually works,
# and that JWKSTokenVerifier picks the right key out of several published
# ---------------------------------------------------------------------------


async def test_jwks_publishes_multiple_keys_during_grace_period(auth_server):
    mock_as, jwks_url = auth_server
    await mock_as.rotate_key()

    async with httpx.AsyncClient() as client:
        jwks = (await client.get(jwks_url)).json()

    assert len(jwks["keys"]) == 2  # original (retired) + new (current)


async def test_token_signed_before_rotation_still_verifies_during_grace_period(auth_server):
    mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url)

    old_token = mock_as.mint_token(audience=AUDIENCE)  # signed with the original key
    await mock_as.rotate_key()  # original key retires but stays published

    result = await verifier.verify_token(old_token)

    assert result is not None  # still verifies: the old key is still in the JWKS


async def test_token_signed_after_rotation_uses_the_new_key(auth_server):
    mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url)

    new_kid = await mock_as.rotate_key()
    new_token = mock_as.mint_token(audience=AUDIENCE)

    result = await verifier.verify_token(new_token)

    assert result is not None
    assert jwt_header_kid(new_token) == new_kid


async def test_token_signed_by_swept_key_is_rejected(auth_server):
    mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url)

    old_token = mock_as.mint_token(audience=AUDIENCE)
    await mock_as.rotate_key()
    dropped = await mock_as.sweep_expired_keys(grace_period_seconds=0)  # force-expire immediately

    assert dropped  # the retired key was actually dropped, not a no-op
    assert await verifier.verify_token(old_token) is None  # its key is gone from the JWKS now


async def test_rotate_key_without_keep_previous_drops_old_key_immediately(auth_server):
    mock_as, jwks_url = auth_server
    verifier = JWKSTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks_url=jwks_url)

    old_token = mock_as.mint_token(audience=AUDIENCE)
    await mock_as.rotate_key(keep_previous=False)

    assert await verifier.verify_token(old_token) is None


async def test_rotate_key_rejects_a_duplicate_kid(auth_server):
    mock_as, _jwks_url = auth_server
    with pytest.raises(ValueError, match="already exists"):
        await mock_as.rotate_key(new_kid=mock_as._current_kid)


async def test_concurrent_rotations_do_not_corrupt_key_state(auth_server):
    """Fires rotations concurrently and checks the key set ends up exactly as
    many rotations produced — not more, not fewer, nothing half-written."""
    mock_as, _jwks_url = auth_server
    await asyncio.gather(*(mock_as.rotate_key() for _ in range(10)))

    assert len(mock_as._keys) == 11  # the original key + 10 new ones, all retired-but-kept
    assert len({k for k in mock_as._keys}) == 11  # every kid unique — no lost updates


def jwt_header_kid(token: str) -> str:
    return jwt.get_unverified_header(token)["kid"]


# ---------------------------------------------------------------------------
# OIDC discovery
# ---------------------------------------------------------------------------


async def test_openid_configuration_points_at_the_jwks_endpoint(auth_server):
    mock_as, jwks_url = auth_server
    discovery_url = jwks_url.replace("/jwks.json", "/.well-known/openid-configuration")

    async with httpx.AsyncClient() as client:
        config = (await client.get(discovery_url)).json()

    assert config["issuer"] == ISSUER
    # jwks_uri is built from the *logical* issuer URL (what's in token `iss`
    # claims), not the ephemeral 127.0.0.1:<port> this test happens to be
    # bound to — those two are allowed to differ, the same way a real IdP's
    # public issuer identity differs from whatever host actually serves it.
    assert config["jwks_uri"] == f"{ISSUER.rstrip('/')}/jwks.json"
