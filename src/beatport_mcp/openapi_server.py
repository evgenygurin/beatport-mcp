"""Alternative, spec-driven server: FastMCP v3 generates one tool per
OpenAPI operation from the vendored Beatport v4 spec.

The curated server in ``server.py`` is the default and returns slimmed-down
responses; this variant is useful when you want raw, spec-complete access:

    BEATPORT_USERNAME=... BEATPORT_PASSWORD=... \
        uv run python -m beatport_mcp.openapi_server
"""

from __future__ import annotations

import asyncio
import json
from importlib.resources import files
from typing import Any

import httpx
from fastmcp import FastMCP

from .auth import TokenManager
from .config import BEATPORT_API_BASE, Settings


class _BearerAuth(httpx.Auth):
    """httpx auth hook that injects a fresh Beatport bearer token per request."""

    requires_response_body = True

    def __init__(self, settings: Settings) -> None:
        self._tokens = TokenManager(settings)
        self._http = httpx.AsyncClient(timeout=settings.timeout)

    async def async_auth_flow(self, request: httpx.Request) -> Any:
        token = await self._tokens.get_access_token(self._http)
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code == 401:
            self._tokens.invalidate()
            token = await self._tokens.get_access_token(self._http)
            request.headers["Authorization"] = f"Bearer {token}"
            yield request


def build_server() -> FastMCP[None]:
    spec_text = files("beatport_mcp").joinpath("data/beatport-v4.openapi.json").read_text()
    spec: dict[str, Any] = json.loads(spec_text)
    settings = Settings.from_env()
    client = httpx.AsyncClient(
        base_url=BEATPORT_API_BASE,
        timeout=settings.timeout,
        auth=_BearerAuth(settings),
    )
    return FastMCP.from_openapi(openapi_spec=spec, client=client, name="Beatport (OpenAPI)")


def main() -> None:
    asyncio.run(build_server().run_async())


if __name__ == "__main__":
    main()
