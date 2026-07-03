"""Thin async HTTP client for the Beatport API v4."""

from __future__ import annotations

from types import TracebackType
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx

from .auth import TokenManager
from .config import BEATPORT_API_BASE, Settings


def _error_detail(response: httpx.Response) -> str:
    """Extract the human-readable error from a Beatport response body."""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("error") or body.get("message")
            if isinstance(detail, str):
                return detail
    except ValueError:
        pass
    return response.text[:500]


# Short, actionable messages surfaced to the LLM/user in place of a raw status
# dump. FastMCP wraps a tool's exception message into its ToolError, so making
# the exception message friendly here is what the client ultimately sees.
_STATUS_MESSAGES = {
    401: "Beatport authorization failed — check BEATPORT_USERNAME/BEATPORT_PASSWORD.",
    403: "Beatport denied access to this resource (it may require a subscription).",
    404: "Beatport: not found — check the id.",
    429: "Beatport is rate limiting requests — try again shortly.",
}


def friendly_api_error(status_code: int, detail: str) -> str:
    """Turn a Beatport error status + detail into a short, actionable message."""
    message = _STATUS_MESSAGES.get(status_code)
    if message:
        return message
    if status_code >= 500:
        return "Beatport API is currently unavailable — try again later."
    return f"Beatport API error {status_code}: {detail}"


class BeatportAPIError(Exception):
    """Raised when the Beatport API returns an error response."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(friendly_api_error(status_code, detail))
        self.status_code = status_code
        self.detail = detail


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
            # Beatport 301-redirects paths without a trailing slash
            follow_redirects=True,
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
        # httpx replaces a URL's query string when `params` is given, so lift a
        # query embedded in the path (e.g. "/catalog/search/?q=x") into params.
        split = urlsplit(path)
        if split.query:
            path = split.path
            clean_params = dict(parse_qsl(split.query)) | clean_params

        response = await self._send(method, path, clean_params, json)
        if response.status_code == 401:
            self._tokens.invalidate()
            response = await self._send(method, path, clean_params, json)

        if response.status_code >= 300:
            raise BeatportAPIError(response.status_code, _error_detail(response))
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
