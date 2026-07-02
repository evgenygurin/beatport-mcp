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
        self.fail_session_login = False
        self.fail_refresh = False
        self.reject_bearer: set[str] = set()
        self.routes: dict[str, Any] = {}
        self.token_counter = 0
        self.session_logins = 0
        self.issued_codes: set[str] = set()

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v4/auth/o/token/":
            return self._handle_token(request)
        if path == "/v4/auth/login/":
            return self._handle_login(request)
        if path == "/v4/auth/o/authorize/":
            return self._handle_authorize(request)
        return self._handle_api(request)

    def _issue_token(self) -> httpx.Response:
        self.token_counter += 1
        token = dict(TOKEN_RESPONSE)
        token["access_token"] = f"ACCESS-{self.token_counter}"
        token["refresh_token"] = f"REFRESH-{self.token_counter}"
        return httpx.Response(200, json=token)

    def _handle_token(self, request: httpx.Request) -> httpx.Response:
        form = dict(parse_qsl(request.content.decode()))
        self.token_requests.append(form)
        grant = form.get("grant_type")
        if grant == "password":
            if self.fail_password_login:
                return httpx.Response(400, json={"error": "unauthorized_client"})
            return self._issue_token()
        if grant == "refresh_token":
            if self.fail_refresh:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return self._issue_token()
        if grant == "authorization_code":
            if form.get("code") in self.issued_codes:
                return self._issue_token()
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(400, json={"error": "unsupported_grant_type"})

    def _handle_login(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        self.session_logins += 1
        if self.fail_session_login or body.get("password") != "hunter2":
            return httpx.Response(401, json={"detail": "Unable to log in."})
        return httpx.Response(
            200,
            json={"username": body["username"]},
            headers={"set-cookie": "sessionid=SESS-1; Path=/"},
        )

    def _handle_authorize(self, request: httpx.Request) -> httpx.Response:
        if "sessionid=" not in request.headers.get("cookie", ""):
            return httpx.Response(401, json={"detail": "Not authenticated"})
        code = f"CODE-{len(self.issued_codes) + 1}"
        self.issued_codes.add(code)
        redirect_uri = request.url.params.get("redirect_uri", "")
        return httpx.Response(302, headers={"location": f"{redirect_uri}?code={code}"})

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
