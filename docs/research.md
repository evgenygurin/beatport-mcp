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
  (vendored here as `openapi/beatport-v4.openapi.json`, also copied to
  `src/beatport_mcp/data/` for the spec-driven server).
- Base URL: `https://api.beatport.com/v4`.

## Authentication with username/password

Two flows are used by open-source clients:

1. **Password grant** (used by this project) — single POST to
   `/v4/auth/o/token/` with `grant_type=password`, `username`, `password`
   (+ `client_id`). Returns `access_token` (~10 h), `refresh_token`, `expires_in`,
   `scope`. Refresh via `grant_type=refresh_token` + `client_id`.
2. **Authorization-code flow with session login** — POST `/v4/auth/login/`
   (username/password → session cookie), GET `/v4/auth/o/authorize/?response_type=code&client_id=…&redirect_uri=https://api.beatport.com/v4/auth/o/post-message/`
   (302 → `?code=…`), then POST `/v4/auth/o/token/` with
   `grant_type=authorization_code`. Used by
   [beets-beatport4](https://github.com/Samik081/beets-beatport4) (which scrapes the
   docs `client_id` automatically) and others.

## Prior art (GitHub)

| Project | What it shows |
| --- | --- |
| [Samik081/beets-beatport4](https://github.com/Samik081/beets-beatport4) | beets plugin; auth-code flow, client_id scraped from the docs page |
| [jackthedev/spotify-to-beatport](https://github.com/jackthedev/spotify-to-beatport) | password login, token refresh, `/catalog/tracks/` search, playlist create + `/my/playlists/{id}/tracks/bulk/` |
| [Dniel97/orpheusdl-beatport](https://github.com/Dniel97/orpheusdl-beatport) | full v4 API module incl. `/my/account`, subscription checks |
| [squelch303/dj-trackfix](https://github.com/squelch303/dj-trackfix) | auth-code flow with `redirect_uri=/v4/auth/o/post-message/` |
| [jentic/jentic-public-apis](https://github.com/jentic/jentic-public-apis) | OpenAPI 3.0.3 spec for the catalog endpoints |

## Endpoints used by this server

- `GET /catalog/tracks/` — filters seen in the wild: `q`, `artist_name`, `genre_id`,
  `bpm_low`, `bpm_high`, `page`, `per_page`, `order_by`
- `GET /catalog/tracks/{id}/`
- `GET /catalog/releases/`, `GET /catalog/releases/{id}/`, `GET /catalog/releases/{id}/tracks/`
- `GET /catalog/artists/`, `GET /catalog/artists/{id}/tracks/`
- `GET /catalog/labels/`, `GET /catalog/labels/{id}/releases/`
- `GET /catalog/genres/`
- `GET /catalog/charts/`, `GET /catalog/charts/{id}/tracks/`
- `GET /my/account/`
- `GET|POST /my/playlists/`, `GET /my/playlists/{id}/tracks/`,
  `POST /my/playlists/{id}/tracks/bulk/`

List responses are paginated: `{"count", "page", "per_page", "next", "previous", "results": […]}`.
