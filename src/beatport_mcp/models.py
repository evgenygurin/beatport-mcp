"""Typed output models for the Beatport MCP server.

Tools annotate their return type with these Pydantic models, so FastMCP
generates a JSON output schema and returns validated structured content —
clients get a stable, declared shape (only the useful fields, never
Beatport's dozens of raw image/exclusivity fields) instead of loose JSON.
"""

from __future__ import annotations

from pydantic import BaseModel


class NamedRef(BaseModel):
    """A minimal id+name reference (nested genre/release/label pointers)."""

    id: int | None = None
    name: str | None = None


class Artist(BaseModel):
    id: int | None = None
    name: str | None = None
    url: str | None = None


class Label(BaseModel):
    id: int | None = None
    name: str | None = None
    url: str | None = None


class Genre(BaseModel):
    id: int | None = None
    name: str | None = None


class Track(BaseModel):
    id: int | None = None
    name: str | None = None
    mix_name: str | None = None
    artists: list[Artist] = []
    remixers: list[Artist] = []
    release: NamedRef | None = None
    genre: NamedRef | None = None
    sub_genre: NamedRef | None = None
    bpm: int | None = None
    key: str | None = None
    length: str | None = None
    publish_date: str | None = None
    isrc: str | None = None
    catalog_number: str | None = None
    price: str | None = None
    preview_url: str | None = None
    streamable: bool | None = None
    url: str | None = None


class Release(BaseModel):
    id: int | None = None
    name: str | None = None
    artists: list[Artist] = []
    label: NamedRef | None = None
    catalog_number: str | None = None
    release_date: str | None = None
    track_count: int | None = None
    upc: str | None = None
    price: str | None = None
    url: str | None = None


class Chart(BaseModel):
    id: int | None = None
    name: str | None = None
    artist: NamedRef | None = None
    genres: list[NamedRef] = []
    track_count: int | None = None
    publish_date: str | None = None


class Playlist(BaseModel):
    id: int | None = None
    name: str | None = None
    track_count: int | None = None
    created_date: str | None = None
    updated_date: str | None = None


class PlaylistItem(BaseModel):
    item_id: int | None = None
    position: int | None = None
    track: Track | None = None


class Preview(BaseModel):
    id: int | None = None
    name: str | None = None
    artists: list[Artist] = []
    mix_name: str | None = None
    preview_url: str | None = None
    preview_start_ms: int | None = None
    preview_end_ms: int | None = None
    streamable: bool | None = None
    purchase_url: str | None = None
    price: str | None = None


class PurchaseLink(BaseModel):
    id: int | None = None
    name: str | None = None
    artists: list[Artist] = []
    release: NamedRef | None = None
    purchase_url: str | None = None
    price: str | None = None


class PurchaseLinks(BaseModel):
    results: list[PurchaseLink] = []


class Recommendations(BaseModel):
    seed: Track
    via: str
    results: list[Track] = []


class Page[T](BaseModel):
    """A paginated list response."""

    count: int | None = None
    page: str | None = None
    per_page: int | None = None
    has_next_page: bool = False
    results: list[T] = []
