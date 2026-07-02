"""Slim down verbose Beatport API responses to LLM-friendly dictionaries.

Beatport list responses look like::

    {"count": 137, "next": "...", "previous": null, "results": [...], ...}

and each entity (track/release/...) carries dozens of fields (image
variants, exclusivity flags, ...). These helpers keep only the fields
useful for search/browse conversations. Unknown shapes are passed through
unchanged so the tools never lose data on API changes.
"""

from __future__ import annotations

from typing import Any

WEB_BASE = "https://www.beatport.com"


def _named(value: Any) -> Any:
    """Collapse {"id": 5, "name": "Melodic House", ...} to its name + id."""
    if isinstance(value, dict):
        slim = {k: value[k] for k in ("id", "name") if k in value}
        return slim or value
    return value


def slim_track(track: Any) -> Any:
    if not isinstance(track, dict):
        return track
    key = track.get("key")
    result: dict[str, Any] = {
        "id": track.get("id"),
        "name": track.get("name"),
        "mix_name": track.get("mix_name"),
        "artists": [_named(a) for a in track.get("artists") or []],
        "remixers": [_named(r) for r in track.get("remixers") or []],
        "release": _named(track.get("release")),
        "genre": _named(track.get("genre")),
        "sub_genre": _named(track.get("sub_genre")),
        "bpm": track.get("bpm"),
        "key": key.get("name") if isinstance(key, dict) else key,
        "length": track.get("length"),
        "publish_date": track.get("publish_date"),
        "isrc": track.get("isrc"),
        "catalog_number": track.get("catalog_number"),
        "price": _price(track.get("price")),
    }
    if track.get("slug") and track.get("id"):
        result["url"] = f"{WEB_BASE}/track/{track['slug']}/{track['id']}"
    return _drop_empty(result)


def slim_release(release: Any) -> Any:
    if not isinstance(release, dict):
        return release
    result = {
        "id": release.get("id"),
        "name": release.get("name"),
        "artists": [_named(a) for a in release.get("artists") or []],
        "label": _named(release.get("label")),
        "catalog_number": release.get("catalog_number"),
        "release_date": release.get("new_release_date") or release.get("publish_date"),
        "track_count": release.get("track_count"),
        "upc": release.get("upc"),
        "price": _price(release.get("price")),
    }
    if release.get("slug") and release.get("id"):
        result["url"] = f"{WEB_BASE}/release/{release['slug']}/{release['id']}"
    return _drop_empty(result)


def slim_artist(artist: Any) -> Any:
    if not isinstance(artist, dict):
        return artist
    result = {
        "id": artist.get("id"),
        "name": artist.get("name"),
    }
    if artist.get("slug") and artist.get("id"):
        result["url"] = f"{WEB_BASE}/artist/{artist['slug']}/{artist['id']}"
    return _drop_empty(result)


def slim_label(label: Any) -> Any:
    if not isinstance(label, dict):
        return label
    result = {
        "id": label.get("id"),
        "name": label.get("name"),
    }
    if label.get("slug") and label.get("id"):
        result["url"] = f"{WEB_BASE}/label/{label['slug']}/{label['id']}"
    return _drop_empty(result)


def slim_genre(genre: Any) -> Any:
    return _named(genre)


def slim_chart(chart: Any) -> Any:
    if not isinstance(chart, dict):
        return chart
    return _drop_empty(
        {
            "id": chart.get("id"),
            "name": chart.get("name"),
            "artist": _named(chart.get("artist") or chart.get("person")),
            "genres": [_named(g) for g in chart.get("genres") or []],
            "track_count": chart.get("track_count"),
            "publish_date": chart.get("publish_date"),
        }
    )


def slim_playlist(playlist: Any) -> Any:
    if not isinstance(playlist, dict):
        return playlist
    track_count = playlist.get("track_count")
    if track_count is None:
        track_count = playlist.get("count")
    return _drop_empty(
        {
            "id": playlist.get("id"),
            "name": playlist.get("name"),
            "track_count": track_count,
            "created_date": playlist.get("created_date"),
            "updated_date": playlist.get("updated_date"),
        }
    )


def slim_playlist_item(item: Any) -> Any:
    """Playlist entries wrap the track: {"id": …, "position": …, "track": {…}}."""
    if isinstance(item, dict) and "track" in item:
        return _drop_empty(
            {
                "item_id": item.get("id"),
                "position": item.get("position"),
                "track": slim_track(item.get("track")),
            }
        )
    return slim_track(item)


# /catalog/search/ nests items under the entity name instead of "results"
LIST_KEYS = ("results", "tracks", "releases", "artists", "labels", "charts")


def slim_page(payload: Any, item_formatter: Any = None) -> Any:
    """Format a paginated list response, applying `item_formatter` per item."""
    if not isinstance(payload, dict):
        return payload
    list_key = next((k for k in LIST_KEYS if isinstance(payload.get(k), list)), None)
    if list_key is None:
        return payload
    items = payload[list_key]
    if item_formatter is not None:
        items = [item_formatter(item) for item in items]
    return _drop_empty(
        {
            "count": payload.get("count"),
            "page": payload.get("page"),
            "per_page": payload.get("per_page"),
            "has_next_page": bool(payload.get("next")),
            "results": items,
        },
        keep=("results", "has_next_page"),
    )


def _price(price: Any) -> Any:
    if isinstance(price, dict):
        return price.get("display") or price
    return price


def _drop_empty(data: dict[str, Any], keep: tuple[str, ...] = ()) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v not in (None, [], {}, "") or k in keep}
