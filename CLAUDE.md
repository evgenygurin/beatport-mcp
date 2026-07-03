# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Tooling is [uv](https://docs.astral.sh/uv/) on Python 3.12.

```bash
uv sync                       # install deps (incl. dev group)
uv run pytest                 # run all tests
uv run pytest tests/test_server.py::test_search_tracks_returns_slim_results  # single test
uv run pytest -k elicitation  # tests matching an expression
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy                   # strict type check (packages = beatport_mcp)
uv run beatport-mcp           # run the curated server over stdio
```

`pytest` is configured with `asyncio_mode = "auto"` — async test functions need no decorator.

### Running against the live API

Unit tests never touch the network. To exercise a change end-to-end, set real credentials
and drive the in-memory client:

```bash
BEATPORT_USERNAME=... BEATPORT_PASSWORD=... uv run python -c '...'
```

In this sandbox, live HTTPS also needs `SSL_CERT_FILE=/root/.ccr/ca-bundle.crt`.

## Architecture

An MCP server (FastMCP v3) wrapping the **Beatport API v4**. Request flow for a tool call:

`server.py` tool → `get_client()` (module-global `BeatportClient` singleton) →
`client.py` (auth + HTTP) → `TokenManager` in `auth.py` → response dict →
`formatters.py` builds a typed `models.py` model → returned to FastMCP.

- **`server.py`** — the curated FastMCP server (`mcp`) and all `@mcp.tool` / `@mcp.resource`
  / `@mcp.prompt` definitions, the `/health` custom route, `lifespan`, `TimingMiddleware`
  registration, and `main()`. Tools carry `tags` and `ToolAnnotations` (`READ_ONLY` /
  `WRITE` / `DESTRUCTIVE` presets). `_search[T]` is the shared helper behind the four
  `search_*` tools; the mutating playlist tools also carry the `write` tag.
- **`client.py`** — `BeatportClient`, an async httpx wrapper: injects the bearer token,
  retries once on 401 after re-auth, and `follow_redirects=True`.
- **`auth.py`** — `TokenManager`: disk-cached OAuth tokens with a single-flight
  `asyncio.Lock`, auto-refresh, and 0600 file perms keyed to username/client_id.
- **`formatters.py` + `models.py`** — slim raw Beatport JSON into typed Pydantic models.
- **`config.py`** — `Settings` (pydantic-settings, `BEATPORT_*` env prefix, `.env` support).
- **`openapi_server.py`** — a *second, alternative* server built with `FastMCP.from_openapi`
  from the vendored spec, using a `_BearerAuth(httpx.Auth)` hook. Run standalone via
  `python -m beatport_mcp.openapi_server`, or mount it into the curated server (see below).

### Two auth flows (important)

Beatport has **disabled the OAuth2 password grant** for public clients (returns
`unauthorized_client`). `TokenManager._login` tries it first anyway (in case a user supplies
their own `BEATPORT_CLIENT_ID`), then falls back to the flow Beatport's own docs frontend
uses and which is verified working: `POST /auth/login/` → `GET /auth/o/authorize/` (302 with
`?code=`) → `POST /auth/o/token/` (`authorization_code`). The default `client_id` is scraped
from that docs frontend. Do not "simplify" auth back to a single password-grant POST.

### Typed structured output

Catalog tools annotate concrete return types (`m.Page[m.Track]`, `m.Track`, `m.Preview`, …)
so FastMCP publishes a per-tool output schema and returns validated structured content.
Consequences to remember:

- In tests, a typed tool result's `.data` is a **reconstructed model object** (attribute
  access: `result.data.results[0].id`), while `.structured_content` is a plain **dict**.
- **Resources cannot return model instances** — they must return `str`/`bytes`/`dict`, so
  resource functions call `.model_dump(mode="json")`. Tools return the model directly.
- Raw passthroughs (`my_account`, `add/remove/delete` playlist, `beatport_api_get`) stay
  `dict[str, Any]`/`Any` and use `cast(...)` to satisfy strict mypy on `client.get()`'s `Any`.

### Non-obvious gotchas

- **Error messages are made friendly in `client.py`, not in middleware.** FastMCP resolves a
  tool's exception into its own `ToolError` *below* the middleware layer, so a middleware
  `on_call_tool` never catches `BeatportAPIError`. `BeatportAPIError.__str__` is the friendly
  message (`friendly_api_error`); the raw body stays on `.detail`.
- **A query string embedded in a path is lifted into params** in `client.request` — httpx
  replaces the URL query when `params=` is passed, which would silently drop
  `beatport_api_get("/catalog/search/?q=…")`.
- **Search endpoints nest items under the entity key** (`{"tracks": [...]}`), not `results`;
  `slim_page` handles both via `LIST_KEYS`. The list endpoints ignore `q=` — free-text search
  goes through `/catalog/search/?type=…`, structured filtering through `/catalog/tracks/`
  (BPM ranges use the `bpm=low:high` string form, not `bpm_low`/`bpm_high`).
- **`set_read_only()` and `mount_raw()` mutate the global `mcp` singleton.** Tests that toggle
  read-only must restore it in a `finally`; `mount_raw()` is idempotent.

### Runtime flags (env)

`BEATPORT_READ_ONLY=1` hides the `write`-tagged tools (`mcp.disable(tags={"write"})`).
`BEATPORT_INCLUDE_RAW=1` mounts the OpenAPI server under the `raw_` namespace.
`BEATPORT_MCP_TRANSPORT=http` (+ `_HOST`/`_PORT`) runs over HTTP instead of stdio.

## Testing approach

Two fake strategies: `tests/conftest.py`'s `FakeBeatport` backs an `httpx.MockTransport` for
`auth.py`/`client.py` tests (real login/refresh/401 paths); `tests/test_server.py`'s
`FakeBeatportClient` is monkeypatched onto `server._client` to exercise tools without HTTP.
The vendored spec lives at `src/beatport_mcp/data/beatport-v4.openapi.json` (used by
`openapi_server`); keep it and the docs in sync if it changes.
