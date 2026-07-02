"""Thin async HTTP client for the Beatport API v4."""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from .auth import TokenManager
from .config import BEATPORT_API_BASE, Settings


class BeatportAPIError(Exception):
    """Raised when the Beatport API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Beatport API error {status_code}: {message}")
        self.status_code = status_code


class BeatportClient:
    """Authenticated client for api.beatport.com/v4.

    Handles bearer-token injection and retries once on 401 after
    re-authenticating (expired/revoked access token).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings or Settings.from_env()
        self._tokens = TokenManager(self._settings)
        self._http = httpx.AsyncClient(
            base_url=BEATPORT_API_BASE,
            timeout=self._settings.timeout,
            headers={
                "User-Agent": "beatport-mcp/0.1 (+https://github.com/evgenygurin/beatport-mcp)"
            },
            transport=transport,  # type: ignore[arg-type]
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Perform an authenticated request; returns the decoded JSON body."""
        path = "/" + path.lstrip("/")
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        response = await self._send(method, path, clean_params, json)
        if response.status_code == 401:
            self._tokens.invalidate()
            response = await self._send(method, path, clean_params, json)

        if response.status_code >= 400:
            raise BeatportAPIError(response.status_code, response.text[:500])
        if response.status_code == 204 or not response.content:
            return {"status": response.status_code}
        return response.json()

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any]) -> Any:
        return await self.request("POST", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def _send(
        self,
        method: str,
        path: str,
        params: dict[str, Any],
        json: dict[str, Any] | None,
    ) -> httpx.Response:
        token = await self._tokens.get_access_token(self._http)
        return await self._http.request(
            method,
            path,
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> BeatportClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
