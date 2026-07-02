"""Configuration for the Beatport MCP server, loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BEATPORT_API_BASE = "https://api.beatport.com/v4"
TOKEN_URL = f"{BEATPORT_API_BASE}/auth/o/token/"

# Public client_id used by Beatport's own API docs (https://api.beatport.com/v4/docs/).
# It is embedded in the docs frontend bundle and is required only for the
# refresh_token grant; the password grant works without it.
DOCS_CLIENT_ID = "0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd"

DEFAULT_TOKEN_FILE = Path.home() / ".beatport-mcp" / "token.json"


@dataclass
class Settings:
    username: str = ""
    password: str = ""
    client_id: str = DOCS_CLIENT_ID
    token_file: Path = field(default_factory=lambda: DEFAULT_TOKEN_FILE)
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            username=os.environ.get("BEATPORT_USERNAME", ""),
            password=os.environ.get("BEATPORT_PASSWORD", ""),
            client_id=os.environ.get("BEATPORT_CLIENT_ID", DOCS_CLIENT_ID),
            token_file=Path(os.environ.get("BEATPORT_TOKEN_FILE", str(DEFAULT_TOKEN_FILE))),
            timeout=float(os.environ.get("BEATPORT_TIMEOUT", "30")),
        )
