# Beatport API v4 — research notes

Notes collected while building this server (July 2026).

## OpenAPI / docs

- Official interactive docs (Swagger-style React app): <https://api.beatport.com/v4/docs/>.
  The app embeds a public OAuth `client_id` (`API_CLIENT_ID` in the JS bundle):
  `0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd`.
- Community OpenAPI 3.0.3 spec (catalog subset — tracks, releases, artists, labels,
  charts, genres; `BearerAuth`):
  [jentic/jentic-public-apis](https://github.com/jentic/jentic-public-apis)
  → `apis/openapi/beatport.com/main/4.0.0/openapi.json`
  (vendored here as `src/beatport_mcp/data/beatport-v4.openapi.json`,
  used by the spec-driven server).
- Base URL: `https://api.beatport.com/v4`.

## Authentication with username/password

Two flows are used by open-source clients:

1. **Password grant** — single POST to `/v4/auth/o/token/` with
   `grant_type=password`, `username`, `password` (+ `client_id`).
   **Status July 2026: disabled for public clients.** Live-tested: the docs
   client_id returns HTTP 400 `{"error": "unauthorized_client"}`, no client_id
   returns 401 `{"error": "invalid_client"}`. The server still tries it first in
   case a user-supplied `BEATPORT_CLIENT_ID` allows it.
2. **Authorization-code flow with session login** (used by this project,
   **live-verified working**) — POST `/v4/auth/login/`
   (username/password JSON → session cookie), GET `/v4/auth/o/authorize/?response_type=code&client_id=…&redirect_uri=https://api.beatport.com/v4/auth/o/post-message/`
   (302 → `?code=…`), then POST `/v4/auth/o/token/` with
   `grant_type=authorization_code` → `access_token` (~10 h), `refresh_token`,
   `scope: "app:docs user:dj"`. Same flow as
   [beets-beatport4](https://github.com/Samik081/beets-beatport4) (which scrapes the
   docs `client_id` automatically).

## Prior art (GitHub)

| Project | What it shows |
| --- | --- |
| [Samik081/beets-beatport4](https://github.com/Samik081/beets-beatport4) | beets plugin; auth-code flow, client_id scraped from the docs page |
| [jackthedev/spotify-to-beatport](https://github.com/jackthedev/spotify-to-beatport) | password login, token refresh, `/catalog/tracks/` search, playlist create + `/my/playlists/{id}/tracks/bulk/` |
| [Dniel97/orpheusdl-beatport](https://github.com/Dniel97/orpheusdl-beatport) | full v4 API module incl. `/my/account`, subscription checks |
| [squelch303/dj-trackfix](https://github.com/squelch303/dj-trackfix) | auth-code flow with `redirect_uri=/v4/auth/o/post-message/` |
| [jentic/jentic-public-apis](https://github.com/jentic/jentic-public-apis) | OpenAPI 3.0.3 spec for the catalog endpoints |

## Endpoints used by this server (live-verified)

- `GET /catalog/search/` — **the** relevance search: `q`, `type`
  (`tracks|releases|artists|labels`), `page`, `per_page`. Items are nested under
  the entity-type key (`"tracks": […]`), not `"results"`. Note: `q` on the list
  endpoints (`/catalog/tracks/?q=…`) is ignored — use this endpoint for free text.
- `GET /catalog/tracks/` — structured filters: `name`, `artist_name`, `genre_id`,
  `bpm` (range as `low:high`, e.g. `bpm=170:175`), `order_by`, `page`, `per_page`
- `GET /catalog/tracks/{id}/`
- `GET /catalog/releases/`, `GET /catalog/releases/{id}/`, `GET /catalog/releases/{id}/tracks/`
- `GET /catalog/artists/`, `GET /catalog/artists/{id}/tracks/`
- `GET /catalog/labels/`, `GET /catalog/labels/{id}/releases/`
- `GET /catalog/genres/`
- `GET /catalog/genres/{id}/top/{n}/` — the genre's Top-N chart (used for the
  hypnotic-techno demo)
- `GET /catalog/charts/` (filter by `name=`, `genre_id`), `GET /catalog/charts/{id}/tracks/`
- `GET /my/account/`
- `GET|POST /my/playlists/`, `GET /my/playlists/{id}/tracks/`,
  `POST /my/playlists/{id}/tracks/bulk/`,
  `DELETE /my/playlists/{id}/`, `DELETE /my/playlists/{id}/tracks/{item_id}/`

List responses are paginated: `{"count", "page", "per_page", "next", "previous", "results": […]}`.
`page` comes back as a string like `"1/1587"`; `/catalog/search/` nests items under the
entity key instead of `results`.

## Track audio / previews (live-verified)

The API serves only a preview clip per track, never the full file — full audio requires
purchasing the track. Relevant track fields:

- `sample_url` — a directly playable MP3 of the ~2-minute preview (e.g.
  `https://geo-samples.beatport.com/track/….LOFI.mp3`, HTTP 200 `audio/mpeg`)
- `sample_start_ms` / `sample_end_ms` — where the clip sits in the full track
- `is_available_for_streaming` — streaming-entitlement flag
- Purchase page: `https://www.beatport.com/track/{slug}/{id}`

## Gotchas

- **Trailing slashes matter.** Paths without a trailing slash 301-redirect to the slashed
  form; the HTTP client must follow redirects (the vendored spec's paths have no trailing
  slash, so the spec-driven server sets `follow_redirects=True`).
- **`bpm` range** is a single `low:high` query param (`bpm=170:175`), not `bpm_low`/`bpm_high`.
- The community spec's response schemas are approximate (e.g. it types `track.key` as a
  string while the API returns an object), so the spec-driven server sets
  `validate_output=False`.
