"""End-to-end tests of the MCP tools via an in-memory FastMCP client."""

from typing import Any

import pytest
from fastmcp import Client

from beatport_mcp import server

RAW_TRACK = {
    "id": 123,
    "name": "Strobe",
    "mix_name": "Original Mix",
    "slug": "strobe",
    "artists": [{"id": 7, "name": "deadmau5", "image": {"uri": "big.jpg"}}],
    "remixers": [],
    "release": {"id": 55, "name": "For Lack of a Better Name", "image": {"uri": "x.jpg"}},
    "genre": {"id": 12, "name": "Progressive House", "url": "..."},
    "sub_genre": None,
    "bpm": 128,
    "key": {"id": 3, "name": "B Minor", "camelot_number": 10},
    "length": "10:37",
    "publish_date": "2009-09-22",
    "isrc": "CA6D80900506",
    "catalog_number": "MAU5CD01",
    "price": {"code": "usd", "symbol": "$", "value": 1.49, "display": "$1.49"},
    "sample_url": "https://geo-samples.beatport.com/track/abc.LOFI.mp3",
    "sample_start_ms": 120167,
    "sample_end_ms": 240167,
    "is_available_for_streaming": True,
    "exclusive": False,
    "sale_type": "purchase",
}


class FakeBeatportClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def get(self, path: str, **params: Any) -> Any:
        self.calls.append(("GET", path, params))
        if path == "/catalog/search/":
            # search responses nest items under the entity-type key
            return {"count": 1, "page": "1/1", "next": None, params["type"]: [RAW_TRACK]}
        if path == "/catalog/tracks/":
            return {
                "count": 1,
                "page": "1/1",
                "per_page": params.get("per_page"),
                "next": None,
                "results": [RAW_TRACK],
            }
        if path == "/catalog/genres/":
            return {"count": 1, "next": None, "results": [{"id": 12, "name": "Prog House"}]}
        if path == "/catalog/tracks/123/":
            return RAW_TRACK
        raise AssertionError(f"unexpected GET {path}")

    async def post(self, path: str, json: dict[str, Any]) -> Any:
        self.calls.append(("POST", path, json))
        if path == "/my/playlists/":
            return {"id": 900, "name": json["name"], "track_count": 0}
        if path == "/my/playlists/900/tracks/bulk/":
            return {"status": 200}
        raise AssertionError(f"unexpected POST {path}")

    async def aclose(self) -> None:  # lifespan closes the client on shutdown
        pass


@pytest.fixture
def fake_client(monkeypatch) -> FakeBeatportClient:
    fake = FakeBeatportClient()
    monkeypatch.setattr(server, "_client", fake)
    return fake


async def test_tools_are_registered():
    async with Client(server.mcp) as client:
        tools = {tool.name for tool in await client.list_tools()}
    assert {
        "search_tracks",
        "filter_tracks",
        "get_track",
        "get_track_preview",
        "get_purchase_links",
        "search_releases",
        "get_release",
        "get_release_tracks",
        "search_artists",
        "get_artist_tracks",
        "search_labels",
        "get_label_releases",
        "list_genres",
        "search_charts",
        "get_chart_tracks",
        "my_account",
        "my_playlists",
        "get_playlist_tracks",
        "create_playlist",
        "add_tracks_to_playlist",
        "remove_track_from_playlist",
        "delete_playlist",
        "beatport_api_get",
    } <= tools


