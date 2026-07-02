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
