"""CHA-2389: non-JSON error bodies must not crash the request path."""

import asyncio

import httpx
import pytest

from src.api.client import KalshiRestClient


def _request_with_error_body(status_code: int, content: bytes):
    client = KalshiRestClient()
    request = httpx.Request("GET", "https://example.test/trade-api/v2/markets")
    response = httpx.Response(status_code, content=content, request=request)

    async def fake_get(*args, **kwargs):
        return response

    client.client.get = fake_get
    return asyncio.run(client._request("GET", "/trade-api/v2/markets"))


@pytest.mark.parametrize(
    "content",
    [
        b"<html><body>502 Bad Gateway</body></html>",
        b"Too Many Requests - retry after 60s",
    ],
    ids=["html-gateway-page", "plain-text-rate-limit"],
)
def test_non_json_error_body_returns_error_dict(content):
    result = _request_with_error_body(502, content)

    assert result["error"] is True
    assert result["status_code"] == 502
    # The raw body is preserved so an operator can see what the gateway said.
    assert content.decode() in result["detail"]["message"]
    assert result["detail"]["parse_error"]


def test_json_error_body_is_passed_through_unchanged():
    result = _request_with_error_body(
        400, b'{"error": {"code": "bad_ticker", "message": "unknown ticker"}}'
    )

    assert result["status_code"] == 400
    assert result["detail"] == {
        "error": {"code": "bad_ticker", "message": "unknown ticker"}
    }


def test_empty_error_body_yields_empty_detail():
    result = _request_with_error_body(503, b"")

    assert result["error"] is True
    assert result["detail"] == {}


def test_non_dict_json_error_body_is_wrapped():
    """`detail` must always be a mapping so callers can index it safely."""
    result = _request_with_error_body(400, b'"just a string"')

    assert result["detail"] == {"message": "just a string"}


def test_long_non_json_error_body_is_truncated():
    result = _request_with_error_body(502, b"<html>" + b"x" * 2000 + b"</html>")

    message = result["detail"]["message"]
    assert len(message) < 600
    assert message.endswith("...")
