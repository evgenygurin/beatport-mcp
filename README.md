# beatport-mcp

MCP server for the [Beatport API v4](https://api.beatport.com/v4/docs/), built with
[FastMCP v3](https://gofastmcp.com). Authenticates with a regular Beatport account
username/password — no API key application needed.

Search the Beatport catalog (tracks, releases, artists, labels), browse genres and DJ
charts, and manage your playlists from Claude or any other MCP client.

## Tools

| Tool | Description |
| --- | --- |
| `search_tracks` | Relevance search for tracks by free text |
| `filter_tracks` | Structured catalog filter (title, artist, genre, BPM range) |
| `get_track` | Track details by id |
| `search_releases` / `get_release` / `get_release_tracks` | Releases and their track lists |
| `search_artists` / `get_artist_tracks` | Artists and their tracks |
| `search_labels` / `get_label_releases` | Labels and their releases |
| `list_genres` | Beatport genres with ids (for `genre_id` filters) |
| `search_charts` / `get_chart_tracks` | DJ charts |
| `my_account` | Authenticated account profile (auth check) |
| `my_playlists` / `get_playlist_tracks` | Your playlists |
| `get_track_preview` / `get_purchase_links` | Official preview MP3 + purchase pages |
| `recommend_similar` | Similar tracks — LLM-suggested (via sampling) and verified against the catalog, or genre/BPM fallback |
| `create_playlist` / `add_tracks_to_playlist` | Playlist management |
| `remove_track_from_playlist` / `delete_playlist` | Playlist cleanup |
| `beatport_api_get` | Escape hatch: any GET endpoint of the v4 API, raw response |

Responses are typed: catalog tools return Pydantic models (`Track`, `Release`, `Artist`,
`Label`, `Genre`, `Chart`, `Playlist`, paginated as `Page[…]`), so FastMCP publishes a
JSON **output schema** per tool and returns validated **structured content** — clients get
a stable, declared shape with only the useful fields (id, name, artists, BPM, key, label,
prices, beatport.com URLs, …), never Beatport's dozens of raw fields. `beatport_api_get`
and `my_account` return raw JSON.

Every tool carries MCP [annotations](https://modelcontextprotocol.io/) (`readOnlyHint`,
`destructiveHint`, …) and a domain `tag` (`catalog` / `playlists` / `account`) so clients
can present the right safety UI and filter by capability.

### Resources

Read-only reference data, addressable by URI (no tool call needed):

| URI | Content |
| --- | --- |
| `beatport://genres` | Full genre list with ids |
| `beatport://account` | Authenticated account profile |
| `beatport://track/{track_id}` | A single track |
| `beatport://release/{release_id}` | A single release |
| `beatport://chart/{chart_id}/tracks` | A DJ chart's tracks |

### Prompts

| Prompt | Purpose |
| --- | --- |
| `crate_dig` | Build a track shortlist from a genre + BPM range, ready to save as a playlist |
| `analyze_playlist` | Analyze a playlist's BPM/key/genre profile as a DJ set |

Batch tools such as `get_purchase_links` stream progress and log via the MCP
`Context`, and the server closes its HTTP client cleanly on shutdown (FastMCP lifespan).
`delete_playlist` asks for confirmation via MCP elicitation before deleting (when the
client supports it). API errors surface as short, actionable messages (e.g. *"Beatport:
not found — check the id."*), and a timing middleware logs each tool call's duration at
debug level. Configuration is validated via pydantic-settings (`BEATPORT_*` env vars or a
`.env` file). `recommend_similar` uses MCP sampling (`ctx.sample`) to have the connected
LLM propose similar tracks, then verifies each against the real catalog. Over the HTTP
transport a `GET /health` route returns `{"status": "ok"}` for liveness probes. Setting
`BEATPORT_READ_ONLY=1` hides the four mutating playlist tools (create/add/remove/delete)
via FastMCP tag visibility, for a safe browse-only deployment.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/evgenygurin/beatport-mcp
cd beatport-mcp
uv sync
```

Set your Beatport credentials (see `.env.example`):

```bash
export BEATPORT_USERNAME="you@example.com"
export BEATPORT_PASSWORD="your-password"
```

Run over stdio:

```bash
uv run beatport-mcp
```

Or over HTTP:

```bash
BEATPORT_MCP_TRANSPORT=http BEATPORT_MCP_PORT=8000 uv run beatport-mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "beatport": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/beatport-mcp", "beatport-mcp"],
      "env": {
        "BEATPORT_USERNAME": "you@example.com",
        "BEATPORT_PASSWORD": "your-password"
      }
    }
  }
}
```

Claude Code: `claude mcp add beatport -e BEATPORT_USERNAME=... -e BEATPORT_PASSWORD=... -- uv run --directory /path/to/beatport-mcp beatport-mcp`

## How authentication works

Only a Beatport username and password are needed. Under the hood the server first
tries the OAuth2 **password grant** on `POST /v4/auth/o/token/` (Beatport currently
answers `unauthorized_client` for public clients, but it is kept for users with their
own `BEATPORT_CLIENT_ID`), then falls back to the flow Beatport's own docs frontend
uses — verified working:

```
1. POST /v4/auth/login/            {"username": …, "password": …}   → session cookie
2. GET  /v4/auth/o/authorize/      ?response_type=code&client_id=…
                                   &redirect_uri=…/auth/o/post-message/ → 302 ?code=…
3. POST /v4/auth/o/token/          grant_type=authorization_code       → tokens
```

The result is an `access_token` (Bearer, ~10 h) plus `refresh_token`. Refreshing uses
`grant_type=refresh_token` with a `client_id`; by default this project uses the public
client_id of Beatport's own Swagger docs frontend (the same approach as
[beets-beatport4](https://github.com/Samik081/beets-beatport4) and other open-source
clients). Override it with `BEATPORT_CLIENT_ID`.

Tokens are cached in `~/.beatport-mcp/token.json` (chmod 600) and refreshed
automatically; a 401 triggers one transparent re-auth + retry.

A standalone ~100-line example of the raw flow lives in
[`examples/login_flow.py`](examples/login_flow.py); using the packaged async
client is shown in [`examples/use_client.py`](examples/use_client.py).

## OpenAPI

- Interactive docs: <https://api.beatport.com/v4/docs/>
- A community OpenAPI 3.0.3 spec for the v4 catalog endpoints is vendored at
  [`src/beatport_mcp/data/beatport-v4.openapi.json`](src/beatport_mcp/data/beatport-v4.openapi.json)
  (source: [jentic/jentic-public-apis](https://github.com/jentic/jentic-public-apis)).
- `python -m beatport_mcp.openapi_server` runs an alternative, spec-driven server that
  auto-generates one MCP tool per OpenAPI operation via `FastMCP.from_openapi` —
  useful when you want raw spec-complete access instead of the curated tools.
- Or set `BEATPORT_INCLUDE_RAW=1` to mount that spec-driven server into the main one
  (`mcp.mount(..., namespace="raw")`), exposing both the curated tools and the raw
  `raw_listTracks` / `raw_getTrack` / … operations from a single process.

See [docs/research.md](docs/research.md) for notes on the API surface and prior art.

## Development

```bash
uv sync
uv run pytest       # tests (httpx MockTransport + in-memory FastMCP client)
uv run ruff check . # lint
uv run ruff format .
uv run mypy         # strict typing
```

## Disclaimer

This is an unofficial client. A Beatport account (and for streaming-related endpoints a
Beatport subscription) is required; use of the API must comply with Beatport's terms of
service. Credentials are only ever sent to `api.beatport.com`.
