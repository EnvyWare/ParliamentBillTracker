"""Snapshot assembly, deterministic hashing and publication guards.

The guards are the safety property that matters most in this project: a run
that is incomplete, empty or implausible must leave the last known-good
``current.json`` exactly where it is. An unrecognised stage is explicitly not
a guard failure — it is normal input that gets published with a warning.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

from .config import (
    OPEN_PARLIAMENT_ATTRIBUTION,
    OPEN_PARLIAMENT_LICENCE_URL,
    SOURCE_NAME,
    Config,
)
from .models import (
    BillStatus,
    House,
    PipelineNode,
    Snapshot,
    SnapshotCounts,
    SnapshotSource,
    SnapshotWarning,
)
from .validation import SchemaValidationError, load_schema, validate

#: Publication is refused if the Bill count falls below this fraction of the
#: previous snapshot while the session id is unchanged.
MIN_RETAINED_FRACTION: Final = 0.7

SCHEMA_FILENAME: Final = "snapshot.schema.json"


class PublicationGuardError(RuntimeError):
    """A guard refused to let this result replace the published snapshot."""


def find_schema_path() -> Path:
    """Locate the snapshot schema.

    The build copies the schema next to this module so the Lambda package is
    self-contained; a checkout resolves it from the repository ``schema``
    directory instead.
    """
    packaged = Path(__file__).with_name(SCHEMA_FILENAME)
    if packaged.is_file():
        return packaged
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "schema" / SCHEMA_FILENAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not locate {SCHEMA_FILENAME}")


def utc_timestamp(moment: datetime) -> str:
    """Format a Lambda-generated instant.

    Only timestamps this code generates are guaranteed UTC, so only these get
    a trailing ``Z``. Source timestamps are never relabelled this way.
    """
    if moment.tzinfo is None:
        raise ValueError("Generated timestamps must be timezone-aware")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


#: Nodes that cannot be placed on either canonical route.
_UNPLACEABLE_NODES: Final[frozenset[str]] = frozenset(
    {PipelineNode.SPECIAL_PROCEDURE.value, PipelineNode.UNKNOWN.value}
)


def is_special_or_unclassified(bill: dict[str, Any]) -> bool:
    """Whether a Bill renders in the special/unclassified section.

    A Bill lands there when it cannot be placed on either canonical route:
    its node is not a route node, or its originating House is unassigned so
    there is no route to place it on.

    Withdrawn and defeated Bills are excluded because they have their own
    concluded section. Enacted Bills are not excluded: Royal Assent is the
    final step of both routes, so an Act with a known originating House is
    rendered there rather than in a separate list.

    The frontend selector applies exactly this rule, so the published counts
    and the rendered sections always agree.
    """
    if bill.get("status") in (BillStatus.WITHDRAWN.value, BillStatus.FAILED.value):
        return False
    return (
        bill.get("pipelineNode") in _UNPLACEABLE_NODES
        or bill.get("originatingHouse") == House.UNASSIGNED.value
    )


def count_bills(bills: Sequence[dict[str, Any]]) -> SnapshotCounts:
    def with_status(status: BillStatus) -> int:
        return sum(1 for b in bills if b.get("status") == status.value)

    return SnapshotCounts(
        total=len(bills),
        active=with_status(BillStatus.ACTIVE),
        enacted=with_status(BillStatus.ENACTED),
        withdrawn=with_status(BillStatus.WITHDRAWN),
        failed=with_status(BillStatus.FAILED),
        unknown=with_status(BillStatus.UNKNOWN),
        special_or_unclassified=sum(1 for b in bills if is_special_or_unclassified(b)),
    )


def sort_bills(bills: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Case-folded title, then numeric Bill id as a deterministic tie-break."""
    return tuple(sorted(bills, key=lambda b: (str(b.get("title", "")).casefold(), b.get("id", 0))))


