"""FastMCP v3 server exposing the Beatport API v4.

Authentication uses a Beatport account username/password (OAuth2 password
grant) taken from the ``BEATPORT_USERNAME`` / ``BEATPORT_PASSWORD``
environment variables. See README.md for setup.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.server.elicitation import CancelledElicitation, DeclinedElicitation
from mcp.types import ToolAnnotations
from pydantic import Field

from . import formatters as fmt
from .client import BeatportClient
from .config import Settings
from .middleware import TimingMiddleware

_client: BeatportClient | None = None


def get_client() -> BeatportClient:
    global _client
    if _client is None:
        _client = BeatportClient(Settings.from_env())
    return _client


@asynccontextmanager
async def lifespan(_server: FastMCP[None]) -> AsyncIterator[None]:
    """Own the shared HTTP client's lifecycle: close it on server shutdown."""
    global _client
    try:
        yield
    finally:
        if _client is not None:
            await _client.aclose()
            _client = None


mcp: FastMCP[None] = FastMCP(
    "Beatport",
    instructions=(
        "Tools for the Beatport API v4: search the music catalog (tracks, "
        "releases, artists, labels), browse genres and DJ charts, and manage "
        "the authenticated user's playlists. All searches are paginated; "
        "pass `page` to fetch more results. Reference data (genre list, the "
        "authenticated account, individual tracks/releases/charts) is also "
        "exposed as `beatport://` resources."
    ),
    lifespan=lifespan,
)

mcp.add_middleware(TimingMiddleware())

# Shared annotation presets. Catalog reads hit an external API (openWorldHint)
# and never mutate state (readOnlyHint); repeated reads are idempotent.
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)

Page = Annotated[int, Field(ge=1, description="Page number (1-based)")]
PerPage = Annotated[int, Field(ge=1, le=150, description="Results per page")]


async def _search(entity_type: str, query: str, page: int, per_page: int, formatter: Any) -> Any:
    """Relevance search on /catalog/search/ for one entity type."""
    data = await get_client().get(
        "/catalog/search/", q=query, type=entity_type, page=page, per_page=per_page
    )
    return fmt.slim_page(data, formatter)


