"""Configuration for the Beatport MCP server, loaded from environment variables.

Settings are read from ``BEATPORT_*`` environment variables via
pydantic-settings, which validates and coerces them (e.g. ``BEATPORT_TIMEOUT``
must parse as a float). A ``.env`` file in the working directory is honored.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BEATPORT_API_BASE = "https://api.beatport.com/v4"
TOKEN_URL = f"{BEATPORT_API_BASE}/auth/o/token/"

# Public client_id used by Beatport's own API docs (https://api.beatport.com/v4/docs/).
# It is embedded in the docs frontend bundle and is required only for the
# refresh_token grant; the password grant works without it.
DOCS_CLIENT_ID = "0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd"

DEFAULT_TOKEN_FILE = Path.home() / ".beatport-mcp" / "token.json"


class Settings(BaseSettings):
    """Server settings, sourced from ``BEATPORT_*`` env vars (or a ``.env`` file)."""

    model_config = SettingsConfigDict(env_prefix="BEATPORT_", env_file=".env", extra="ignore")

    username: str = ""
    password: str = ""
    client_id: str = DOCS_CLIENT_ID
    token_file: Path = DEFAULT_TOKEN_FILE
    timeout: float = Field(default=30.0, gt=0)
    # When true, the mutating playlist tools (create/add/remove/delete) are
    # hidden — a safe, read-only deployment for untrusted contexts.
    read_only: bool = False
    # When true, also mount the spec-driven OpenAPI server under the `raw_`
    # namespace, exposing one schema'd tool per Beatport v4 operation.
    include_raw: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        """Construct from the environment (kept for call-site readability)."""
        return cls()
