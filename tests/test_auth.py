import json
import time

import httpx
import pytest

from beatport_mcp.auth import BeatportAuthError, TokenManager
from beatport_mcp.config import Settings


async def test_password_login_and_cache(fake_beatport, settings):
    manager = TokenManager(settings)
    async with httpx.AsyncClient(transport=fake_beatport.transport()) as http:
        token = await manager.get_access_token(http)

    assert token == "ACCESS-1"
    assert fake_beatport.token_requests[0]["grant_type"] == "password"
    assert fake_beatport.token_requests[0]["username"] == "user@example.com"

    cached = json.loads(settings.token_file.read_text())
    assert cached["access_token"] == "ACCESS-1"
    assert cached["expires_at"] > time.time()
    assert settings.token_file.stat().st_mode & 0o777 == 0o600


async def test_valid_cached_token_is_reused(fake_beatport, settings):
    manager = TokenManager(settings)
    async with httpx.AsyncClient(transport=fake_beatport.transport()) as http:
        first = await manager.get_access_token(http)
        second = await manager.get_access_token(http)

    assert first == second
    assert len(fake_beatport.token_requests) == 1


async def test_expired_token_is_refreshed(fake_beatport, settings):
    settings.token_file.write_text(
        json.dumps(
            {
                "access_token": "STALE",
                "refresh_token": "OLD-REFRESH",
                "expires_at": time.time() - 10,
            }
        )
    )
    manager = TokenManager(settings)
    async with httpx.AsyncClient(transport=fake_beatport.transport()) as http:
        token = await manager.get_access_token(http)

    assert token == "ACCESS-1"
    request = fake_beatport.token_requests[0]
    assert request["grant_type"] == "refresh_token"
    assert request["refresh_token"] == "OLD-REFRESH"
    assert request["client_id"]


async def test_failed_refresh_falls_back_to_password(fake_beatport, settings):
    fake_beatport.fail_refresh = True
    settings.token_file.write_text(
        json.dumps(
            {
                "access_token": "STALE",
                "refresh_token": "DEAD-REFRESH",
                "expires_at": time.time() - 10,
            }
        )
    )
    manager = TokenManager(settings)
    async with httpx.AsyncClient(transport=fake_beatport.transport()) as http:
        token = await manager.get_access_token(http)

    assert token == "ACCESS-1"
    grants = [r["grant_type"] for r in fake_beatport.token_requests]
    assert grants == ["refresh_token", "password"]


async def test_cached_token_for_other_account_is_ignored(fake_beatport, settings):
    settings.token_file.write_text(
        json.dumps(
            {
                "access_token": "OTHER-USERS-TOKEN",
                "refresh_token": "OTHER-REFRESH",
                "expires_at": time.time() + 3600,
                "account": {"username": "someone@else.com", "client_id": settings.client_id},
            }
        )
    )
    manager = TokenManager(settings)
    async with httpx.AsyncClient(transport=fake_beatport.transport()) as http:
        token = await manager.get_access_token(http)

    assert token == "ACCESS-1"  # fresh login, foreign token not reused
    assert fake_beatport.token_requests[0]["grant_type"] == "password"


async def test_invalidate_keeps_refresh_token_usable(fake_beatport, settings):
    manager = TokenManager(settings)
    async with httpx.AsyncClient(transport=fake_beatport.transport()) as http:
        await manager.get_access_token(http)  # login -> ACCESS-1 / REFRESH-1
        manager.invalidate()
        token = await manager.get_access_token(http)

    assert token == "ACCESS-2"
    grants = [r["grant_type"] for r in fake_beatport.token_requests]
    assert grants == ["password", "refresh_token"]  # invalidation refreshes, no re-login
    # the on-disk cache still contains a loadable token for the next process
    assert json.loads(settings.token_file.read_text())["refresh_token"] == "REFRESH-2"


async def test_missing_credentials_raise(fake_beatport, tmp_path):
    manager = TokenManager(Settings(token_file=tmp_path / "token.json"))
    async with httpx.AsyncClient(transport=fake_beatport.transport()) as http:
        with pytest.raises(BeatportAuthError, match="BEATPORT_USERNAME"):
            await manager.get_access_token(http)


async def test_password_grant_disabled_falls_back_to_session_flow(fake_beatport, settings):
    """Beatport returns unauthorized_client for the password grant → session flow."""
    fake_beatport.fail_password_login = True
    manager = TokenManager(settings)
    async with httpx.AsyncClient(transport=fake_beatport.transport()) as http:
        token = await manager.get_access_token(http)

    assert token == "ACCESS-1"
    assert fake_beatport.session_logins == 1
    grants = [r["grant_type"] for r in fake_beatport.token_requests]
    assert grants == ["password", "authorization_code"]
    code_request = fake_beatport.token_requests[1]
    assert code_request["code"] in fake_beatport.issued_codes
    assert code_request["redirect_uri"].endswith("/auth/o/post-message/")


async def test_bad_password_raises(fake_beatport, settings):
    fake_beatport.fail_password_login = True
    fake_beatport.fail_session_login = True
    manager = TokenManager(settings)
    async with httpx.AsyncClient(transport=fake_beatport.transport()) as http:
        with pytest.raises(BeatportAuthError, match="login failed"):
            await manager.get_access_token(http)
