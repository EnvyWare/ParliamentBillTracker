"""Turn raw Bills API objects into the normalised process model.

Three rules drive everything in this module:

* Terminal state wins over stage position, in a fixed precedence.
* An ancillary stage never replaces a Bill's position; it anchors back to the
  most recent canonical stage and keeps its own label as detail.
* Anything the table does not recognise becomes an explicit ``unknown``
  record with the raw source retained. Unrecognised input is a normal,
  visible condition, never a reason to guess or to drop a Bill.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .config import BILL_PAGE_TEMPLATE
from .models import (
    CANONICAL_NODES,
    BillStatus,
    BillType,
    House,
    MappingMode,
    NormalisedBill,
    PipelineNode,
    Sitting,
    Sponsor,
    StageOccurrence,
    WarningCode,
)
from .stage_map import CONSIDERATION_STAGE_IDS, ROYAL_ASSENT_STAGE_ID, StageCategory, rule_for

LONDON = ZoneInfo("Europe/London")


def today_in_london(now: datetime | None = None) -> date:
    """The Parliamentary calendar date currently in effect."""
    moment = now.astimezone(LONDON) if now is not None else datetime.now(tz=LONDON)
    return moment.date()


def normalise_house(raw: object) -> House:
    """Map an API House string onto the normalised enum.

    Anything unrecognised, including ``None`` and the API's own
    ``"Unassigned"``, becomes ``unassigned``. It is never guessed.
    """
    if not isinstance(raw, str):
        return House.UNASSIGNED
    match raw.strip().lower():
        case "commons":
            return House.COMMONS
        case "lords":
            return House.LORDS
        case _:
            return House.UNASSIGNED


def parse_calendar_date(raw: object) -> str | None:
    """Extract a ``YYYY-MM-DD`` calendar date from a source value.

    The source emits values such as ``2026-09-07T00:00:00`` with no guaranteed
    UTC offset, so the time part is discarded rather than being reinterpreted
    as an instant.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = raw.strip().split("T", 1)[0]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def normalise_sittings(raw_sittings: object) -> tuple[Sitting, ...]:
    if not isinstance(raw_sittings, list):
        return ()
    sittings: list[Sitting] = []
    for entry in raw_sittings:
        if not isinstance(entry, dict):
            continue
        raw_date = entry.get("date")
        sittings.append(
            Sitting(
                id=entry.get("id") if isinstance(entry.get("id"), int) else None,
                date=parse_calendar_date(raw_date),
                source_date_time=raw_date if isinstance(raw_date, str) else None,
            )
        )
    # Deterministic order: by calendar date, then id. Undated sittings sort last.
    return tuple(
        sorted(sittings, key=lambda s: (s.date is None, s.date or "", s.id if s.id else 0))
    )


def next_sitting_date(sittings: tuple[Sitting, ...], today: date) -> str | None:
    """Earliest sitting date on or after ``today``.

    A sitting is a scheduled or recorded event, not proof that a stage has
    finished, so this is only ever used as a "what happens next" hint.
    """
    upcoming = [
        s.date for s in sittings if s.date is not None and date.fromisoformat(s.date) >= today
    ]
    return min(upcoming) if upcoming else None


def normalise_stage_occurrence(raw: dict[str, Any], today: date) -> StageOccurrence:
    """Normalise one stage occurrence and record how it maps."""
    stage_id = raw.get("stageId") if isinstance(raw.get("stageId"), int) else None
    rule = rule_for(stage_id)
    sittings = normalise_sittings(raw.get("stageSittings"))

    if rule is None:
        mapped_node: PipelineNode | None = None
        mapping_mode = MappingMode.UNKNOWN
    elif rule.category is StageCategory.DIRECT:
        mapped_node = rule.node
        mapping_mode = MappingMode.DIRECT
    else:
        mapped_node = None
        mapping_mode = MappingMode.SPECIAL

    description = raw.get("description")
    return StageOccurrence(
        bill_stage_id=raw.get("id") if isinstance(raw.get("id"), int) else None,
        stage_id=stage_id,
        session_id=raw.get("sessionId") if isinstance(raw.get("sessionId"), int) else None,
        label=description if isinstance(description, str) and description else "Unnamed stage",
        abbreviation=raw.get("abbreviation") if isinstance(raw.get("abbreviation"), str) else None,
        house=normalise_house(raw.get("house")),
        sort_order=raw.get("sortOrder") if isinstance(raw.get("sortOrder"), int) else None,
        sittings=sittings,
        next_sitting_date=next_sitting_date(sittings, today),
        detail=None,
        mapped_node=mapped_node,
        mapping_mode=mapping_mode,
    )


