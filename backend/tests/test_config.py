"""Environment parsing, defaults and the source-host guard."""

from __future__ import annotations

import pytest

from bill_pipeline.config import DEFAULT_BILLS_API_BASE, ConfigError, load_config

BASE_ENV = {
    "DATA_BUCKET": "example-data-bucket",
    "PARLIAMENT_SESSION_ID": "40",
    "PARLIAMENT_SESSION_LABEL": "2026-27",
}


def test_defaults_match_the_documented_deployment() -> None:
    config = load_config(dict(BASE_ENV))
    assert config.current_key == "data/current.json"
    assert config.snapshot_prefix == "archive/snapshots/"
    assert config.bills_api_base == DEFAULT_BILLS_API_BASE
    assert config.refresh_interval_minutes == 30
    assert config.http_timeout_seconds == 15.0
    assert config.max_concurrent_requests == 5
    assert config.full_reconcile_after_days == 7
    assert config.schema_version == 1
    assert config.log_level == "INFO"


def test_user_agent_identifies_the_project_and_its_repository() -> None:
    config = load_config({**BASE_ENV, "REPOSITORY_URL": "https://example.invalid/repo"})
    assert config.user_agent == "uk-bill-pipeline/1 (+https://example.invalid/repo)"


@pytest.mark.parametrize(
    "missing", ["DATA_BUCKET", "PARLIAMENT_SESSION_ID", "PARLIAMENT_SESSION_LABEL"]
)
def test_required_variables_are_required(missing: str) -> None:
    env = {k: v for k, v in BASE_ENV.items() if k != missing}
    with pytest.raises(ConfigError, match=missing):
        load_config(env)


def test_blank_required_variable_is_rejected() -> None:
    with pytest.raises(ConfigError):
        load_config({**BASE_ENV, "DATA_BUCKET": "   "})


def test_session_id_must_be_an_integer() -> None:
    with pytest.raises(ConfigError, match="PARLIAMENT_SESSION_ID"):
        load_config({**BASE_ENV, "PARLIAMENT_SESSION_ID": "2026-27"})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("REFRESH_INTERVAL_MINUTES", "0"),
        ("REFRESH_INTERVAL_MINUTES", "-5"),
        ("REFRESH_INTERVAL_MINUTES", "half an hour"),
        ("MAX_CONCURRENT_REQUESTS", "0"),
        ("FULL_RECONCILE_AFTER_DAYS", "nope"),
        ("HTTP_TIMEOUT_SECONDS", "0"),
        ("HTTP_TIMEOUT_SECONDS", "soon"),
    ],
)
def test_numeric_variables_are_validated(name: str, value: str) -> None:
    with pytest.raises(ConfigError, match=name):
        load_config({**BASE_ENV, name: value})


# ---------------------------------------------------------------------------
# Source host pinning
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base",
    [
        "https://evil.invalid/api/v1",
        "https://bills-api.parliament.uk.evil.invalid/api/v1",
        "http://bills-api.parliament.uk/api/v1",
        "https://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
    ],
)
def test_source_base_url_is_pinned_to_the_parliament_host(base: str) -> None:
    """Configuration cannot redirect ingestion at another host.

    The API host is configuration-controlled rather than event-controlled, and
    even configuration cannot point it somewhere else.
    """
    with pytest.raises(ConfigError):
        load_config({**BASE_ENV, "BILLS_API_BASE": base})


def test_trailing_slash_is_normalised() -> None:
    config = load_config({**BASE_ENV, "BILLS_API_BASE": f"{DEFAULT_BILLS_API_BASE}/"})
    assert config.bills_api_base == DEFAULT_BILLS_API_BASE


def test_load_config_restores_the_process_environment() -> None:
    """The explicit-mapping form must not leak into os.environ."""
    import os

    before = dict(os.environ)
    load_config(dict(BASE_ENV))
    assert dict(os.environ) == before
