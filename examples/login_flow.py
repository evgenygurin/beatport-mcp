"""Minimal, dependency-light example: authenticate to the Beatport API v4
with a plain username/password and make a few requests.

Verified working flow (July 2026). Beatport has disabled the OAuth2
*password grant* for its public clients (the token endpoint answers
``{"error": "unauthorized_client"}``), so the reliable path is the one
Beatport's own docs frontend uses:

    1. POST /v4/auth/login/                      username+password -> session cookie
    2. GET  /v4/auth/o/authorize/?...            302 redirect with ?code=...
    3. POST /v4/auth/o/token/                    grant_type=authorization_code -> tokens

Usage:
    BEATPORT_USERNAME=you@example.com BEATPORT_PASSWORD=... \
        uv run python examples/login_flow.py

This is the same flow the MCP server uses internally (see
src/beatport_mcp/auth.py), shown here as a standalone script.
"""

import json
import os
import sys
from urllib.parse import parse_qs, urlsplit

import httpx

API = "https://api.beatport.com/v4"

# Public client_id of Beatport's API docs frontend (https://api.beatport.com/v4/docs/),
# extracted from its JS bundle (Config.API_CLIENT_ID).
CLIENT_ID = "0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd"
REDIRECT_URI = f"{API}/auth/o/post-message/"


def login(username: str, password: str) -> dict:
    """Full username/password login -> token dict with access_token + refresh_token."""
    with httpx.Client(base_url=API) as http:
        # 1. session login (sets cookies on the client)
        response = http.post("/auth/login/", json={"username": username, "password": password})
        response.raise_for_status()

        # 2. authorize -> 302 whose Location carries the authorization code
        response = http.get(
            "/auth/o/authorize/",
            params={
                "response_type": "code",
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
            },
        )
        code = parse_qs(urlsplit(response.headers["location"]).query)["code"][0]

        # 3. exchange the code for tokens
        response = http.post(
            "/auth/o/token/",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
            },
        )
        response.raise_for_status()
        return response.json()
        # -> {"access_token": "...", "expires_in": 36000, "token_type": "Bearer",
        #     "scope": "app:docs user:dj", "refresh_token": "..."}


def refresh(refresh_token: str) -> dict:
    """Get a fresh access token once the old one expires (~10 h)."""
    response = httpx.post(
        f"{API}/auth/o/token/",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    username = os.environ.get("BEATPORT_USERNAME")
    password = os.environ.get("BEATPORT_PASSWORD")
    if not (username and password):
        sys.exit("Set BEATPORT_USERNAME and BEATPORT_PASSWORD first.")

    token = login(username, password)
    headers = {"Authorization": f"Bearer {token['access_token']}"}

    # Who am I?
    account = httpx.get(f"{API}/my/account/", headers=headers).json()
    print("Logged in as:", account.get("username"))

    # Relevance search (note: items come back under the entity-type key, e.g. "tracks")
    found = httpx.get(
        f"{API}/catalog/search/",
        params={"q": "strobe deadmau5", "type": "tracks", "per_page": 5},
        headers=headers,
    ).json()
    for t in found.get("tracks", []):
        artists = ", ".join(a["name"] for a in t.get("artists", []))
        print(f"  [{t['id']}] {artists} - {t['name']} ({t.get('mix_name')}) {t.get('bpm')} BPM")

    # Structured filtering: BPM ranges use "low:high"
    dnb = httpx.get(
        f"{API}/catalog/tracks/",
        params={"genre_id": 1, "bpm": "170:175", "per_page": 3},
        headers=headers,
    ).json()
    print("DnB 170-175 BPM:", [t["name"] for t in dnb.get("results", [])])

    # List genres
    genres = httpx.get(f"{API}/catalog/genres/", params={"per_page": 5}, headers=headers).json()
    print(
        "Some genres:",
        json.dumps(
            [{"id": g["id"], "name": g["name"]} for g in genres.get("results", [])],
            ensure_ascii=False,
        ),
    )


if __name__ == "__main__":
    main()
