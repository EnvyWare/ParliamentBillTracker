"""Lambda entry point and the ingestion run it orchestrates.

The orchestration lives in :func:`run_ingestion`, which takes its
collaborators as arguments so the whole flow can be tested without AWS, a
network or the environment. :func:`lambda_handler` only wires the real ones.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import Config, load_config
from .http_client import HttpClient, StdlibTransport
from .models import BillType, SnapshotWarning, WarningCode
from .normalise import normalise_bill, today_in_london
from .parliament_client import ParliamentClient
from .snapshot import (
    PublicationGuardError,
    archive_key,
    build_snapshot,
    detect_session_rollover,
    evaluate_publication_guards,
    find_schema_path,
    is_special_or_unclassified,
    refresh_derived_fields,
    utc_timestamp,
)
from .storage import SnapshotStorage
from .validation import SchemaValidationError, load_schema, validate

logger = logging.getLogger("bill_pipeline")


class SessionRolloverError(RuntimeError):
    """The configured session is behind the live Parliamentary session."""


@dataclass(slots=True)
class RunSummary:
    """One structured log line per invocation."""

    invocation_id: str
    status: str = "started"
    started_at: str = ""
    duration_ms: int = 0
    source_request_count: int = 0
    source_record_count: int = 0
    changed_record_count: int = 0
    published_record_count: int = 0
    special_or_unknown_count: int = 0
    retry_count: int = 0
    content_hash: str | None = None
    snapshot_changed: bool = False
    full_reconciliation: bool = False
    unmapped_stage_ids: list[int] = field(default_factory=list)
    message: str | None = None

    def to_log(self) -> dict[str, Any]:
        """Summary fields for the per-invocation log record."""
        return {_camel(key): value for key, value in asdict(self).items() if value is not None}


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _log(level: int, event: str, **fields: Any) -> None:
    """Emit one structured JSON log record.

    Never log the full snapshot or sponsor payloads: the logs are for
    operating the pipeline, not for storing a second copy of the data.
    """
    logger.log(level, json.dumps({"event": event, **fields}, default=str))


def _needs_fetch(cached: dict[str, Any] | None, source_bill: dict[str, Any]) -> bool:
    """Whether this Bill's detail and history must be retrieved again."""
    if cached is None:
        return True
    if not (cached.get("detailsComplete") and cached.get("historyComplete")):
        return True
    # Exact string comparison. lastUpdate carries no guaranteed offset, so it is
    # compared verbatim rather than parsed into an instant.
    return cached.get("sourceLastUpdate") != source_bill.get("lastUpdate")


def _due_for_full_reconciliation(
    previous: dict[str, Any] | None, now: datetime, after_days: int
) -> bool:
    if previous is None:
        return True
    raw = previous.get("lastFullReconciliationAt")
    if not isinstance(raw, str):
        return True
    try:
        last = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return True
    return now - last >= timedelta(days=after_days)


