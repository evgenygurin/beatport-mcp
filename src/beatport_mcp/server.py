"""FastMCP v3 server exposing the Beatport API v4.

Authentication uses a Beatport account username/password (OAuth2 password
grant) taken from the ``BEATPORT_USERNAME`` / ``BEATPORT_PASSWORD``
environment variables. See README.md for setup.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from . import formatters as fmt
from .client import BeatportClient
from .config import Settings

mcp: FastMCP[None] = FastMCP(
    "Beatport",
    instructions=(
        "Tools for the Beatport API v4: search the music catalog (tracks, "
        "releases, artists, labels), browse genres and DJ charts, and manage "
        "the authenticated user's playlists. All searches are paginated; "
        "pass `page` to fetch more results."
    ),
)

_client: BeatportClient | None = None


def get_client() -> BeatportClient:
    global _client
    if _client is None:
        _client = BeatportClient(Settings.from_env())
    return _client


Page = Annotated[int, Field(ge=1, description="Page number (1-based)")]
PerPage = Annotated[int, Field(ge=1, le=150, description="Results per page")]


# ---------------------------------------------------------------------------
# Catalog: tracks
# ---------------------------------------------------------------------------


@mcp.tool
async def search_tracks(
    query: Annotated[str, Field(description="Free-text search, e.g. 'strobe deadmau5'")],
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """Relevance search for tracks by free text (title, artist, remixer …)."""
    data = await get_client().get(
        "/catalog/search/", q=query, type="tracks", page=page, per_page=per_page
    )
    return fmt.slim_page(data, fmt.slim_track)


@mcp.tool
async def filter_tracks(
    name: Annotated[str | None, Field(description="Track title filter")] = None,
    artist_name: Annotated[str | None, Field(description="Filter by artist name")] = None,
    genre_id: Annotated[
        int | None, Field(description="Filter by Beatport genre id (see list_genres)")
    ] = None,
    bpm_low: Annotated[int | None, Field(description="Minimum BPM (inclusive)")] = None,
    bpm_high: Annotated[int | None, Field(description="Maximum BPM (inclusive)")] = None,
    order_by: Annotated[
        str | None,
        Field(description="Sort field, e.g. '-publish_date' (newest first) or 'bpm'"),
    ] = None,
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """Filter the track catalog by structured criteria (title, artist, genre, BPM range).

    Use search_tracks for free-text relevance search; this tool is for precise
    filtering, e.g. all Drum & Bass 170-175 BPM, or every track named 'Strobe'
    by deadmau5.
    """
    bpm = None
    if bpm_low is not None or bpm_high is not None:
        bpm = f"{bpm_low if bpm_low is not None else 1}:{bpm_high if bpm_high is not None else 999}"
    data = await get_client().get(
        "/catalog/tracks/",
        name=name,
        artist_name=artist_name,
        genre_id=genre_id,
        bpm=bpm,
        order_by=order_by,
        page=page,
        per_page=per_page,
    )
    return fmt.slim_page(data, fmt.slim_track)


@mcp.tool
async def get_track(track_id: int) -> Any:
    """Get full details of a single track by its Beatport id."""
    return fmt.slim_track(await get_client().get(f"/catalog/tracks/{track_id}/"))


# ---------------------------------------------------------------------------
# Catalog: releases
# ---------------------------------------------------------------------------


@mcp.tool
async def search_releases(
    query: Annotated[str, Field(description="Release name / free-text search")],
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """Relevance search for releases (albums/EPs/singles)."""
    data = await get_client().get(
        "/catalog/search/", q=query, type="releases", page=page, per_page=per_page
    )
    return fmt.slim_page(data, fmt.slim_release)


@mcp.tool
async def get_release(release_id: int) -> Any:
    """Get details of a release by id."""
    return fmt.slim_release(await get_client().get(f"/catalog/releases/{release_id}/"))


@mcp.tool
async def get_release_tracks(release_id: int, page: Page = 1, per_page: PerPage = 100) -> Any:
    """List the tracks of a release."""
    data = await get_client().get(
        f"/catalog/releases/{release_id}/tracks/", page=page, per_page=per_page
    )
    return fmt.slim_page(data, fmt.slim_track)


# ---------------------------------------------------------------------------
# Catalog: artists & labels
# ---------------------------------------------------------------------------


@mcp.tool
async def search_artists(
    query: Annotated[str, Field(description="Artist name to search for")],
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """Search artists by name."""
    data = await get_client().get(
        "/catalog/search/", q=query, type="artists", page=page, per_page=per_page
    )
    return fmt.slim_page(data, fmt.slim_artist)


@mcp.tool
async def get_artist_tracks(
    artist_id: int,
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """List an artist's tracks, newest first."""
    data = await get_client().get(
        f"/catalog/artists/{artist_id}/tracks/",
        page=page,
        per_page=per_page,
        order_by="-publish_date",
    )
    return fmt.slim_page(data, fmt.slim_track)