def sort_history(history: list[StageOccurrence]) -> tuple[StageOccurrence, ...]:
    """Order by API ``sortOrder``, then occurrence id as a deterministic tie-break."""
    return tuple(
        sorted(
            history,
            key=lambda s: (
                s.sort_order if s.sort_order is not None else -1,
                s.bill_stage_id if s.bill_stage_id is not None else -1,
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class Position:
    """Where a Bill sits, and how that was decided."""

    status: BillStatus
    node: PipelineNode
    mapping_mode: MappingMode
    non_standard_route: bool
    last_known_node: PipelineNode | None
    stage_detail: str | None
    warnings: tuple[str, ...]


def _last_canonical(history: tuple[StageOccurrence, ...]) -> PipelineNode | None:
    for occurrence in reversed(history):
        if occurrence.mapped_node is not None and occurrence.mapped_node in CANONICAL_NODES:
            return occurrence.mapped_node
    return None


def _anchor_candidates(
    history: tuple[StageOccurrence, ...], current: StageOccurrence
) -> tuple[StageOccurrence, ...]:
    """History occurrences that precede ``current``.

    The current occurrence is located by its ``billStageId``, which is the
    per-Bill occurrence id rather than the reusable stage-reference id. If the
    occurrence is absent from the history (an incomplete fetch), fall back to
    ordering by ``sortOrder`` so anchoring still degrades usefully.
    """
    for index, occurrence in enumerate(history):
        if current.bill_stage_id is not None and occurrence.bill_stage_id == current.bill_stage_id:
            return history[:index]
    if current.sort_order is None:
        return history
    return tuple(
        occurrence
        for occurrence in history
        if occurrence.sort_order is not None and occurrence.sort_order < current.sort_order
    )


def resolve_position(
    raw_bill: dict[str, Any],
    current: StageOccurrence | None,
    history: tuple[StageOccurrence, ...],
) -> Position:
    """Apply terminal precedence, then map the current stage.

    Precedence (specification section 8.2): withdrawn, then defeated, then
    enacted, then the current stage, then unknown.
    """
    warnings: list[str] = []

    withdrawn_raw = raw_bill.get("billWithdrawn")
    is_withdrawn = withdrawn_raw is not None
    is_defeated = raw_bill.get("isDefeated") is True
    is_enacted = raw_bill.get("isAct") is True or (
        current is not None and current.stage_id == ROYAL_ASSENT_STAGE_ID
    )

    if sum([is_withdrawn, is_defeated, is_enacted]) > 1:
        warnings.append(WarningCode.TERMINAL_FLAGS_CONFLICT)

    last_known = _last_canonical(history)
    if last_known is None and current is not None and current.mapped_node in CANONICAL_NODES:
        last_known = current.mapped_node

    if is_withdrawn:
        return Position(
            BillStatus.WITHDRAWN,
            PipelineNode.WITHDRAWN,
            MappingMode.TERMINAL,
            False,
            last_known,
            current.label if current else None,
            tuple(warnings),
        )
    if is_defeated:
        return Position(
            BillStatus.FAILED,
            PipelineNode.FAILED,
            MappingMode.TERMINAL,
            False,
            last_known,
            current.label if current else None,
            tuple(warnings),
        )
    if is_enacted:
        return Position(
            BillStatus.ENACTED,
            PipelineNode.ROYAL_ASSENT,
            MappingMode.TERMINAL,
            False,
            last_known or PipelineNode.ROYAL_ASSENT,
            current.label if current else None,
            tuple(warnings),
        )

    if current is None:
        warnings.append(WarningCode.NO_CURRENT_STAGE)
        return Position(
            BillStatus.UNKNOWN,
            PipelineNode.UNKNOWN,
            MappingMode.UNKNOWN,
            False,
            last_known,
            None,
            tuple(warnings),
        )

    rule = rule_for(current.stage_id)

    if rule is None:
        # A stage id this build has never seen. Publish it visibly as unknown
        # rather than inferring anything from its description.
        warnings.append(WarningCode.UNKNOWN_STAGE_ID)
        return Position(
            BillStatus.ACTIVE,
            PipelineNode.UNKNOWN,
            MappingMode.UNKNOWN,
            True,
            last_known,
            current.label,
            tuple(warnings),
        )

    if rule.category is StageCategory.DIRECT:
        assert rule.node is not None
        return Position(
            BillStatus.ACTIVE,
            rule.node,
            MappingMode.DIRECT,
            False,
            rule.node,
            None,
            tuple(warnings),
        )

    # Ancillary or private-Bill examination: anchor to the previous canonical
    # stage, including one in an earlier included session.
    anchor = _last_canonical(_anchor_candidates(history, current))
    if anchor is not None:
        return Position(
            BillStatus.ACTIVE,
            anchor,
            MappingMode.PREVIOUS_CANONICAL,
            True,
            anchor,
            current.label,
            tuple(warnings),
        )

    warnings.append(WarningCode.NO_CANONICAL_PREDECESSOR)
    return Position(
        BillStatus.ACTIVE,
        PipelineNode.SPECIAL_PROCEDURE,
        MappingMode.SPECIAL,
        True,
        last_known,
        current.label,
        tuple(warnings),
    )


def ping_pong_exchange_number(
    history: tuple[StageOccurrence, ...],
    current: StageOccurrence | None,
    history_complete: bool,
) -> int | None:
    """Which consideration-of-amendments exchange the Bill is currently in.

    Counted as occurrences of a consideration stage up to and including the
    current one. Called an exchange rather than a round: one exchange is a
    single House considering the other House's amendments or message.
    """
    if current is None or not history_complete:
        return None
    if current.stage_id not in CONSIDERATION_STAGE_IDS:
        return None

    count = 0
    for occurrence in history:
        if occurrence.stage_id in CONSIDERATION_STAGE_IDS:
            count += 1
        if current.bill_stage_id is not None and occurrence.bill_stage_id == current.bill_stage_id:
            return count
    # The current occurrence was not present in the fetched history.
    return None


def normalise_sponsors(raw_detail: dict[str, Any] | None) -> tuple[Sponsor, ...]:
    """Names and parties only.

    Member photograph and contact URLs returned by the API are deliberately
    discarded: this project never publishes or proxies Parliamentary imagery.
    """
    if not raw_detail:
        return ()
    raw_sponsors = raw_detail.get("sponsors")
    if not isinstance(raw_sponsors, list):
        return ()

    def sort_key(entry: dict[str, Any]) -> int:
        order = entry.get("sortOrder")
        return order if isinstance(order, int) else 0

    ordered = sorted((s for s in raw_sponsors if isinstance(s, dict)), key=sort_key)

    sponsors: list[Sponsor] = []
    for entry in ordered:
        member = entry.get("member") if isinstance(entry.get("member"), dict) else None
        organisation = (
            entry.get("organisation") if isinstance(entry.get("organisation"), dict) else None
        )
        organisation_name = (
            organisation.get("name")
            if organisation and isinstance(organisation.get("name"), str)
            else None
        )
        name = member.get("name") if member and isinstance(member.get("name"), str) else None
        display_name = name or organisation_name
        if not display_name:
            continue
        sponsors.append(
            Sponsor(
                member_id=(
                    member.get("memberId")
                    if member and isinstance(member.get("memberId"), int)
                    else None
                ),
                name=display_name,
                house=normalise_house(member.get("house") if member else None),
                party=(
                    member.get("party") if member and isinstance(member.get("party"), str) else None
                ),
                organisation=organisation_name,
            )
        )
    return tuple(sponsors)


def _summary_text(raw_detail: dict[str, Any] | None) -> str | None:
    """Prefer the API summary, falling back to the Bill's long title.

    The API's ``summary`` is null for most Bills while ``longTitle`` carries
    Parliament's own one-sentence description of what the Bill does. Using it
    as the fallback gives the details panel and the search index real content
    without inventing any wording.
    """
    if not raw_detail:
        return None
    for key in ("summary", "longTitle"):
        value = raw_detail.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def normalise_bill(
    *,
    summary_raw: dict[str, Any],
    detail_raw: dict[str, Any] | None,
    stages_raw: list[dict[str, Any]] | None,
    bill_types: dict[int, BillType],
    session_id: int,
    today: date,
) -> NormalisedBill:
    """Build one normalised Bill from its list entry, detail and stage history."""
    source = {**summary_raw, **(detail_raw or {})}
    bill_id = source.get("billId")
    if not isinstance(bill_id, int):
        raise ValueError(f"Bill is missing an integer billId: {summary_raw!r}")

    details_complete = detail_raw is not None
    history_complete = stages_raw is not None

    raw_current = source.get("currentStage")
    current = (
        normalise_stage_occurrence(raw_current, today) if isinstance(raw_current, dict) else None
    )

    history = sort_history(
        [
            normalise_stage_occurrence(entry, today)
            for entry in (stages_raw or [])
            if isinstance(entry, dict)
        ]
    )

    position = resolve_position(source, current, history)
    warnings = list(position.warnings)

    if not details_complete:
        warnings.append(WarningCode.INCOMPLETE_DETAILS)
    if not history_complete:
        warnings.append(WarningCode.INCOMPLETE_HISTORY)

    originating_house = normalise_house(source.get("originatingHouse"))
    if originating_house is House.UNASSIGNED:
        warnings.append(WarningCode.UNASSIGNED_ORIGINATING_HOUSE)
    if position.non_standard_route:
        warnings.append(WarningCode.NON_STANDARD_ROUTE)

    included = source.get("includedSessionIds")
    included_ids = (
        tuple(i for i in included if isinstance(i, int)) if isinstance(included, list) else ()
    )
    introduced = source.get("introducedSessionId")
    introduced_id = introduced if isinstance(introduced, int) else None

    stage = None
    if current is not None:
        stage = StageOccurrence(
            bill_stage_id=current.bill_stage_id,
            stage_id=current.stage_id,
            session_id=current.session_id,
            label=current.label,
            abbreviation=current.abbreviation,
            house=current.house,
            sort_order=current.sort_order,
            sittings=current.sittings,
            next_sitting_date=current.next_sitting_date,
            detail=position.stage_detail,
            mapped_node=current.mapped_node,
            mapping_mode=current.mapping_mode,
        )

    title = source.get("shortTitle")
    bill_type_id = source.get("billTypeId")

    return NormalisedBill(
        id=bill_id,
        title=title.strip() if isinstance(title, str) and title.strip() else f"Bill {bill_id}",
        former_title=(
            source.get("formerShortTitle")
            if isinstance(source.get("formerShortTitle"), str)
            else None
        ),
        summary=_summary_text(detail_raw),
        parliament_url=BILL_PAGE_TEMPLATE.format(bill_id=bill_id),
        bill_type=bill_types.get(bill_type_id) if isinstance(bill_type_id, int) else None,
        originating_house=originating_house,
        current_house=normalise_house(source.get("currentHouse")),
        introduced_session_id=introduced_id,
        included_session_ids=included_ids,
        carried_over=session_id in included_ids and introduced_id != session_id,
        source_last_update=(
            source.get("lastUpdate") if isinstance(source.get("lastUpdate"), str) else None
        ),
        withdrawn_source_date=(
            source.get("billWithdrawn") if isinstance(source.get("billWithdrawn"), str) else None
        ),
        status=position.status,
        pipeline_node=position.node,
        last_known_pipeline_node=position.last_known_node,
        mapping_mode=position.mapping_mode,
        non_standard_route=position.non_standard_route,
        stage=stage,
        sponsors=normalise_sponsors(detail_raw),
        history=history,
        ping_pong_exchange_number=ping_pong_exchange_number(history, current, history_complete),
        details_complete=details_complete,
        history_complete=history_complete,
        warnings=tuple(dict.fromkeys(warnings)),
    )
