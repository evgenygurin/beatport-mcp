from beatport_mcp.client import BeatportAPIError, friendly_api_error
from beatport_mcp.server import _parse_suggestions


def test_parse_suggestions_strips_bullets_and_numbering():
    text = "1. Adam Beyer - Your Mind\n- Charlotte de Witte - Doppler\n\n2) Kobosil - Zeit"
    assert _parse_suggestions(text) == [
        "Adam Beyer - Your Mind",
        "Charlotte de Witte - Doppler",
        "Kobosil - Zeit",
    ]


def test_friendly_messages_by_status():
    assert "BEATPORT_USERNAME" in friendly_api_error(401, "x")
    assert "subscription" in friendly_api_error(403, "x")
    assert "not found" in friendly_api_error(404, "x")
    assert "rate limiting" in friendly_api_error(429, "x")
    assert "unavailable" in friendly_api_error(503, "x")


def test_unmapped_status_falls_back_to_detail():
    message = friendly_api_error(418, "teapot")
    assert "418" in message and "teapot" in message


def test_error_message_is_friendly_and_detail_preserved():
    exc = BeatportAPIError(404, '{"detail": "Not found."}')
    assert "not found" in str(exc)
    assert exc.detail == '{"detail": "Not found."}'  # raw detail still available
