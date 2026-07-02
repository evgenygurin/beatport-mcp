"""Minimal, dependency-light example: authenticate to the Beatport API v4
with a username/password (OAuth2 password grant) and make a few requests.

Usage:
    BEATPORT_USERNAME=you@example.com BEATPORT_PASSWORD=... \
        uv run python examples/password_grant.py

This is the same flow the MCP server uses internally (see
src/beatport_mcp/auth.py), shown here as a standalone script.
"""

import json
import os
import sys

import httpx

API = "https://api.beatport.com/v4"
TOKEN_URL = f"{API}/auth/o/token/"

# Public client_id of Beatport's API docs frontend (https://api.beatport.com/v4/docs/).
# Needed for the refresh_token grant; the password grant works even without it.
CLIENT_ID = "0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd"


def login(username: str, password: str) -> dict:
    """Exchange username/password for an access + refresh token."""
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": CLIENT_ID,
        },
    )
    response.raise_for_status()
    return response.json()
    # -> {"access_token": "...", "expires_in": 36000, "token_type": "Bearer",
    #     "scope": "app:docs user:dj", "refresh_token": "..."}


def refresh(refresh_token: str) -> dict:
    """Get a fresh access token once the old one expires."""
    response = httpx.post(
        TOKEN_URL,
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
    print("Logged in as:", account.get("username") or account.get("email"))

    # Search tracks
    tracks = httpx.get(
        f"{API}/catalog/tracks/",
        params={"q": "strobe deadmau5", "per_page": 5},
        headers=headers,
    ).json()
    for t in tracks.get("results", []):
        artists = ", ".join(a["name"] for a in t.get("artists", []))
        print(f"  [{t['id']}] {artists} - {t['name']} ({t.get('mix_name')}) {t.get('bpm')} BPM")

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