async def test_read_tools_carry_readonly_annotation():
    async with Client(server.mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["search_tracks"].annotations.readOnlyHint is True
    assert tools["delete_playlist"].annotations.destructiveHint is True
    assert tools["create_playlist"].annotations.readOnlyHint is False


async def test_resources_and_prompts_are_registered():
    async with Client(server.mcp) as client:
        resources = {str(r.uri) for r in await client.list_resources()}
        templates = {t.uriTemplate for t in await client.list_resource_templates()}
        prompts = {p.name for p in await client.list_prompts()}
    assert {"beatport://genres", "beatport://account"} <= resources
    assert {"beatport://track/{track_id}", "beatport://chart/{chart_id}/tracks"} <= templates
    assert {"crate_dig", "analyze_playlist"} <= prompts


async def test_genres_resource_reads_catalog(fake_client):
    async with Client(server.mcp) as client:
        result = await client.read_resource("beatport://genres")
    import json

    payload = json.loads(result[0].text)
    assert payload["results"][0]["name"] == "Prog House"


async def test_track_template_resource(fake_client):
    async with Client(server.mcp) as client:
        result = await client.read_resource("beatport://track/123")
    import json

    assert json.loads(result[0].text)["id"] == 123


async def test_crate_dig_prompt_renders():
    async with Client(server.mcp) as client:
        result = await client.get_prompt(
            "crate_dig", {"genre": "hypnotic techno", "bpm_low": 130, "bpm_high": 138}
        )
    text = result.messages[0].content.text
    assert "hypnotic techno" in text
    assert "130" in text and "138" in text


async def test_get_purchase_links_reports_progress(fake_client):
    seen: list[tuple[float, float | None]] = []

    async def on_progress(progress, total, message):
        seen.append((progress, total))

    async with Client(server.mcp, progress_handler=on_progress) as client:
        result = await client.call_tool("get_purchase_links", {"track_ids": [123, 123]})

    assert len(result.data["results"]) == 2
    assert seen[-1] == (2, 2)


async def test_search_tracks_returns_slim_results(fake_client):
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_tracks", {"query": "strobe", "per_page": 5})

    page = result.data
    assert page["count"] == 1
    assert page["has_next_page"] is False
    track = page["results"][0]
    assert track["id"] == 123
    assert track["artists"] == [{"id": 7, "name": "deadmau5"}]
    assert track["key"] == "B Minor"
    assert track["price"] == "$1.49"
    assert track["url"] == "https://www.beatport.com/track/strobe/123"
    assert "exclusive" not in track  # noisy fields stripped

    method, path, params = fake_client.calls[0]
    assert (method, path) == ("GET", "/catalog/search/")
    assert params["q"] == "strobe"
    assert params["type"] == "tracks"


async def test_filter_tracks_builds_bpm_range(fake_client):
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "filter_tracks", {"artist_name": "deadmau5", "bpm_low": 170, "bpm_high": 175}
        )

    assert result.data["results"][0]["id"] == 123
    method, path, params = fake_client.calls[0]
    assert (method, path) == ("GET", "/catalog/tracks/")
    assert params["artist_name"] == "deadmau5"
    assert params["bpm"] == "170:175"
    assert params["name"] is None  # dropped later by the HTTP client


async def test_get_track_preview_returns_official_sample(fake_client):
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_track_preview", {"track_id": 123})

    data = result.data
    assert data["preview_url"] == "https://geo-samples.beatport.com/track/abc.LOFI.mp3"
    assert data["preview_start_ms"] == 120167
    assert data["preview_end_ms"] == 240167
    assert data["streamable"] is True
    assert data["purchase_url"] == "https://www.beatport.com/track/strobe/123"
    assert data["price"] == "$1.49"


async def test_get_purchase_links(fake_client):
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_purchase_links", {"track_ids": [123]})

    entry = result.data["results"][0]
    assert entry["purchase_url"] == "https://www.beatport.com/track/strobe/123"
    assert entry["price"] == "$1.49"
    assert "preview_url" not in entry  # purchase view stays focused on buying


async def test_create_playlist_and_add_tracks(fake_client):
    async with Client(server.mcp) as client:
        created = await client.call_tool("create_playlist", {"name": "Peak Time"})
        added = await client.call_tool(
            "add_tracks_to_playlist", {"playlist_id": 900, "track_ids": [123, 456]}
        )

    assert created.data["id"] == 900
    assert added.data == {"status": 200}
    bulk_call = ("POST", "/my/playlists/900/tracks/bulk/", {"track_ids": [123, 456]})
    assert bulk_call in fake_client.calls


async def test_per_page_is_validated():
    async with Client(server.mcp) as client:
        with pytest.raises(Exception, match=r"per_page|validation"):
            await client.call_tool("search_tracks", {"query": "x", "per_page": 9999})