def run_ingestion(
    *,
    config: Config,
    client: ParliamentClient,
    storage: SnapshotStorage,
    now: datetime,
    invocation_id: str,
    force_full_reconciliation: bool = False,
    schema: dict[str, Any] | None = None,
) -> RunSummary:
    """Retrieve, normalise, guard and publish one snapshot."""
    started = now
    summary = RunSummary(invocation_id=invocation_id, started_at=utc_timestamp(now))
    today = today_in_london(now)
    schema = schema if schema is not None else load_schema(find_schema_path())
    warnings: list[SnapshotWarning] = []

    # 1. Previous snapshot, validated before it is trusted as a cache.
    previous = storage.read_current()
    if previous is not None:
        try:
            validate(previous, schema)
        except SchemaValidationError as exc:
            _log(
                logging.WARNING,
                "previous_snapshot_invalid",
                detail=str(exc)[:500],
            )
            warnings.append(
                SnapshotWarning(
                    code="previous_snapshot_invalid",
                    message=(
                        "The previously published snapshot failed validation and was not "
                        "reused as a cache. This run performed a full reconciliation."
                    ),
                    severity="warning",
                )
            )
            previous = None

    # 2. Session rollover canary, before any expensive work.
    newer_session = detect_session_rollover(
        client.latest_updated_bill(), config.parliament_session_id
    )
    if newer_session is not None:
        summary.status = "failed"
        summary.message = (
            f"Configured session {config.parliament_session_id} is behind the live "
            f"session {newer_session}"
        )
        _log(
            logging.CRITICAL,
            "session_rollover_detected",
            configuredSessionId=config.parliament_session_id,
            observedSessionId=newer_session,
            action=(
                "Update the parliament_session_id and parliament_session_label Terraform "
                "variables and re-apply. See docs/operations.md."
            ),
        )
        raise SessionRolloverError(summary.message)

    # 3. Reference data and the complete session list.
    bill_types = _index_bill_types(client.list_bill_types())
    catalogue = client.list_stages()
    unmapped = _unmapped_catalogue_ids(catalogue)
    if unmapped:
        summary.unmapped_stage_ids = list(unmapped)
        _log(logging.WARNING, "unmapped_stage_ids", stageIds=list(unmapped))
        warnings.append(
            SnapshotWarning(
                code=WarningCode.UNMAPPED_STAGE_IN_CATALOGUE,
                message=(
                    "The Bills API publishes stage ids this build does not classify. "
                    "Bills at those stages are shown as unclassified until the stage "
                    "table is updated."
                ),
                severity="warning",
                stage_ids=tuple(unmapped),
            )
        )

    source_bills = client.list_session_bills(config.parliament_session_id)
    summary.source_record_count = len(source_bills)

    # 4. Decide what actually needs re-fetching.
    previous_index = _previous_index(previous, config.parliament_session_id)
    full_reconciliation = (
        force_full_reconciliation
        or not previous_index
        or _due_for_full_reconciliation(previous, now, config.full_reconcile_after_days)
    )
    summary.full_reconciliation = full_reconciliation

    changed = [
        bill
        for bill in source_bills
        if full_reconciliation or _needs_fetch(previous_index.get(bill.get("billId")), bill)
    ]
    summary.changed_record_count = len(changed)

    fetched = _fetch_changed(client, changed, config.max_concurrent_requests)

    # 5. Normalise changed Bills; reuse validated cache for the rest.
    bills: list[dict[str, Any]] = []
    for source_bill in source_bills:
        bill_id = source_bill.get("billId")
        if bill_id in fetched:
            detail, stages = fetched[bill_id]
            bills.append(
                normalise_bill(
                    summary_raw=source_bill,
                    detail_raw=detail,
                    stages_raw=stages,
                    bill_types=bill_types,
                    session_id=config.parliament_session_id,
                    today=today,
                ).to_dict()
            )
        else:
            cached = previous_index[bill_id]
            bills.append(refresh_derived_fields(json.loads(json.dumps(cached)), today))

    unknown_stage_bills = tuple(
        sorted(
            bill["id"]
            for bill in bills
            if WarningCode.UNKNOWN_STAGE_ID.value in bill.get("warnings", [])
        )
    )
    if unknown_stage_bills:
        warnings.append(
            SnapshotWarning(
                code=WarningCode.UNKNOWN_STAGE_ID,
                message=(
                    "Some Bills are at a stage this build does not recognise and are "
                    "shown as unclassified rather than being placed by guesswork."
                ),
                severity="info",
                bill_ids=unknown_stage_bills,
            )
        )

    # 6. Assemble, guard, publish.
    last_full = now if full_reconciliation else _previous_reconciliation_time(previous)
    document = build_snapshot(
        bills=bills,
        config=config,
        generated_at=now,
        last_full_reconciliation_at=last_full,
        warnings=warnings,
    )

    evaluate_publication_guards(
        document=document,
        previous=previous,
        session_id=config.parliament_session_id,
        schema=schema,
    )

    summary.content_hash = document["dataHash"]
    summary.published_record_count = len(document["bills"])
    summary.special_or_unknown_count = sum(
        1 for b in document["bills"] if is_special_or_unclassified(b)
    )
    summary.snapshot_changed = previous is None or previous.get("dataHash") != document["dataHash"]

    if summary.snapshot_changed:
        storage.write_archive(archive_key(config.snapshot_prefix, document["dataHash"]), document)

    # current.json is written last and written whole. Object replacement is
    # atomic for readers, and rewriting it every run keeps the freshness
    # indicator honest even when Parliament published nothing.
    storage.write_current(document)

    summary.status = "succeeded"
    summary.source_request_count = client.http.request_count
    summary.retry_count = client.http.retry_count
    summary.duration_ms = int((datetime.now(tz=UTC) - started).total_seconds() * 1000)
    return summary


