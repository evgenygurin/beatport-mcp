"""OAuth2 authentication against the Beatport API v4 using username/password.

Two flows are attempted, in order:

1. **Password grant** — single POST to ``/v4/auth/o/token/`` with
   ``grant_type=password``. Beatport has disabled this grant for the public
   docs client (returns ``unauthorized_client``), but it is kept first in
   case a user supplies their own ``BEATPORT_CLIENT_ID`` that allows it.

2. **Session login + authorization code** (the flow Beatport's own docs
   frontend uses, verified working):

   - ``POST /v4/auth/login/`` with the username/password → session cookie
   - ``GET /v4/auth/o/authorize/?response_type=code&client_id=…&redirect_uri=…``
     → 302 redirect whose ``code`` query param is the authorization code
   - ``POST /v4/auth/o/token/`` with ``grant_type=authorization_code``

Refreshing uses ``grant_type=refresh_token`` with the same ``client_id``.
Tokens are cached on disk (default ``~/.beatport-mcp/token.json``) so
restarts don't re-send the password.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from .config import BEATPORT_API_BASE, TOKEN_URL, Settings

LOGIN_URL = f"{BEATPORT_API_BASE}/auth/login/"
AUTHORIZE_URL = f"{BEATPORT_API_BASE}/auth/o/authorize/"
REDIRECT_URI = f"{BEATPORT_API_BASE}/auth/o/post-message/"

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
                pass  # refresh token revoked/expired — fall back to a fresh login

        return await self._store(await self._login(http))

    def invalidate(self) -> None:
        """Drop the current token so the next call re-authenticates."""
        if self._token is not None:
            self._token.pop("access_token", None)
            self._token["expires_at"] = 0
            self._save_cache(self._token)

    async def _login(self, http: httpx.AsyncClient) -> dict[str, Any]:
        if not (self._settings.username and self._settings.password):
            raise BeatportAuthError(
                "BEATPORT_USERNAME and BEATPORT_PASSWORD environment variables must be set"
            )
        try:
            return await self._password_grant(http)
        except BeatportAuthError:
            return await self._session_login(http)

    async def _password_grant(self, http: httpx.AsyncClient) -> dict[str, Any]:
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

    async def _session_login(self, http: httpx.AsyncClient) -> dict[str, Any]:
        login = await http.post(
            LOGIN_URL,
            json={
                "username": self._settings.username,
                "password": self._settings.password,
            },
        )
        if login.status_code != 200:
            raise BeatportAuthError(
                f"Beatport login failed with HTTP {login.status_code}: {login.text[:300]}"
            )

        authorize = await http.get(
            AUTHORIZE_URL,
            params={
                "response_type": "code",
                "client_id": self._settings.client_id,
                "redirect_uri": REDIRECT_URI,
            },
            cookies=login.cookies,
            follow_redirects=False,
        )
        location = authorize.headers.get("location", "")
        code = parse_qs(urlsplit(location).query).get("code", [""])[0]
        if authorize.status_code not in (301, 302) or not code:
            raise BeatportAuthError(
                f"Beatport authorize step failed (HTTP {authorize.status_code}); "
                "no authorization code in redirect"
            )

        token = await http.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self._settings.client_id,
                "redirect_uri": REDIRECT_URI,
            },
            cookies=login.cookies,
        )
        return self._parse_token_response(token, "authorization code exchange")

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
