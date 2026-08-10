"""Small Auth0 Management API client for Conduit server-side administration.

The client uses the OAuth 2.0 client-credentials flow and keeps the resulting
Management API access token in memory until it is close to expiry. Secrets and
tokens never leave the server process.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .config import Auth0AdminConfig


class Auth0AdminError(RuntimeError):
    """Raised when the Auth0 Management API cannot be reached or rejects a request."""


class Auth0AdminClient:
    """Authenticated, cached-token client for Auth0 Management API v2."""

    def __init__(self, config: Auth0AdminConfig, timeout: float = 10.0) -> None:
        self.config = config
        self.timeout = timeout
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def _get_access_token(self) -> str:
        # Refresh a little early so an API request never starts with a token
        # that is about to expire.
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token

        async with self._lock:
            if self._access_token and time.time() < self._expires_at - 60:
                return self._access_token

            payload = {
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "audience": self.config.audience,
                "grant_type": "client_credentials",
            }
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.config.token_url,
                        headers={"content-type": "application/json"},
                        json=payload,
                    )
            except httpx.HTTPError as exc:
                raise Auth0AdminError(f"Auth0 token request failed: {exc}") from exc

            if response.is_error:
                detail = _safe_error_detail(response)
                raise Auth0AdminError(f"Auth0 token request failed ({response.status_code}): {detail}")

            try:
                data = response.json()
                token = str(data["access_token"])
                expires_in = int(data.get("expires_in", 86400))
            except (ValueError, KeyError, TypeError) as exc:
                raise Auth0AdminError("Auth0 token response was malformed") from exc

            self._access_token = token
            self._expires_at = time.time() + max(60, expires_in)
            return token

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        token = await self._get_access_token()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {token}"
        url = f"{self.config.management_base_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise Auth0AdminError(f"Auth0 Management API request failed: {exc}") from exc

        if response.status_code == 401:
            # A cached token can be invalidated by an operator or tenant-side
            # change. Retry once with a freshly acquired token.
            self._access_token = None
            self._expires_at = 0.0
            token = await self._get_access_token()
            headers["Authorization"] = f"Bearer {token}"
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(method, url, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                raise Auth0AdminError(f"Auth0 Management API retry failed: {exc}") from exc

        if response.is_error:
            detail = _safe_error_detail(response)
            raise Auth0AdminError(f"Auth0 Management API returned {response.status_code}: {detail}")

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    async def list_clients(self, *, page: int = 0, per_page: int = 100) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/clients",
            params={"page": page, "per_page": min(max(per_page, 1), 100)},
        )
        if not isinstance(data, list):
            raise Auth0AdminError("Auth0 returned an unexpected clients response")
        return data

    async def get_client(self, client_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/clients/{client_id}")
        if not isinstance(data, dict):
            raise Auth0AdminError("Auth0 returned an unexpected client response")
        return data


def _safe_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            error = data.get("error")
            description = data.get("error_description") or data.get("message")
            if error and description:
                return f"{error}: {description}"
            if error:
                return str(error)
        return response.text[:500]
    except ValueError:
        return response.text[:500]
