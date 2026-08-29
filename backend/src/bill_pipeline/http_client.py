"""Standard-library HTTP client with retries, size limits and host pinning.

Deliberately built on :mod:`http.client` rather than a third-party library so
the deployment package stays tiny. Using ``http.client`` directly (rather than
``urllib.request``) buys two things the security requirements need:

* a genuine split between the connect timeout and the read timeout, and
* manual redirect handling, so a redirect away from the pinned Parliament host
  is refused instead of silently followed.
"""

from __future__ import annotations

import http.client
import json
import random
import ssl
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

from .config import ALLOWED_SOURCE_HOSTS

#: Statuses worth retrying. Everything else in the 4xx range is a client error
#: that will not improve by being asked again.
RETRYABLE_STATUSES: frozenset[int] = frozenset({408, 429})

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 3
DEFAULT_MAX_ATTEMPTS = 4  # one initial attempt plus three retries
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
MAX_BACKOFF_SECONDS = 20.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 3.0


class HttpError(RuntimeError):
    """Base class for every failure raised by this module."""


class TransportError(HttpError):
    """The request could not be completed at the network level."""


class HttpStatusError(HttpError):
    """The server returned a status that is not a success."""

    def __init__(self, status: int, url: str, body_excerpt: str = "") -> None:
        super().__init__(f"HTTP {status} for {url}: {body_excerpt[:200]}")
        self.status = status
        self.url = url


class ResponseTooLargeError(HttpError):
    """The response body exceeded the configured cap."""


class UnsafeRedirectError(HttpError):
    """The server tried to redirect away from the pinned source host."""


class InvalidContentTypeError(HttpError):
    """The response was not declared as JSON."""


class InvalidJsonError(HttpError):
    """The response body was not parsable JSON of the expected shape."""


@dataclass(frozen=True, slots=True)
class RawResponse:
    """A single completed HTTP exchange."""

    status: int
    headers: Mapping[str, str]
    body: bytes
    url: str


class Transport(Protocol):
    """Minimal transport seam so tests never open a socket."""

    def perform(self, url: str, headers: Mapping[str, str]) -> RawResponse:  # pragma: no cover
        ...


@dataclass(slots=True)
class StdlibTransport:
    """HTTPS GET transport built on :mod:`http.client`."""

    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    read_timeout: float = 15.0
    max_response_bytes: int = MAX_RESPONSE_BYTES
    allowed_hosts: frozenset[str] = ALLOWED_SOURCE_HOSTS
    _ssl_context: ssl.SSLContext = field(default_factory=ssl.create_default_context)

    def perform(self, url: str, headers: Mapping[str, str]) -> RawResponse:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            response = self._single_request(current, headers)
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise TransportError(f"Redirect from {current} carried no Location header")
                current = self._validate_redirect(current, location)
                continue
            return response
        raise UnsafeRedirectError(f"Exceeded {MAX_REDIRECTS} redirects starting at {url}")

    def _validate_redirect(self, source: str, location: str) -> str:
        from urllib.parse import urljoin

        target = urljoin(source, location)
        parts = urlsplit(target)
        if parts.scheme != "https" or parts.hostname not in self.allowed_hosts:
            raise UnsafeRedirectError(
                f"Refusing redirect from {source} to {target}: host is not the pinned source"
            )
        return target

    def _single_request(self, url: str, headers: Mapping[str, str]) -> RawResponse:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in self.allowed_hosts:
            raise UnsafeRedirectError(f"Refusing to request {url}: host is not the pinned source")

        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"

        connection = http.client.HTTPSConnection(
            parts.hostname,
            parts.port or 443,
            timeout=self.connect_timeout,
            context=self._ssl_context,
        )
        try:
            connection.connect()
            # Connection is established; give the exchange the longer read budget.
            if connection.sock is not None:
                connection.sock.settimeout(self.read_timeout)
            connection.request("GET", path, headers=dict(headers))
            response = connection.getresponse()
            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise ResponseTooLargeError(
                    f"Response from {url} exceeded {self.max_response_bytes} bytes"
                )
            return RawResponse(
                status=response.status,
                headers={k.lower(): v for k, v in response.getheaders()},
                body=body,
                url=url,
            )
        except TimeoutError as exc:
            raise TransportError(f"Timed out requesting {url}") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise TransportError(f"Network failure requesting {url}: {exc}") from exc
        finally:
            connection.close()


@dataclass(slots=True)
class HttpClient:
    """Retrying JSON client over an injected :class:`Transport`."""

    transport: Transport
    user_agent: str
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS
    sleeper: Callable[[float], None] = time.sleep
    jitter: Callable[[], float] = random.random
    request_count: int = 0
    retry_count: int = 0
    # Detail fetches run on a small thread pool, so the counters used for the
    # invocation summary are guarded rather than incremented in the open.
    _counter_lock: threading.Lock = field(default_factory=threading.Lock)

    def _count_request(self) -> None:
        with self._counter_lock:
            self.request_count += 1

    def _count_retry(self) -> None:
        with self._counter_lock:
            self.retry_count += 1

    def get_json(self, url: str, params: Mapping[str, object] | None = None) -> dict[str, Any]:
        """GET ``url`` and return a parsed JSON object.

        Raises an :class:`HttpError` subclass on any failure. Callers treat that
        as fatal for the affected source read.
        """
        full_url = f"{url}?{urlencode(dict(params))}" if params else url
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "Connection": "close",
        }

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._count_request()
            try:
                response = self.transport.perform(full_url, headers)
            except (TransportError, ResponseTooLargeError) as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
                self._wait(attempt, None)
                continue

            if _is_retryable(response.status):
                last_error = HttpStatusError(
                    response.status, full_url, response.body[:200].decode("utf-8", "replace")
                )
                if attempt == self.max_attempts:
                    break
                self._wait(attempt, response.headers.get("retry-after"))
                continue

            if response.status >= 400:
                # Any other 4xx is a client error; retrying cannot help.
                raise HttpStatusError(
                    response.status, full_url, response.body[:200].decode("utf-8", "replace")
                )

            return _decode_json(response)

        assert last_error is not None
        raise last_error

    def _wait(self, attempt: int, retry_after: str | None) -> None:
        self._count_retry()
        self.sleeper(self._delay_for(attempt, retry_after))

    def _delay_for(self, attempt: int, retry_after: str | None) -> float:
        honoured = _parse_retry_after(retry_after)
        if honoured is not None:
            return min(honoured, MAX_BACKOFF_SECONDS)
        exponential: float = self.backoff_base_seconds * (2 ** (attempt - 1))
        jittered: float = exponential + self.jitter() * self.backoff_base_seconds
        return min(jittered, MAX_BACKOFF_SECONDS)


def _is_retryable(status: int) -> bool:
    return status in RETRYABLE_STATUSES or 500 <= status <= 599


def _parse_retry_after(value: str | None) -> float | None:
    """Interpret a Retry-After header expressed as delay seconds."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        # An HTTP-date form is permitted by the RFC but is not used by this
        # source; fall back to the computed backoff rather than guessing.
        return None
    return max(seconds, 0.0)


def _decode_json(response: RawResponse) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type.lower():
        raise InvalidContentTypeError(
            f"Expected JSON from {response.url}, got content-type {content_type!r}"
        )
    try:
        parsed = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidJsonError(f"Malformed JSON from {response.url}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise InvalidJsonError(
            f"Expected a JSON object from {response.url}, got {type(parsed).__name__}"
        )
    return parsed