def _previous_reconciliation_time(previous: dict[str, Any] | None) -> datetime | None:
    if previous is None:
        return None
    raw = previous.get("lastFullReconciliationAt")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _previous_index(previous: dict[str, Any] | None, session_id: int) -> dict[Any, dict[str, Any]]:
    """Index the previous snapshot's Bills, but only for the same session."""
    if previous is None:
        return {}
    if previous.get("source", {}).get("sessionId") != session_id:
        return {}
    bills = previous.get("bills")
    if not isinstance(bills, list):
        return {}
    return {bill["id"]: bill for bill in bills if isinstance(bill, dict) and "id" in bill}


def _index_bill_types(raw_types: Sequence[dict[str, Any]]) -> dict[int, BillType]:
    types: dict[int, BillType] = {}
    for entry in raw_types:
        type_id = entry.get("id")
        name = entry.get("name")
        if isinstance(type_id, int) and isinstance(name, str):
            category = entry.get("category")
            types[type_id] = BillType(
                id=type_id,
                name=name,
                category=category if isinstance(category, str) else None,
            )
    return types


def _unmapped_catalogue_ids(catalogue: Sequence[dict[str, Any]]) -> tuple[int, ...]:
    from .stage_map import unmapped_ids

    published = {entry["id"] for entry in catalogue if isinstance(entry.get("id"), int)}
    return unmapped_ids(published)


def _fetch_changed(
    client: ParliamentClient,
    changed: Sequence[dict[str, Any]],
    max_workers: int,
) -> dict[Any, tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Fetch detail and stage history for changed Bills, bounded concurrency.

    Parliament is a public service, so fan-out is capped. Any failure here
    propagates and fails the invocation, leaving the published snapshot alone.
    """
    if not changed:
        return {}

    def fetch(source_bill: dict[str, Any]) -> tuple[Any, dict[str, Any], list[dict[str, Any]]]:
        bill_id = source_bill["billId"]
        return bill_id, client.get_bill(bill_id), client.get_bill_stages(bill_id)

    results: dict[Any, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        for bill_id, detail, stages in pool.map(fetch, changed):
            results[bill_id] = (detail, stages)
    return results


def lambda_handler(event: dict[str, Any] | None, context: Any = None) -> dict[str, Any]:
    """AWS Lambda entry point."""
    config = load_config()
    logging.getLogger().setLevel(config.log_level)
    logger.setLevel(config.log_level)

    invocation_id = getattr(context, "aws_request_id", None) or str(uuid.uuid4())

    # A boolean operator flag is safe to accept; a source URL never is, which is
    # why the API host stays configuration-controlled.
    force_full = bool((event or {}).get("forceFullReconciliation"))

    http = HttpClient(
        transport=StdlibTransport(read_timeout=config.http_timeout_seconds),
        user_agent=config.user_agent,
    )
    client = ParliamentClient(http=http, base_url=config.bills_api_base)
    storage = SnapshotStorage(
        client=_s3_client(),
        bucket=config.data_bucket,
        current_key=config.current_key,
        snapshot_prefix=config.snapshot_prefix,
    )

    try:
        summary = run_ingestion(
            config=config,
            client=client,
            storage=storage,
            now=datetime.now(tz=UTC),
            invocation_id=invocation_id,
            force_full_reconciliation=force_full,
        )
    except PublicationGuardError as exc:
        _log(
            logging.ERROR,
            "publication_guard_refused",
            invocationId=invocation_id,
            detail=str(exc)[:500],
            outcome="The previously published snapshot was left in place.",
        )
        raise
    except Exception as exc:
        _log(
            logging.ERROR,
            "ingestion_failed",
            invocationId=invocation_id,
            errorType=type(exc).__name__,
            detail=str(exc)[:500],
            outcome="The previously published snapshot was left in place.",
        )
        raise

    _log(logging.INFO, "ingestion_summary", **summary.to_log())
    return summary.to_log()


def _s3_client() -> Any:  # pragma: no cover - exercised only in AWS
    import boto3

    return boto3.client("s3", region_name=os.environ.get("AWS_REGION"))
