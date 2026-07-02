import pytest

from beatport_mcp.client import BeatportAPIError, BeatportClient

TRACKS_PAGE = {
    "count": 1,
    "page": "1/1",
    "per_page": 25,
    "next": None,
    "previous": None,
    "results": [{"id": 123, "name": "Strobe"}],
}


async def test_get_injects_bearer_and_filters_none_params(fake_beatport, settings):
    fake_beatport.routes["/v4/catalog/tracks/"] = TRACKS_PAGE
    async with BeatportClient(settings, transport=fake_beatport.transport()) as client:
        data = await client.get("/catalog/tracks/", q="strobe", genre_id=None)

    assert data["results"][0]["id"] == 123
    request = fake_beatport.api_requests[0]
    assert request.headers["Authorization"] == "Bearer ACCESS-1"
    assert request.url.params["q"] == "strobe"
    assert "genre_id" not in request.url.params


async def test_retries_once_after_401(fake_beatport, settings):
    fake_beatport.routes["/v4/my/account/"] = {"username": "dj"}
    fake_beatport.reject_bearer.add("ACCESS-1")  # first token gets revoked server-side
    async with BeatportClient(settings, transport=fake_beatport.transport()) as client:
        data = await client.get("/my/account/")

    assert data == {"username": "dj"}
    assert len(fake_beatport.api_requests) == 2
    assert fake_beatport.api_requests[1].headers["Authorization"] == "Bearer ACCESS-2"


async def test_api_error_raises(fake_beatport, settings):
    async with BeatportClient(settings, transport=fake_beatport.transport()) as client:
        with pytest.raises(BeatportAPIError) as excinfo:
            await client.get("/catalog/tracks/999999999/")

    assert excinfo.value.status_code == 404
    assert "Not found." in str(excinfo.value)  # JSON detail extracted, not raw body


async def test_query_string_embedded_in_path_is_preserved(fake_beatport, settings):
    """httpx would drop a path-embedded query when params= is passed; we lift it."""
    fake_beatport.routes["/v4/catalog/search/"] = {"count": 0, "results": []}
    async with BeatportClient(settings, transport=fake_beatport.transport()) as client:
        await client.get("/catalog/search/?q=techno&type=tracks", per_page=5)

    params = fake_beatport.api_requests[0].url.params
    assert params["q"] == "techno"
    assert params["type"] == "tracks"
    assert params["per_page"] == "5"


async def test_concurrent_calls_login_only_once(fake_beatport, settings):
    """Parallel tool calls with no token must not stampede the login endpoint."""
    import asyncio

    fake_beatport.routes["/v4/my/account/"] = {"username": "dj"}
    async with BeatportClient(settings, transport=fake_beatport.transport()) as client:
        results = await asyncio.gather(*(client.get("/my/account/") for _ in range(5)))

    assert all(r == {"username": "dj"} for r in results)
    password_grants = [r for r in fake_beatport.token_requests if r["grant_type"] == "password"]
    assert len(password_grants) == 1
