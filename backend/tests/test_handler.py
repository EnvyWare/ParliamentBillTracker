"""End-to-end ingestion runs, without AWS or a network."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import synthetic_source as synthetic

from bill_pipeline.config import Config
from bill_pipeline.handler import RunSummary, SessionRolloverError, run_ingestion
from bill_pipeline.parliament_client import ParliamentClient
from bill_pipeline.snapshot import PublicationGuardError
from bill_pipeline.storage import SnapshotStorage
from conftest import InMemoryS3, SyntheticApiHttp

NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


def ingest(
    *,
    config: Config,
    http: SyntheticApiHttp,
    storage: SnapshotStorage,
    now: datetime = NOW,
    schema: dict[str, Any],
    force: bool = False,
) -> RunSummary:
    client = ParliamentClient(http=http, base_url=config.bills_api_base)  # type: ignore[arg-type]
    return run_ingestion(
        config=config,
        client=client,
        storage=storage,
        now=now,
        invocation_id="test-invocation",
        force_full_reconciliation=force,
        schema=schema,
    )


# ---------------------------------------------------------------------------
# Cold start
# ---------------------------------------------------------------------------


def test_cold_start_publishes_a_complete_snapshot(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    http = SyntheticApiHttp()
    summary = ingest(config=config, http=http, storage=storage, schema=schema)

    assert summary.status == "succeeded"
    assert summary.full_reconciliation is True
    assert summary.published_record_count == len(synthetic.SYNTHETIC_BILLS)
    assert summary.snapshot_changed is True

    published = s3.load("data/current.json")
    assert published["status"] == "healthy"
    assert published["synthetic"] is False
    assert len(published["bills"]) == len(synthetic.SYNTHETIC_BILLS)

    # Every Bill was fetched in full on the first run.
    assert sorted(http.detail_fetches) == sorted(b.bill_id for b in synthetic.SYNTHETIC_BILLS)
    assert sorted(http.history_fetches) == sorted(b.bill_id for b in synthetic.SYNTHETIC_BILLS)


def test_cold_start_writes_the_archive_before_current(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    assert s3.put_calls[-1] == "data/current.json"
    assert any(key.startswith("archive/snapshots/") for key in s3.put_calls)


def test_summary_reports_the_operational_counters(
    config: Config, storage: SnapshotStorage, schema: dict[str, Any]
) -> None:
    summary = ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    log = summary.to_log()
    for key in (
        "invocationId",
        "status",
        "startedAt",
        "durationMs",
        "sourceRequestCount",
        "sourceRecordCount",
        "changedRecordCount",
        "publishedRecordCount",
        "specialOrUnknownCount",
        "retryCount",
        "contentHash",
        "snapshotChanged",
        "fullReconciliation",
    ):
        assert key in log, f"summary log is missing {key}"
    assert summary.source_request_count > 0
    assert summary.special_or_unknown_count == 3


def test_summary_never_contains_bill_or_sponsor_payloads(
    config: Config, storage: SnapshotStorage, schema: dict[str, Any]
) -> None:
    summary = ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    rendered = json.dumps(summary.to_log())
    assert "sponsors" not in rendered
    assert "Wesley Marchant" not in rendered


# ---------------------------------------------------------------------------
# Incremental refresh
# ---------------------------------------------------------------------------


def test_second_run_fetches_nothing_when_nothing_changed(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)

    later = SyntheticApiHttp()
    summary = ingest(
        config=config,
        http=later,
        storage=storage,
        now=NOW + timedelta(minutes=30),
        schema=schema,
    )

    assert summary.full_reconciliation is False
    assert summary.changed_record_count == 0
    assert later.detail_fetches == []
    assert later.history_fetches == []
    assert summary.snapshot_changed is False


def test_only_changed_bills_are_refetched(
    config: Config, storage: SnapshotStorage, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)

    moved = copy.deepcopy(synthetic.bills_list())
    target = next(b for b in moved if b["billId"] == 9002)
    target["lastUpdate"] = "2026-08-29T11:00:00.0000000"

    later = SyntheticApiHttp(bills=moved)
    summary = ingest(
        config=config, http=later, storage=storage, now=NOW + timedelta(minutes=30), schema=schema
    )

    assert summary.changed_record_count == 1
    assert later.detail_fetches == [9002]
    assert later.history_fetches == [9002]


def test_current_is_rewritten_even_when_the_content_is_unchanged(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    """Freshness must stay honest on a quiet day.

    The archive is only written when content changes, but current.json is
    rewritten every run so the site does not report itself stale simply
    because Parliament published nothing.
    """
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    first_generated = s3.load("data/current.json")["generatedAt"]
    archives = [k for k in s3.put_calls if k.startswith("archive/")]

    ingest(
        config=config,
        http=SyntheticApiHttp(),
        storage=storage,
        now=NOW + timedelta(hours=2),
        schema=schema,
    )
    second = s3.load("data/current.json")
    assert second["generatedAt"] != first_generated
    assert [k for k in s3.put_calls if k.startswith("archive/")] == archives


def test_weekly_reconciliation_refetches_everything(
    config: Config, storage: SnapshotStorage, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)

    later = SyntheticApiHttp()
    summary = ingest(
        config=config,
        http=later,
        storage=storage,
        now=NOW + timedelta(days=8),
        schema=schema,
    )
    assert summary.full_reconciliation is True
    assert len(later.detail_fetches) == len(synthetic.SYNTHETIC_BILLS)


def test_forced_reconciliation_refetches_everything(
    config: Config, storage: SnapshotStorage, schema: dict[str, Any]
) -> None:
    """The operator escape hatch used after the stage table changes."""
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    later = SyntheticApiHttp()
    summary = ingest(
        config=config,
        http=later,
        storage=storage,
        now=NOW + timedelta(minutes=30),
        schema=schema,
        force=True,
    )
    assert summary.full_reconciliation is True
    assert len(later.detail_fetches) == len(synthetic.SYNTHETIC_BILLS)


def test_cached_bill_next_sitting_is_recomputed_against_today(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    """A reused record must not keep a sitting date that has since passed."""
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    before = next(b for b in s3.load("data/current.json")["bills"] if b["id"] == 9004)
    assert before["stage"]["nextSittingDate"] == "2026-09-07"

    ingest(
        config=config,
        http=SyntheticApiHttp(),
        storage=storage,
        now=datetime(2026, 9, 8, 6, 0, tzinfo=UTC),
        schema=schema,
    )
    after = next(b for b in s3.load("data/current.json")["bills"] if b["id"] == 9004)
    assert after["stage"]["nextSittingDate"] == "2026-09-08"


def test_incomplete_cached_record_is_refetched(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    stored = s3.load("data/current.json")
    next(b for b in stored["bills"] if b["id"] == 9003)["historyComplete"] = False
    s3.store("data/current.json", stored)

    later = SyntheticApiHttp()
    ingest(
        config=config, http=later, storage=storage, now=NOW + timedelta(minutes=30), schema=schema
    )
    assert 9003 in later.detail_fetches


def test_invalid_previous_snapshot_forces_a_full_reconciliation(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    s3.store("data/current.json", {"schemaVersion": 1, "bills": "not a list"})
    later = SyntheticApiHttp()
    summary = ingest(config=config, http=later, storage=storage, schema=schema)

    assert summary.full_reconciliation is True
    published = s3.load("data/current.json")
    assert any(w["code"] == "previous_snapshot_invalid" for w in published["warnings"])


def test_snapshot_from_a_different_session_is_not_reused_as_cache(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    stored = s3.load("data/current.json")
    stored["source"]["sessionId"] = 39
    s3.store("data/current.json", stored)

    later = SyntheticApiHttp()
    summary = ingest(
        config=config, http=later, storage=storage, now=NOW + timedelta(minutes=30), schema=schema
    )
    assert summary.full_reconciliation is True


# ---------------------------------------------------------------------------
# Guards keep the last known-good snapshot
# ---------------------------------------------------------------------------


def test_empty_session_leaves_the_previous_snapshot_in_place(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    good = s3.load("data/current.json")

    with pytest.raises(PublicationGuardError):
        ingest(
            config=config,
            http=SyntheticApiHttp(bills=[]),
            storage=storage,
            now=NOW + timedelta(minutes=30),
            schema=schema,
        )

    assert s3.load("data/current.json") == good


def test_catastrophic_shrink_leaves_the_previous_snapshot_in_place(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    good = s3.load("data/current.json")

    with pytest.raises(PublicationGuardError, match="fell from"):
        ingest(
            config=config,
            http=SyntheticApiHttp(bills=synthetic.bills_list()[:5]),
            storage=storage,
            now=NOW + timedelta(minutes=30),
            schema=schema,
        )

    assert s3.load("data/current.json") == good


def test_source_failure_leaves_the_previous_snapshot_in_place(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    good = s3.load("data/current.json")

    class Failing(SyntheticApiHttp):
        def get_json(self, url: str, params: Any = None) -> dict[str, Any]:
            if url.endswith("/Stages") and "/Bills/" in url:
                raise RuntimeError("source unavailable")
            return super().get_json(url, params)

    with pytest.raises(RuntimeError, match="source unavailable"):
        ingest(
            config=config,
            http=Failing(),
            storage=storage,
            now=NOW + timedelta(minutes=30),
            schema=schema,
            force=True,
        )

    assert s3.load("data/current.json") == good


def test_session_rollover_fails_the_run_without_republishing(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    good = s3.load("data/current.json")

    with pytest.raises(SessionRolloverError, match="behind the live session"):
        ingest(
            config=config,
            http=SyntheticApiHttp(canary_session_id=41),
            storage=storage,
            now=NOW + timedelta(minutes=30),
            schema=schema,
        )

    assert s3.load("data/current.json") == good


def test_rollover_canary_runs_before_any_expensive_work(
    config: Config, storage: SnapshotStorage, schema: dict[str, Any]
) -> None:
    http = SyntheticApiHttp(canary_session_id=41)
    with pytest.raises(SessionRolloverError):
        ingest(config=config, http=http, storage=storage, schema=schema)
    assert http.detail_fetches == []
    assert http.request_count == 1


# ---------------------------------------------------------------------------
# Unknown stages stay visible
# ---------------------------------------------------------------------------


def test_unknown_stage_is_published_with_a_warning_not_dropped(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    published = s3.load("data/current.json")

    unknown = next(b for b in published["bills"] if b["id"] == 9019)
    assert unknown["pipelineNode"] == "unknown"
    assert "unknown_stage_id" in unknown["warnings"]
    assert unknown["stage"]["detail"] == "A stage introduced after this build"

    codes = {w["code"] for w in published["warnings"]}
    assert "unknown_stage_id" in codes


def test_unmapped_catalogue_ids_raise_a_run_warning(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    class ExtraStage(SyntheticApiHttp):
        def get_json(self, url: str, params: Any = None) -> dict[str, Any]:
            result = super().get_json(url, params)
            if url.endswith("/Stages") and "/Bills/" not in url:
                items = [*result["items"], {"id": 51, "name": "A new stage", "house": "Commons"}]
                return {"totalResults": len(items), "items": items}
            return result

    summary = ingest(config=config, http=ExtraStage(), storage=storage, schema=schema)
    assert summary.unmapped_stage_ids == [51]

    published = s3.load("data/current.json")
    warning = next(w for w in published["warnings"] if w["code"] == "unmapped_stage_in_catalogue")
    assert warning["stageIds"] == [51]
    assert warning["severity"] == "warning"


# ---------------------------------------------------------------------------
# Duplicate delivery
# ---------------------------------------------------------------------------


def test_duplicate_invocation_is_safe(
    config: Config, storage: SnapshotStorage, s3: InMemoryS3, schema: dict[str, Any]
) -> None:
    """Scheduler delivers at least once; a repeat must not duplicate archives."""
    ingest(config=config, http=SyntheticApiHttp(), storage=storage, schema=schema)
    archives_after_first = [k for k in s3.put_calls if k.startswith("archive/")]

    ingest(
        config=config,
        http=SyntheticApiHttp(),
        storage=storage,
        now=NOW + timedelta(seconds=5),
        schema=schema,
    )
    archives_after_second = [k for k in s3.put_calls if k.startswith("archive/")]
    assert archives_after_second == archives_after_first
    assert len(set(archives_after_second)) == 1


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------


def test_lambda_handler_wires_config_and_returns_a_summary(
    monkeypatch: pytest.MonkeyPatch, s3: InMemoryS3
) -> None:
    """The entry point reads configuration and publishes through real S3 calls."""
    from bill_pipeline import handler as handler_module

    for key, value in {
        "DATA_BUCKET": "test-data-bucket",
        "PARLIAMENT_SESSION_ID": "40",
        "PARLIAMENT_SESSION_LABEL": "2026-27",
    }.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr(handler_module, "_s3_client", lambda: s3)
    monkeypatch.setattr(
        handler_module,
        "HttpClient",
        lambda **_: SyntheticApiHttp(),
    )
    monkeypatch.setattr(handler_module, "StdlibTransport", lambda **_: None)

    result = handler_module.lambda_handler({}, None)

    assert result["status"] == "succeeded"
    assert result["publishedRecordCount"] == len(synthetic.SYNTHETIC_BILLS)
    assert "data/current.json" in s3.objects


def test_lambda_handler_rejects_a_source_url_supplied_by_the_event(
    monkeypatch: pytest.MonkeyPatch, s3: InMemoryS3
) -> None:
    """An event may not influence where data is read from.

    Accepting a URL from the Scheduler payload would create a server-side
    request forgery primitive, so the event is only ever read for the
    forceFullReconciliation flag.
    """
    from bill_pipeline import handler as handler_module

    for key, value in {
        "DATA_BUCKET": "test-data-bucket",
        "PARLIAMENT_SESSION_ID": "40",
        "PARLIAMENT_SESSION_LABEL": "2026-27",
    }.items():
        monkeypatch.setenv(key, value)

    captured: dict[str, Any] = {}

    def record_client(**kwargs: Any) -> SyntheticApiHttp:
        captured.update(kwargs)
        return SyntheticApiHttp()

    monkeypatch.setattr(handler_module, "_s3_client", lambda: s3)
    monkeypatch.setattr(handler_module, "HttpClient", record_client)
    monkeypatch.setattr(handler_module, "StdlibTransport", lambda **_: None)

    result = handler_module.lambda_handler(
        {"BILLS_API_BASE": "https://evil.invalid", "billsApiBase": "https://evil.invalid"}, None
    )

    assert result["status"] == "succeeded"
    published = s3.load("data/current.json")
    assert published["source"]["baseUrl"] == "https://bills-api.parliament.uk/api/v1"


def test_lambda_handler_reraises_after_logging_a_guard_refusal(
    monkeypatch: pytest.MonkeyPatch, s3: InMemoryS3
) -> None:
    from bill_pipeline import handler as handler_module

    for key, value in {
        "DATA_BUCKET": "test-data-bucket",
        "PARLIAMENT_SESSION_ID": "40",
        "PARLIAMENT_SESSION_LABEL": "2026-27",
    }.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr(handler_module, "_s3_client", lambda: s3)
    monkeypatch.setattr(handler_module, "HttpClient", lambda **_: SyntheticApiHttp(bills=[]))
    monkeypatch.setattr(handler_module, "StdlibTransport", lambda **_: None)

    with pytest.raises(PublicationGuardError):
        handler_module.lambda_handler({}, None)
    assert "data/current.json" not in s3.objects


def test_lambda_handler_uses_the_aws_request_id_as_the_invocation_id(
    monkeypatch: pytest.MonkeyPatch, s3: InMemoryS3
) -> None:
    from bill_pipeline import handler as handler_module

    for key, value in {
        "DATA_BUCKET": "test-data-bucket",
        "PARLIAMENT_SESSION_ID": "40",
        "PARLIAMENT_SESSION_LABEL": "2026-27",
    }.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr(handler_module, "_s3_client", lambda: s3)
    monkeypatch.setattr(handler_module, "HttpClient", lambda **_: SyntheticApiHttp())
    monkeypatch.setattr(handler_module, "StdlibTransport", lambda **_: None)

    class Context:
        aws_request_id = "abc-123"

    assert handler_module.lambda_handler({}, Context())["invocationId"] == "abc-123"
