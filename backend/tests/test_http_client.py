"""Retry policy, host pinning and response validation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from bill_pipeline.http_client import (
    HttpClient,
    HttpStatusError,
    InvalidContentTypeError,
    InvalidJsonError,
    RawResponse,
    ResponseTooLargeError,
    StdlibTransport,
    TransportError,
    UnsafeRedirectError,
)

URL = "https://bills-api.parliament.uk/api/v1/Bills"
JSON_HEADERS = {"content-type": "application/json; charset=utf-8"}


class FakeTransport:
    """Replays a scripted sequence of responses or exceptions."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, Mapping[str, str]]] = []

    def perform(self, url: str, headers: Mapping[str, str]) -> RawResponse:
        self.calls.append((url, dict(headers)))
        outcome = self.outcomes.pop(0) if self.outcomes else self.outcomes
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, RawResponse)
        return outcome


def ok(payload: dict[str, Any] | None = None) -> RawResponse:
    return RawResponse(200, JSON_HEADERS, json.dumps(payload or {"ok": True}).encode(), URL)


def status(code: int, headers: dict[str, str] | None = None) -> RawResponse:
    return RawResponse(code, {**JSON_HEADERS, **(headers or {})}, b"{}", URL)


def make_client(transport: FakeTransport, **kwargs: Any) -> tuple[HttpClient, list[float]]:
    """Build a client alongside the list of backoff delays it slept for."""
    slept: list[float] = []
    client = HttpClient(
        transport=transport,
        user_agent="uk-bill-pipeline/1 (+https://example.invalid)",
        sleeper=slept.append,
        jitter=lambda: 0.0,
        backoff_base_seconds=0.5,
        **kwargs,
    )
    return client, slept


def test_successful_request_sends_the_required_headers() -> None:
    transport = FakeTransport(ok({"totalResults": 0, "items": []}))
    client, _ = make_client(transport)
    assert client.get_json(URL) == {"totalResults": 0, "items": []}

    _, headers = transport.calls[0]
    assert headers["Accept"] == "application/json"
    assert "uk-bill-pipeline" in headers["User-Agent"]
    assert "https://" in headers["User-Agent"]


def test_query_parameters_are_encoded_onto_the_url() -> None:
    transport = FakeTransport(ok())
    make_client(transport)[0].get_json(URL, {"Session": 40, "Take": 100})
    assert transport.calls[0][0] == f"{URL}?Session=40&Take=100"


@pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
def test_retryable_statuses_are_retried_then_succeed(code: int) -> None:
    transport = FakeTransport(status(code), status(code), ok())
    client, _ = make_client(transport)
    assert client.get_json(URL) == {"ok": True}
    assert client.retry_count == 2
    assert client.request_count == 3


@pytest.mark.parametrize("code", [400, 401, 403, 404, 410, 422])
def test_ordinary_client_errors_are_not_retried(code: int) -> None:
    transport = FakeTransport(status(code), ok())
    client, _ = make_client(transport)
    with pytest.raises(HttpStatusError) as excinfo:
        client.get_json(URL)
    assert excinfo.value.status == code
    assert client.retry_count == 0
    assert len(transport.calls) == 1


def test_retries_are_bounded_at_three() -> None:
    transport = FakeTransport(*[status(503) for _ in range(6)])
    client, _ = make_client(transport)
    with pytest.raises(HttpStatusError):
        client.get_json(URL)
    assert len(transport.calls) == 4  # one attempt plus three retries
    assert client.retry_count == 3


def test_retry_after_is_honoured() -> None:
    transport = FakeTransport(status(429, {"retry-after": "7"}), ok())
    client, slept = make_client(transport)
    client.get_json(URL)
    assert slept == [7.0]


def test_retry_after_is_capped() -> None:
    transport = FakeTransport(status(429, {"retry-after": "9999"}), ok())
    client, slept = make_client(transport)
    client.get_json(URL)
    assert slept == [20.0]


def test_unparsable_retry_after_falls_back_to_exponential_backoff() -> None:
    transport = FakeTransport(
        status(429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        status(429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        ok(),
    )
    client, slept = make_client(transport)
    client.get_json(URL)
    assert slept == [0.5, 1.0]


def test_timeouts_are_retried_then_reported() -> None:
    transport = FakeTransport(*[TransportError("Timed out requesting") for _ in range(4)])
    client, _ = make_client(transport)
    with pytest.raises(TransportError):
        client.get_json(URL)
    assert len(transport.calls) == 4


def test_oversized_response_is_rejected() -> None:
    transport = FakeTransport(*[ResponseTooLargeError("too big") for _ in range(4)])
    with pytest.raises(ResponseTooLargeError):
        make_client(transport)[0].get_json(URL)


def test_non_json_content_type_is_rejected_without_retrying() -> None:
    transport = FakeTransport(RawResponse(200, {"content-type": "text/html"}, b"<html>", URL))
    with pytest.raises(InvalidContentTypeError):
        make_client(transport)[0].get_json(URL)


def test_malformed_json_is_rejected() -> None:
    transport = FakeTransport(RawResponse(200, JSON_HEADERS, b"{not json", URL))
    with pytest.raises(InvalidJsonError):
        make_client(transport)[0].get_json(URL)


def test_json_array_at_the_top_level_is_rejected() -> None:
    transport = FakeTransport(RawResponse(200, JSON_HEADERS, b"[1,2,3]", URL))
    with pytest.raises(InvalidJsonError):
        make_client(transport)[0].get_json(URL)


# ---------------------------------------------------------------------------
# Host pinning
# ---------------------------------------------------------------------------


def test_transport_refuses_a_request_to_another_host() -> None:
    transport = StdlibTransport()
    with pytest.raises(UnsafeRedirectError):
        transport.perform("https://example.invalid/steal", {})


def test_transport_refuses_plain_http() -> None:
    transport = StdlibTransport()
    with pytest.raises(UnsafeRedirectError):
        transport.perform("http://bills-api.parliament.uk/api/v1/Bills", {})


def test_redirect_to_another_host_is_refused() -> None:
    transport = StdlibTransport()
    with pytest.raises(UnsafeRedirectError, match="not the pinned source"):
        transport._validate_redirect(URL, "https://evil.invalid/collect")


def test_redirect_within_the_pinned_host_is_allowed() -> None:
    transport = StdlibTransport()
    assert transport._validate_redirect(URL, "/api/v1/Bills?Skip=0") == (
        "https://bills-api.parliament.uk/api/v1/Bills?Skip=0"
    )
