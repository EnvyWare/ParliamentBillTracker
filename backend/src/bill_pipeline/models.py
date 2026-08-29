"""Normalised domain model and its JSON projection.

These types are the Python half of the published contract in
``schema/snapshot.schema.json``. Every ``to_dict`` emits exactly the fields
that schema requires, so a change here that is not mirrored there fails the
contract tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class House(StrEnum):
    """Which House a stage or member belongs to."""

    COMMONS = "commons"
    LORDS = "lords"
    UNASSIGNED = "unassigned"


class BillStatus(StrEnum):
    ACTIVE = "active"
    ENACTED = "enacted"
    WITHDRAWN = "withdrawn"
    FAILED = "failed"
    UNKNOWN = "unknown"


class PipelineNode(StrEnum):
    COMMONS_FIRST_READING = "commons_first_reading"
    COMMONS_SECOND_READING = "commons_second_reading"
    COMMONS_COMMITTEE = "commons_committee"
    COMMONS_REPORT = "commons_report"
    COMMONS_THIRD_READING = "commons_third_reading"
    LORDS_FIRST_READING = "lords_first_reading"
    LORDS_SECOND_READING = "lords_second_reading"
    LORDS_COMMITTEE = "lords_committee"
    LORDS_REPORT = "lords_report"
    LORDS_THIRD_READING = "lords_third_reading"
    PING_PONG = "ping_pong"
    ROYAL_ASSENT = "royal_assent"
    SPECIAL_PROCEDURE = "special_procedure"
    WITHDRAWN = "withdrawn"
    FAILED = "failed"
    UNKNOWN = "unknown"


class MappingMode(StrEnum):
    DIRECT = "direct"
    PREVIOUS_CANONICAL = "previous_canonical"
    TERMINAL = "terminal"
    SPECIAL = "special"
    UNKNOWN = "unknown"


#: Nodes that represent a Bill still moving through the process.
CANONICAL_NODES: frozenset[PipelineNode] = frozenset(
    {
        PipelineNode.COMMONS_FIRST_READING,
        PipelineNode.COMMONS_SECOND_READING,
        PipelineNode.COMMONS_COMMITTEE,
        PipelineNode.COMMONS_REPORT,
        PipelineNode.COMMONS_THIRD_READING,
        PipelineNode.LORDS_FIRST_READING,
        PipelineNode.LORDS_SECOND_READING,
        PipelineNode.LORDS_COMMITTEE,
        PipelineNode.LORDS_REPORT,
        PipelineNode.LORDS_THIRD_READING,
        PipelineNode.PING_PONG,
        PipelineNode.ROYAL_ASSENT,
    }
)


class WarningCode(StrEnum):
    """Machine-readable warning codes attached to a Bill or to the run."""

    TERMINAL_FLAGS_CONFLICT = "terminal_flags_conflict"
    UNKNOWN_STAGE_ID = "unknown_stage_id"
    NO_CURRENT_STAGE = "no_current_stage"
    NO_CANONICAL_PREDECESSOR = "no_canonical_predecessor"
    UNASSIGNED_ORIGINATING_HOUSE = "unassigned_originating_house"
    INCOMPLETE_HISTORY = "incomplete_history"
    INCOMPLETE_DETAILS = "incomplete_details"
    NON_STANDARD_ROUTE = "non_standard_route"
    UNMAPPED_STAGE_IN_CATALOGUE = "unmapped_stage_in_catalogue"
    SESSION_ROLLOVER_SUSPECTED = "session_rollover_suspected"


@dataclass(frozen=True, slots=True)
class Sitting:
    id: int | None
    date: str | None
    source_date_time: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "date": self.date,
            "sourceDateTime": self.source_date_time,
        }


@dataclass(frozen=True, slots=True)
class StageOccurrence:
    """One occurrence of a stage for one Bill."""

    bill_stage_id: int | None
    stage_id: int | None
    session_id: int | None
    label: str
    abbreviation: str | None
    house: House
    sort_order: int | None
    sittings: tuple[Sitting, ...] = ()
    next_sitting_date: str | None = None
    detail: str | None = None
    mapped_node: PipelineNode | None = None
    mapping_mode: MappingMode = MappingMode.UNKNOWN

    def to_current_dict(self) -> dict[str, Any]:
        """Projection used for ``bill.stage``."""
        return {
            "billStageId": self.bill_stage_id,
            "stageId": self.stage_id,
            "sessionId": self.session_id,
            "label": self.label,
            "abbreviation": self.abbreviation,
            "house": self.house.value,
            "sortOrder": self.sort_order,
            "sittings": [s.to_dict() for s in self.sittings],
            "nextSittingDate": self.next_sitting_date,
            "detail": self.detail,
        }

    def to_history_dict(self) -> dict[str, Any]:
        """Projection used for entries of ``bill.history``."""
        return {
            "billStageId": self.bill_stage_id,
            "stageId": self.stage_id,
            "sessionId": self.session_id,
            "label": self.label,
            "abbreviation": self.abbreviation,
            "house": self.house.value,
            "sortOrder": self.sort_order,
            "sittings": [s.to_dict() for s in self.sittings],
            "mappedNode": self.mapped_node.value if self.mapped_node else None,
            "mappingMode": self.mapping_mode.value,
        }


@dataclass(frozen=True, slots=True)
class Sponsor:
    member_id: int | None
    name: str
    house: House
    party: str | None
    organisation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "memberId": self.member_id,
            "name": self.name,
            "house": self.house.value,
            "party": self.party,
            "organisation": self.organisation,
        }


@dataclass(frozen=True, slots=True)
class BillType:
    id: int | None
    name: str
    category: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "category": self.category}


@dataclass(frozen=True, slots=True)
class NormalisedBill:
    id: int
    title: str
    former_title: str | None
    summary: str | None
    parliament_url: str
    bill_type: BillType | None
    originating_house: House
    current_house: House
    introduced_session_id: int | None
    included_session_ids: tuple[int, ...]
    carried_over: bool
    source_last_update: str | None
    withdrawn_source_date: str | None
    status: BillStatus
    pipeline_node: PipelineNode
    last_known_pipeline_node: PipelineNode | None
    mapping_mode: MappingMode
    non_standard_route: bool
    stage: StageOccurrence | None
    sponsors: tuple[Sponsor, ...] = ()
    history: tuple[StageOccurrence, ...] = ()
    ping_pong_exchange_number: int | None = None
    details_complete: bool = True
    history_complete: bool = True
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "formerTitle": self.former_title,
            "summary": self.summary,
            "parliamentUrl": self.parliament_url,
            "billType": self.bill_type.to_dict() if self.bill_type else None,
            "originatingHouse": self.originating_house.value,
            "currentHouse": self.current_house.value,
            "introducedSessionId": self.introduced_session_id,
            "includedSessionIds": list(self.included_session_ids),
            "carriedOver": self.carried_over,
            "sourceLastUpdate": self.source_last_update,
            "withdrawnSourceDate": self.withdrawn_source_date,
            "status": self.status.value,
            "pipelineNode": self.pipeline_node.value,
            "lastKnownPipelineNode": (
                self.last_known_pipeline_node.value if self.last_known_pipeline_node else None
            ),
            "mappingMode": self.mapping_mode.value,
            "nonStandardRoute": self.non_standard_route,
            "stage": self.stage.to_current_dict() if self.stage else None,
            "sponsors": [s.to_dict() for s in self.sponsors],
            "history": [h.to_history_dict() for h in self.history],
            "pingPongExchangeNumber": self.ping_pong_exchange_number,
            "detailsComplete": self.details_complete,
            "historyComplete": self.history_complete,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class SnapshotWarning:
    code: str
    message: str
    severity: str = "warning"
    bill_ids: tuple[int, ...] = ()
    stage_ids: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }
        if self.bill_ids:
            payload["billIds"] = list(self.bill_ids)
        if self.stage_ids:
            payload["stageIds"] = list(self.stage_ids)
        return payload


@dataclass(frozen=True, slots=True)
class SnapshotSource:
    name: str
    base_url: str
    session_id: int
    session_label: str
    attribution: str
    licence_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "baseUrl": self.base_url,
            "sessionId": self.session_id,
            "sessionLabel": self.session_label,
            "attribution": self.attribution,
            "licenceUrl": self.licence_url,
        }


@dataclass(frozen=True, slots=True)
class SnapshotCounts:
    total: int = 0
    active: int = 0
    enacted: int = 0
    withdrawn: int = 0
    failed: int = 0
    unknown: int = 0
    special_or_unclassified: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "active": self.active,
            "enacted": self.enacted,
            "withdrawn": self.withdrawn,
            "failed": self.failed,
            "unknown": self.unknown,
            "specialOrUnclassified": self.special_or_unclassified,
        }


@dataclass(frozen=True, slots=True)
class Snapshot:
    schema_version: int
    generated_at: str
    last_full_reconciliation_at: str | None
    status: str
    synthetic: bool
    source: SnapshotSource
    counts: SnapshotCounts
    data_hash: str
    bills: tuple[dict[str, Any], ...] = ()
    warnings: tuple[SnapshotWarning, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "generatedAt": self.generated_at,
            "lastFullReconciliationAt": self.last_full_reconciliation_at,
            "status": self.status,
            "synthetic": self.synthetic,
            "source": self.source.to_dict(),
            "counts": self.counts.to_dict(),
            "warnings": [w.to_dict() for w in self.warnings],
            "dataHash": self.data_hash,
            "bills": list(self.bills),
        }
