import json
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

from beatport_mcp.config import Settings

TOKEN_RESPONSE = {
    "access_token": "ACCESS-1",
    "expires_in": 36000,
    "token_type": "Bearer",
    "scope": "app:docs user:dj",
    "refresh_token": "REFRESH-1",
}


class FakeBeatport:
    """In-memory Beatport API backed by httpx.MockTransport."""

    def __init__(self) -> None:
        self.token_requests: list[dict[str, str]] = []
        self.api_requests: list[httpx.Request] = []
        self.fail_password_login = False
        self.fail_refresh = False
        self.reject_bearer: set[str] = set()
        self.routes: dict[str, Any] = {}
        self.token_counter = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v4/auth/o/token/":
            return self._handle_token(request)
        return self._handle_api(request)

    def _handle_token(self, request: httpx.Request) -> httpx.Response:
        form = dict(parse_qsl(request.content.decode()))
        self.token_requests.append(form)
        grant = form.get("grant_type")
        if grant == "password" and self.fail_password_login:
            return httpx.Response(401, json={"error": "invalid_grant"})
        if grant == "refresh_token" and self.fail_refresh:
            return httpx.Response(400, json={"error": "invalid_grant"})
        self.token_counter += 1
        token = dict(TOKEN_RESPONSE)
        token["access_token"] = f"ACCESS-{self.token_counter}"
        token["refresh_token"] = f"REFRESH-{self.token_counter}"
        return httpx.Response(200, json=token)

    def _handle_api(self, request: httpx.Request) -> httpx.Response:
        self.api_requests.append(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth.removeprefix("Bearer ") in self.reject_bearer:
            return httpx.Response(401, json={"detail": "Invalid token."})
        body = self.routes.get(request.url.path)
        if body is None:
            return httpx.Response(404, json={"detail": "Not found."})
        return httpx.Response(200, content=json.dumps(body))


@pytest.fixture
def fake_beatport() -> FakeBeatport:
    return FakeBeatport()


@pytest.fixture
def settings(tmp_path: Any) -> Settings:
    return Settings(
        username="user@example.com",
        password="hunter2",
        token_file=tmp_path / "token.json",
    )
