"""OAuth2 authentication against the Beatport API v4.

Beatport's token endpoint (``/v4/auth/o/token/``) supports the resource-owner
password grant: POST ``grant_type=password`` with a Beatport account username
and password and it returns a bearer ``access_token`` plus a
``refresh_token``. Refreshing requires a ``client_id``; the public client_id
of Beatport's own API docs frontend is used by default (see ``config.py``).

Tokens are cached on disk (default ``~/.beatport-mcp/token.json``) so
restarts don't re-send the password.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .config import TOKEN_URL, Settings

# Refresh this many seconds before the token actually expires.
EXPIRY_MARGIN = 60.0


class BeatportAuthError(Exception):
    """Raised when authentication against the Beatport API fails."""


class TokenManager:
    """Obtains, caches, refreshes and persists Beatport OAuth tokens."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token: dict[str, Any] | None = None

    async def get_access_token(self, http: httpx.AsyncClient) -> str:
        """Return a valid access token, logging in or refreshing as needed."""
        token = self._token or self._load_cache()
        if token and not self._expired(token):
            self._token = token
            return str(token["access_token"])

        if token and token.get("refresh_token"):
            try:
                return await self._store(await self._refresh(http, str(token["refresh_token"])))
            except BeatportAuthError:
                pass  # refresh token revoked/expired — fall back to password login

        return await self._store(await self._password_login(http))

    def invalidate(self) -> None:
        """Drop the current token so the next call re-authenticates."""
        if self._token is not None:
            self._token.pop("access_token", None)
            self._token["expires_at"] = 0
            self._save_cache(self._token)

    async def _password_login(self, http: httpx.AsyncClient) -> dict[str, Any]:
        if not (self._settings.username and self._settings.password):
            raise BeatportAuthError(
                "BEATPORT_USERNAME and BEATPORT_PASSWORD environment variables must be set"
            )
        response = await http.post(
            TOKEN_URL,
            data={
                "grant_type": "password",
                "username": self._settings.username,
                "password": self._settings.password,
                "client_id": self._settings.client_id,
            },
        )
        return self._parse_token_response(response, "password login")

    async def _refresh(self, http: httpx.AsyncClient, refresh_token: str) -> dict[str, Any]:
        response = await http.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._settings.client_id,
            },
        )
        return self._parse_token_response(response, "token refresh")

    @staticmethod
    def _parse_token_response(response: httpx.Response, action: str) -> dict[str, Any]:
        if response.status_code != 200:
            raise BeatportAuthError(
                f"Beatport {action} failed with HTTP {response.status_code}: {response.text[:300]}"
            )
        token: dict[str, Any] = response.json()
        if "access_token" not in token:
            raise BeatportAuthError(f"Beatport {action} returned no access_token")
        token["expires_at"] = time.time() + float(token.get("expires_in", 3600))
        return token

    @staticmethod
    def _expired(token: dict[str, Any]) -> bool:
        return time.time() >= float(token.get("expires_at", 0)) - EXPIRY_MARGIN

    async def _store(self, token: dict[str, Any]) -> str:
        self._token = token
        self._save_cache(token)
        return str(token["access_token"])

    def _load_cache(self) -> dict[str, Any] | None:
        path = self._settings.token_file
        try:
            data: dict[str, Any] = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        return data if "access_token" in data else None

    def _save_cache(self, token: dict[str, Any]) -> None:
        path = self._settings.token_file
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(token, indent=2))
            path.chmod(0o600)
        except OSError:
            pass  # cache is best-effort; auth still works without it