# ---------------------------------------------------------------------------
# Catalog: tracks
# ---------------------------------------------------------------------------


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def search_tracks(
    query: Annotated[str, Field(description="Free-text search, e.g. 'strobe deadmau5'")],
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """Relevance search for tracks by free text (title, artist, remixer …)."""
    return await _search("tracks", query, page, per_page, fmt.slim_track)


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
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


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def get_track(track_id: int) -> Any:
    """Get full details of a single track by its Beatport id."""
    return fmt.slim_track(await get_client().get(f"/catalog/tracks/{track_id}/"))


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def get_track_preview(track_id: int) -> Any:
    """Get the official Beatport audio preview for a track.

    Returns the ~2-minute preview clip Beatport provides for legal
    listening before purchase (`preview_url`, a direct MP3), the clip's
    position within the full track, the track's purchase page, and its
    price. This is the only track audio the API serves; full downloads
    require purchasing the track (see `purchase_url`).
    """
    track = await get_client().get(f"/catalog/tracks/{track_id}/")
    slim = fmt.slim_track(track)
    return fmt._drop_empty(
        {
            "id": track.get("id"),
            "name": slim.get("name"),
            "artists": slim.get("artists"),
            "mix_name": slim.get("mix_name"),
            "preview_url": track.get("sample_url"),
            "preview_start_ms": track.get("sample_start_ms"),
            "preview_end_ms": track.get("sample_end_ms"),
            "streamable": track.get("is_available_for_streaming"),
            "purchase_url": slim.get("url"),
            "price": slim.get("price"),
        }
    )


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def get_purchase_links(
    track_ids: Annotated[list[int], Field(min_length=1, description="Beatport track ids")],
    ctx: Context | None = None,
) -> Any:
    """Get the beatport.com purchase page and price for one or more tracks.

    Use this to buy tracks in full quality — the API only serves previews
    (see `get_track_preview`); the full file is available after purchase on
    the returned `purchase_url`.
    """
    results = []
    total = len(track_ids)
    for index, track_id in enumerate(track_ids, start=1):
        track = await get_client().get(f"/catalog/tracks/{track_id}/")
        slim = fmt.slim_track(track)
        results.append(
            fmt._drop_empty(
                {
                    "id": track.get("id"),
                    "name": slim.get("name"),
                    "artists": slim.get("artists"),
                    "release": slim.get("release"),
                    "purchase_url": slim.get("url"),
                    "price": slim.get("price"),
                }
            )
        )
        if ctx is not None:
            await ctx.report_progress(progress=index, total=total)
    if ctx is not None:
        await ctx.info(f"Resolved purchase links for {total} track(s)")
    return {"results": results}


# ---------------------------------------------------------------------------
# Catalog: releases
# ---------------------------------------------------------------------------


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def search_releases(
    query: Annotated[str, Field(description="Release name / free-text search")],
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """Relevance search for releases (albums/EPs/singles)."""
    return await _search("releases", query, page, per_page, fmt.slim_release)


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def get_release(release_id: int) -> Any:
    """Get details of a release by id."""
    return fmt.slim_release(await get_client().get(f"/catalog/releases/{release_id}/"))


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def get_release_tracks(release_id: int, page: Page = 1, per_page: PerPage = 100) -> Any:
    """List the tracks of a release."""
    data = await get_client().get(
        f"/catalog/releases/{release_id}/tracks/", page=page, per_page=per_page
    )
    return fmt.slim_page(data, fmt.slim_track)


# ---------------------------------------------------------------------------
# Catalog: artists & labels
# ---------------------------------------------------------------------------


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def search_artists(
    query: Annotated[str, Field(description="Artist name to search for")],
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """Search artists by name."""
    return await _search("artists", query, page, per_page, fmt.slim_artist)


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
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


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def search_labels(
    query: Annotated[str, Field(description="Label name to search for")],
    page: Page = 1,
    per_page: PerPage = 25,
) -> Any:
    """Search record labels by name."""
    return await _search("labels", query, page, per_page, fmt.slim_label)


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
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


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def list_genres(page: Page = 1, per_page: PerPage = 100) -> Any:
    """List Beatport genres with their ids (used by genre_id filters)."""
    data = await get_client().get("/catalog/genres/", page=page, per_page=per_page)
    return fmt.slim_page(data, fmt.slim_genre)


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
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


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
async def get_chart_tracks(chart_id: int, page: Page = 1, per_page: PerPage = 100) -> Any:
    """List the tracks of a DJ chart."""
    data = await get_client().get(
        f"/catalog/charts/{chart_id}/tracks/", page=page, per_page=per_page
    )
    return fmt.slim_page(data, fmt.slim_track)


# ---------------------------------------------------------------------------
# Account & playlists (require the authenticated user)
# ---------------------------------------------------------------------------


@mcp.tool(tags={"account"}, annotations=READ_ONLY)
async def my_account() -> Any:
    """Get the authenticated Beatport account's profile (also a good auth check)."""
    return await get_client().get("/my/account/")


@mcp.tool(tags={"playlists"}, annotations=READ_ONLY)
async def my_playlists(page: Page = 1, per_page: PerPage = 50) -> Any:
    """List the authenticated user's playlists."""
    data = await get_client().get("/my/playlists/", page=page, per_page=per_page)
    return fmt.slim_page(data, fmt.slim_playlist)


@mcp.tool(tags={"playlists"}, annotations=READ_ONLY)
async def get_playlist_tracks(playlist_id: int, page: Page = 1, per_page: PerPage = 100) -> Any:
    """List the tracks in one of the user's playlists."""
    data = await get_client().get(
        f"/my/playlists/{playlist_id}/tracks/", page=page, per_page=per_page
    )
    return fmt.slim_page(data, fmt.slim_playlist_item)


@mcp.tool(tags={"playlists"}, annotations=WRITE)
async def create_playlist(name: Annotated[str, Field(min_length=1)]) -> Any:
    """Create a new playlist in the user's Beatport account."""
    return fmt.slim_playlist(await get_client().post("/my/playlists/", json={"name": name}))


@mcp.tool(tags={"playlists"}, annotations=WRITE)
async def add_tracks_to_playlist(
    playlist_id: int,
    track_ids: Annotated[list[int], Field(min_length=1, description="Beatport track ids")],
) -> Any:
    """Add tracks to one of the user's playlists."""
    return await get_client().post(
        f"/my/playlists/{playlist_id}/tracks/bulk/", json={"track_ids": track_ids}
    )


@mcp.tool(tags={"playlists"}, annotations=DESTRUCTIVE)
async def remove_track_from_playlist(
    playlist_id: int,
    item_id: Annotated[
        int, Field(description="Playlist item id (item_id from get_playlist_tracks, not track id)")
    ],
) -> Any:
    """Remove a single entry from one of the user's playlists."""
    return await get_client().delete(f"/my/playlists/{playlist_id}/tracks/{item_id}/")


@mcp.tool(tags={"playlists"}, annotations=DESTRUCTIVE)
async def delete_playlist(playlist_id: int, ctx: Context | None = None) -> Any:
    """Permanently delete one of the user's playlists.

    If the client supports elicitation, asks for confirmation first, since
    the deletion cannot be undone.
    """
    if ctx is not None:
        try:
            answer = await ctx.elicit(
                f"Permanently delete Beatport playlist {playlist_id}? This cannot be undone.",
                response_type=None,
            )
        except Exception:
            answer = None  # client doesn't support elicitation — annotation already warns
        if isinstance(answer, DeclinedElicitation | CancelledElicitation):
            return {"cancelled": True, "playlist_id": playlist_id}
    return await get_client().delete(f"/my/playlists/{playlist_id}/")


# ---------------------------------------------------------------------------
# Escape hatch
# ---------------------------------------------------------------------------


@mcp.tool(tags={"catalog"}, annotations=READ_ONLY)
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


# ---------------------------------------------------------------------------
# Resources — read-only reference data, addressable by URI
# ---------------------------------------------------------------------------


@mcp.resource(
    "beatport://genres",
    name="Beatport genres",
    description="The full list of Beatport genres with their ids.",
    mime_type="application/json",
    tags={"catalog"},
)
async def genres_resource() -> Any:
    data = await get_client().get("/catalog/genres/", per_page=150)
    return fmt.slim_page(data, fmt.slim_genre)


@mcp.resource(
    "beatport://account",
    name="Beatport account",
    description="The authenticated Beatport account profile.",
    mime_type="application/json",
    tags={"account"},
)
async def account_resource() -> Any:
    return await get_client().get("/my/account/")


@mcp.resource(
    "beatport://track/{track_id}",
    name="Beatport track",
    description="A single track by id, as slimmed JSON.",
    mime_type="application/json",
    tags={"catalog"},
)
async def track_resource(track_id: int) -> Any:
    return fmt.slim_track(await get_client().get(f"/catalog/tracks/{track_id}/"))


@mcp.resource(
    "beatport://release/{release_id}",
    name="Beatport release",
    description="A single release by id, as slimmed JSON.",
    mime_type="application/json",
    tags={"catalog"},
)
async def release_resource(release_id: int) -> Any:
    return fmt.slim_release(await get_client().get(f"/catalog/releases/{release_id}/"))


@mcp.resource(
    "beatport://chart/{chart_id}/tracks",
    name="Beatport chart tracks",
    description="The tracks of a DJ chart by id.",
    mime_type="application/json",
    tags={"catalog"},
)
async def chart_tracks_resource(chart_id: int) -> Any:
    data = await get_client().get(f"/catalog/charts/{chart_id}/tracks/", per_page=100)
    return fmt.slim_page(data, fmt.slim_track)


# ---------------------------------------------------------------------------
# Prompts — reusable, parameterized instructions
# ---------------------------------------------------------------------------


@mcp.prompt(tags={"catalog"})
def crate_dig(
    genre: Annotated[str, Field(description="Genre name or vibe, e.g. 'hypnotic techno'")],
    bpm_low: Annotated[int, Field(ge=40, le=300, description="Minimum BPM")] = 120,
    bpm_high: Annotated[int, Field(ge=40, le=300, description="Maximum BPM")] = 135,
    count: Annotated[int, Field(ge=1, le=100, description="How many tracks")] = 20,
) -> str:
    """Ask the model to dig a crate: build a track shortlist from Beatport."""
    return (
        f"Using the Beatport tools, find {count} {genre} tracks between {bpm_low} and "
        f"{bpm_high} BPM. First call list_genres to resolve the closest genre_id, then "
        f"filter_tracks with that genre_id and the BPM range (fall back to search_tracks "
        f"if the genre is a loose vibe). Present the results as a numbered list of "
        f"'Artist - Title (Mix) — BPM, key' with the beatport.com purchase URL for each, "
        f"and offer to save them to a new playlist with create_playlist + "
        f"add_tracks_to_playlist."
    )


@mcp.prompt(tags={"playlists"})
def analyze_playlist(
    playlist_id: Annotated[int, Field(description="Beatport playlist id (see my_playlists)")],
) -> str:
    """Ask the model to analyze the harmonic/tempo profile of a playlist."""
    return (
        f"Fetch the tracks of Beatport playlist {playlist_id} with get_playlist_tracks, "
        f"then analyze it as a DJ set: summarize the BPM range and distribution, the "
        f"Camelot/key spread and which tracks mix harmonically, the dominant genres and "
        f"labels, and suggest a play order plus any tracks that feel like outliers."
    )


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
