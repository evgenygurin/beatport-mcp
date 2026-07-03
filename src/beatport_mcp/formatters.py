"""Convert verbose Beatport API responses into the typed models in models.py.

Each entity carries dozens of fields (image variants, exclusivity flags, …);
these helpers keep only the fields useful for search/browse conversations and
return Pydantic models so tools expose a real output schema.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import (
    Artist,
    Chart,
    Genre,
    Label,
    NamedRef,
    Page,
    Playlist,
    PlaylistItem,
    Release,
    Track,
)

WEB_BASE = "https://www.beatport.com"

# /catalog/search/ nests items under the entity name instead of "results"
LIST_KEYS = ("results", "tracks", "releases", "artists", "labels", "charts")


def _web(kind: str, obj: Any) -> str | None:
    """Build a beatport.com URL from an object's slug + id, if both present."""
    if isinstance(obj, dict) and obj.get("slug") and obj.get("id"):
        return f"{WEB_BASE}/{kind}/{obj['slug']}/{obj['id']}"
    return None


def _price(price: Any) -> str | None:
    if isinstance(price, dict):
        display = price.get("display")
        return display if isinstance(display, str) else None
    return price if isinstance(price, str) else None


def _named(value: Any) -> NamedRef | None:
    """Collapse {"id": 5, "name": "Melodic House", ...} to an id+name ref."""
    if isinstance(value, dict) and (value.get("id") is not None or value.get("name")):
        return NamedRef(id=value.get("id"), name=value.get("name"))
    return None


def _artist(value: Any) -> Artist:
    return Artist(id=value.get("id"), name=value.get("name"), url=_web("artist", value))


def slim_track(track: Any) -> Track:
    key = track.get("key")
    return Track(
        id=track.get("id"),
        name=track.get("name"),
        mix_name=track.get("mix_name"),
        artists=[_artist(a) for a in track.get("artists") or []],
        remixers=[_artist(r) for r in track.get("remixers") or []],
        release=_named(track.get("release")),
        genre=_named(track.get("genre")),
        sub_genre=_named(track.get("sub_genre")),
        bpm=track.get("bpm"),
        key=key.get("name") if isinstance(key, dict) else key,
        length=track.get("length"),
        publish_date=track.get("publish_date"),
        isrc=track.get("isrc"),
        catalog_number=track.get("catalog_number"),
        price=_price(track.get("price")),
        preview_url=track.get("sample_url"),
        streamable=track.get("is_available_for_streaming"),
        url=_web("track", track),
    )


def slim_release(release: Any) -> Release:
    return Release(
        id=release.get("id"),
        name=release.get("name"),
        artists=[_artist(a) for a in release.get("artists") or []],
        label=_named(release.get("label")),
        catalog_number=release.get("catalog_number"),
        release_date=release.get("new_release_date") or release.get("publish_date"),
        track_count=release.get("track_count"),
        upc=release.get("upc"),
        price=_price(release.get("price")),
        url=_web("release", release),
    )


def slim_artist(artist: Any) -> Artist:
    return _artist(artist)


def slim_label(label: Any) -> Label:
    return Label(id=label.get("id"), name=label.get("name"), url=_web("label", label))


def slim_genre(genre: Any) -> Genre:
    return Genre(id=genre.get("id"), name=genre.get("name"))


def slim_chart(chart: Any) -> Chart:
    return Chart(
        id=chart.get("id"),
        name=chart.get("name"),
        artist=_named(chart.get("artist") or chart.get("person")),
        genres=[ref for g in chart.get("genres") or [] if (ref := _named(g))],
        track_count=chart.get("track_count"),
        publish_date=chart.get("publish_date"),
    )


def slim_playlist(playlist: Any) -> Playlist:
    track_count = playlist.get("track_count")
    if track_count is None:
        track_count = playlist.get("count")
    return Playlist(
        id=playlist.get("id"),
        name=playlist.get("name"),
        track_count=track_count,
        created_date=playlist.get("created_date"),
        updated_date=playlist.get("updated_date"),
    )


def slim_playlist_item(item: Any) -> PlaylistItem:
    """Playlist entries wrap the track: {"id": …, "position": …, "track": {…}}."""
    if isinstance(item, dict) and "track" in item:
        return PlaylistItem(
            item_id=item.get("id"),
            position=item.get("position"),
            track=slim_track(item.get("track")),
        )
    return PlaylistItem(track=slim_track(item))


def slim_page[T](payload: Any, formatter: Callable[[Any], T]) -> Page[T]:
    """Format a paginated list response, applying `formatter` to each item."""
    list_key = None
    if isinstance(payload, dict):
        list_key = next((k for k in LIST_KEYS if isinstance(payload.get(k), list)), None)
    items = payload.get(list_key) if list_key else []
    return Page(
        count=payload.get("count") if isinstance(payload, dict) else None,
        page=payload.get("page") if isinstance(payload, dict) else None,
        per_page=payload.get("per_page") if isinstance(payload, dict) else None,
        has_next_page=bool(payload.get("next")) if isinstance(payload, dict) else False,
        results=[formatter(item) for item in items or []],
    )
