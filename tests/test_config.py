import pytest
from pydantic import ValidationError

from beatport_mcp.config import DOCS_CLIENT_ID, Settings


def test_from_env_reads_and_coerces(monkeypatch, tmp_path):
    monkeypatch.setenv("BEATPORT_USERNAME", "dj@example.com")
    monkeypatch.setenv("BEATPORT_PASSWORD", "secret")
    monkeypatch.setenv("BEATPORT_TIMEOUT", "12.5")
    monkeypatch.setenv("BEATPORT_TOKEN_FILE", str(tmp_path / "t.json"))

    settings = Settings.from_env()

    assert settings.username == "dj@example.com"
    assert settings.password == "secret"
    assert settings.timeout == 12.5  # coerced from str to float
    assert settings.token_file == tmp_path / "t.json"
    assert settings.client_id == DOCS_CLIENT_ID  # default preserved


def test_invalid_timeout_is_rejected(monkeypatch):
    monkeypatch.setenv("BEATPORT_TIMEOUT", "not-a-number")
    with pytest.raises(ValidationError):
        Settings.from_env()


def test_explicit_kwargs_override_env(monkeypatch):
    monkeypatch.setenv("BEATPORT_USERNAME", "from-env")
    settings = Settings(username="explicit")
    assert settings.username == "explicit"