@mcp.tool
async def search_labels(
    query: Annotated[str, Field(description="Label name to search for")],
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """Search record labels by name."""
    data = await get_client().get(
        "/catalog/search/", q=query, type="labels", page=page, per_page=per_page
    )
    return fmt.slim_page(data, fmt.slim_label)


@mcp.tool
async def get_label_releases(label_id: int, page: Page = 1, per_page: PerPage = 25) -> Any:
    """List a label's releases, newest first."""
    data = await get_client().get(
        f"/catalog/labels/{label_id}/releases/",
        page=page,
        per_page=per_page,
        order_by="-publish_date",
    )
    return fmt.slim_page(data, fmt.slim_release)


# ---------------------------------------------------------------------------
# Catalog: genres & charts
# ---------------------------------------------------------------------------


@mcp.tool
async def list_genres(page: Page = 1, per_page: PerPage = 100) -> Any:
    """List Beatport genres with their ids (used by genre_id filters)."""
    data = await get_client().get("/catalog/genres/", page=page, per_page=per_page)
    return fmt.slim_page(data, fmt.slim_genre)


@mcp.tool
async def search_charts(
    query: Annotated[str, Field(description="Chart name to search for")] = "",
    genre_id: Annotated[int | None, Field(description="Filter by genre id")] = None,
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """Search DJ charts."""
    data = await get_client().get(
        "/catalog/charts/", name=query or None, genre_id=genre_id, page=page, per_page=per_page
    )
    return fmt.slim_page(data, fmt.slim_chart)


@mcp.tool
async def get_chart_tracks(chart_id: int, page: Page = 1, per_page: PerPage = 100) -> Any:
    """List the tracks of a DJ chart."""
    data = await get_client().get(
        f"/catalog/charts/{chart_id}/tracks/", page=page, per_page=per_page
    )
    return fmt.slim_page(data, fmt.slim_track)


# ---------------------------------------------------------------------------
# Account & playlists (require the authenticated user)
# ---------------------------------------------------------------------------


@mcp.tool
async def my_account() -> Any:
    """Get the authenticated Beatport account's profile (also a good auth check)."""
    return await get_client().get("/my/account/")


@mcp.tool
async def my_playlists(page: Page = 1, per_page: PerPage = 50) -> Any:
    """List the authenticated user's playlists."""
    data = await get_client().get("/my/playlists/", page=page, per_page=per_page)
    return fmt.slim_page(data, fmt.slim_playlist)


@mcp.tool
async def get_playlist_tracks(playlist_id: int, page: Page = 1, per_page: PerPage = 100) -> Any:
    """List the tracks in one of the user's playlists."""
    data = await get_client().get(
        f"/my/playlists/{playlist_id}/tracks/", page=page, per_page=per_page
    )
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        # playlist items wrap the track: {"id": ..., "position": ..., "track": {...}}
        data["results"] = [
            {
                "item_id": item.get("id"),
                "position": item.get("position"),
                "track": fmt.slim_track(item.get("track")),
            }
            if isinstance(item, dict) and "track" in item
            else fmt.slim_track(item)
            for item in data["results"]
        ]
    return fmt.slim_page(data)


@mcp.tool
async def create_playlist(name: Annotated[str, Field(min_length=1)]) -> Any:
    """Create a new playlist in the user's Beatport account."""
    return fmt.slim_playlist(await get_client().post("/my/playlists/", json={"name": name}))


@mcp.tool
async def add_tracks_to_playlist(
    playlist_id: int,
    track_ids: Annotated[list[int], Field(min_length=1, description="Beatport track ids")],
) -> Any:
    """Add tracks to one of the user's playlists."""
    return await get_client().post(
        f"/my/playlists/{playlist_id}/tracks/bulk/", json={"track_ids": track_ids}
    )


# ---------------------------------------------------------------------------
# Escape hatch
# ---------------------------------------------------------------------------


@mcp.tool
async def beatport_api_get(
    path: Annotated[
        str,
        Field(
            description=(
                "Any GET path of the Beatport API v4, e.g. '/catalog/tracks/123/' or "
                "'/catalog/search/?q=techno&type=tracks'. See https://api.beatport.com/v4/docs/"
            )
        ),
    ],
    params: Annotated[dict[str, Any] | None, Field(description="Extra query parameters")] = None,
) -> Any:
    """Call any read-only (GET) Beatport API v4 endpoint — full raw response."""
    return await get_client().get(path, **(params or {}))


def main() -> None:
    """Console entry point: run over stdio by default, HTTP if configured."""
    transport = os.environ.get("BEATPORT_MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(
            transport="http",
            host=os.environ.get("BEATPORT_MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("BEATPORT_MCP_PORT", "8000")),
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