def hashable_projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strip everything that changes without the source data changing.

    Removed: the two generated timestamps, the hash field itself, and each
    stage's ``nextSittingDate``. That last one is derived from the current
    calendar date rather than from the source, so leaving it in would produce
    a fresh archive object every day even when Parliament published nothing.
    The sittings it is derived from stay in the hash.
    """
    projection = copy.deepcopy(snapshot)
    for volatile in ("generatedAt", "lastFullReconciliationAt", "dataHash"):
        projection.pop(volatile, None)
    for bill in projection.get("bills", []):
        stage = bill.get("stage")
        if isinstance(stage, dict):
            stage.pop("nextSittingDate", None)
    return projection


def compute_data_hash(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(
        hashable_projection(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def archive_key(prefix: str, data_hash: str) -> str:
    """Content-addressed archive key.

    At-least-once delivery means the same content can be produced twice; a
    content-addressed key makes the second write a harmless overwrite of an
    identical object instead of a duplicate archive.
    """
    return f"{prefix}{data_hash.removeprefix('sha256:')}.json"


def build_snapshot(
    *,
    bills: Sequence[dict[str, Any]],
    config: Config,
    generated_at: datetime,
    last_full_reconciliation_at: datetime | None,
    warnings: Sequence[SnapshotWarning] = (),
    synthetic: bool = False,
) -> dict[str, Any]:
    """Assemble the complete snapshot document, including its data hash."""
    ordered = sort_bills(bills)
    snapshot = Snapshot(
        schema_version=config.schema_version,
        generated_at=utc_timestamp(generated_at),
        last_full_reconciliation_at=(
            utc_timestamp(last_full_reconciliation_at) if last_full_reconciliation_at else None
        ),
        status="synthetic" if synthetic else "healthy",
        synthetic=synthetic,
        source=SnapshotSource(
            name=SOURCE_NAME,
            base_url=config.bills_api_base,
            session_id=config.parliament_session_id,
            session_label=config.parliament_session_label,
            attribution=OPEN_PARLIAMENT_ATTRIBUTION,
            licence_url=OPEN_PARLIAMENT_LICENCE_URL,
        ),
        counts=count_bills(ordered),
        data_hash="sha256:" + "0" * 64,
        bills=ordered,
        warnings=tuple(warnings),
    )
    document = snapshot.to_dict()
    document["dataHash"] = compute_data_hash(document)
    return document


def validate_snapshot(document: dict[str, Any], schema: dict[str, Any] | None = None) -> None:
    """Validate against the published contract, raising on any failure."""
    validate(document, schema if schema is not None else load_schema(find_schema_path()))


def evaluate_publication_guards(
    *,
    document: dict[str, Any],
    previous: dict[str, Any] | None,
    session_id: int,
    schema: dict[str, Any] | None = None,
) -> None:
    """Refuse to publish an empty, shrunken or invalid result.

    Raises :class:`PublicationGuardError`. The caller leaves the existing
    ``current.json`` untouched and fails the invocation so the alarm fires.
    """
    bills = document.get("bills")
    if not isinstance(bills, list):
        raise PublicationGuardError("Snapshot has no bills array")

    if not bills:
        raise PublicationGuardError(
            f"Refusing to publish an empty result for configured live session {session_id}"
        )

    if previous is not None:
        previous_session = previous.get("source", {}).get("sessionId")
        previous_bills = previous.get("bills")
        if (
            previous_session == session_id
            and isinstance(previous_bills, list)
            and previous_bills
            and len(bills) < len(previous_bills) * MIN_RETAINED_FRACTION
        ):
            raise PublicationGuardError(
                f"Refusing to publish: Bill count fell from {len(previous_bills)} to "
                f"{len(bills)} for unchanged session {session_id}"
            )

    incomplete = [
        bill["id"]
        for bill in bills
        if isinstance(bill, dict)
        and not (bill.get("detailsComplete") and bill.get("historyComplete"))
    ]
    if incomplete:
        raise PublicationGuardError(
            f"Refusing to publish: {len(incomplete)} Bill(s) could not be fully "
            f"normalised, for example {incomplete[:5]}"
        )

    try:
        validate_snapshot(document, schema)
    except SchemaValidationError as exc:
        raise PublicationGuardError(str(exc)) from exc


def detect_session_rollover(
    latest_bill: dict[str, Any] | None, configured_session_id: int
) -> int | None:
    """Return the newer session id if the canary suggests a rollover.

    The Bills API has no dependable current-session lookup, so the most
    recently updated Bill across all sessions acts as the canary. A newer
    session id means the deployment configuration is stale and the run must
    stop rather than publish a snapshot for a session that has ended.
    """
    if not latest_bill:
        return None
    introduced = latest_bill.get("introducedSessionId")
    if isinstance(introduced, int) and introduced > configured_session_id:
        return introduced
    return None


def is_stale(document: dict[str, Any], now: datetime, max_age_minutes: int) -> bool:
    """Whether a previously published snapshot is older than the threshold."""
    raw = document.get("generatedAt")
    if not isinstance(raw, str):
        return True
    try:
        generated = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return True
    return (now - generated).total_seconds() > max_age_minutes * 60


def refresh_derived_fields(bill: dict[str, Any], today: date) -> dict[str, Any]:
    """Recompute clock-dependent fields on a Bill reused from the cache.

    ``nextSittingDate`` is defined relative to the ingestion date, so a Bill
    carried forward unchanged still needs it recalculated. Everything else in
    a cached record is source-derived and is reused verbatim.
    """
    stage = bill.get("stage")
    if not isinstance(stage, dict):
        return bill
    sittings = stage.get("sittings")
    upcoming: list[str] = []
    if isinstance(sittings, list):
        for sitting in sittings:
            value = sitting.get("date") if isinstance(sitting, dict) else None
            if isinstance(value, str):
                try:
                    if date.fromisoformat(value) >= today:
                        upcoming.append(value)
                except ValueError:
                    continue
    stage["nextSittingDate"] = min(upcoming) if upcoming else None
    return bill
