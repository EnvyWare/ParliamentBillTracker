"""Deployment configuration, read once from the environment.

Every value that controls where data is read from or written to is
configuration. Nothing here may be influenced by a Scheduler event payload:
accepting a source URL from an event would turn the ingestion function into a
server-side request forgery primitive.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

DEFAULT_BILLS_API_BASE: Final = "https://bills-api.parliament.uk/api/v1"

#: The only host the ingestion function will exchange data with.
ALLOWED_SOURCE_HOSTS: Final[frozenset[str]] = frozenset({"bills-api.parliament.uk"})

OPEN_PARLIAMENT_LICENCE_URL: Final = (
    "https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/"
)
OPEN_PARLIAMENT_ATTRIBUTION: Final = (
    "Contains Parliamentary information licensed under the Open Parliament Licence v3.0."
)
SOURCE_NAME: Final = "UK Parliament Bills API"

#: Public Bill page on the Parliament website, for the outbound details link.
BILL_PAGE_TEMPLATE: Final = "https://bills.parliament.uk/bills/{bill_id}"

SCHEMA_VERSION: Final = 1


class ConfigError(RuntimeError):
    """Raised when required deployment configuration is missing or unusable."""


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved deployment configuration for one invocation."""

    data_bucket: str
    current_key: str
    snapshot_prefix: str
    bills_api_base: str
    parliament_session_id: int
    parliament_session_label: str
    refresh_interval_minutes: int
    http_timeout_seconds: float
    max_concurrent_requests: int
    full_reconcile_after_days: int
    schema_version: int
    log_level: str
    repository_url: str

    @property
    def user_agent(self) -> str:
        """Descriptive User-Agent so Parliament can identify and contact this client."""
        return f"uk-bill-pipeline/{self.schema_version} (+{self.repository_url})"


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Required environment variable {name} is missing or empty")
    return value


def _optional(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _positive_int(name: str, default: str) -> int:
    raw = _optional(name, default)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"Environment variable {name} must be positive, got {value}")
    return value


def _positive_float(name: str, default: str) -> float:
    raw = _optional(name, default)
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"Environment variable {name} must be positive, got {value}")
    return value


def load_config(environ: dict[str, str] | None = None) -> Config:
    """Build a :class:`Config` from the process environment.

    ``environ`` exists so tests can supply an explicit mapping rather than
    mutating global state.
    """
    if environ is not None:
        previous = dict(os.environ)
        os.environ.clear()
        os.environ.update(environ)
        try:
            return load_config()
        finally:
            os.environ.clear()
            os.environ.update(previous)

    session_raw = _require("PARLIAMENT_SESSION_ID")
    try:
        session_id = int(session_raw)
    except ValueError as exc:
        raise ConfigError(f"PARLIAMENT_SESSION_ID must be an integer, got {session_raw!r}") from exc

    base = _optional("BILLS_API_BASE", DEFAULT_BILLS_API_BASE).rstrip("/")
    _assert_allowed_base(base)

    return Config(
        data_bucket=_require("DATA_BUCKET"),
        current_key=_optional("CURRENT_KEY", "data/current.json"),
        snapshot_prefix=_optional("SNAPSHOT_PREFIX", "archive/snapshots/"),
        bills_api_base=base,
        parliament_session_id=session_id,
        parliament_session_label=_require("PARLIAMENT_SESSION_LABEL"),
        refresh_interval_minutes=_positive_int("REFRESH_INTERVAL_MINUTES", "30"),
        http_timeout_seconds=_positive_float("HTTP_TIMEOUT_SECONDS", "15"),
        max_concurrent_requests=_positive_int("MAX_CONCURRENT_REQUESTS", "5"),
        full_reconcile_after_days=_positive_int("FULL_RECONCILE_AFTER_DAYS", "7"),
        schema_version=_positive_int("SCHEMA_VERSION", str(SCHEMA_VERSION)),
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
        repository_url=_optional("REPOSITORY_URL", "https://github.com/EnvyWare/ParliamentBillTracker"),
    )


def _assert_allowed_base(base: str) -> None:
    from urllib.parse import urlsplit

    parts = urlsplit(base)
    if parts.scheme != "https":
        raise ConfigError(f"BILLS_API_BASE must use https, got {base!r}")
    if parts.hostname not in ALLOWED_SOURCE_HOSTS:
        raise ConfigError(
            f"BILLS_API_BASE host {parts.hostname!r} is not in the allowed source host list"
        )
