"""Stage mapping, terminal precedence, anchoring and date handling."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
import synthetic_source as synthetic

from bill_pipeline.models import (
    BillStatus,
    BillType,
    House,
    MappingMode,
    PipelineNode,
    WarningCode,
)
from bill_pipeline.normalise import (
    next_sitting_date,
    normalise_bill,
    normalise_house,
    normalise_sittings,
    normalise_stage_occurrence,
    parse_calendar_date,
    ping_pong_exchange_number,
    resolve_position,
    sort_history,
)

TODAY = date(2026, 8, 29)


def stage(
    stage_id: int,
    sort_order: int,
    *,
    occurrence: int | None = None,
    house: str = "Commons",
    description: str = "Example stage",
    session_id: int = 40,
    dates: tuple[str, ...] = (),
) -> dict[str, Any]:
    occurrence_id = occurrence if occurrence is not None else 1000 + sort_order
    return {
        "id": occurrence_id,
        "stageId": stage_id,
        "sessionId": session_id,
        "description": description,
        "abbreviation": None,
        "house": house,
        "stageSittings": [
            {"id": 5000 + i, "billStageId": occurrence_id, "date": f"{d}T00:00:00"}
            for i, d in enumerate(dates)
        ],
        "sortOrder": sort_order,
    }


def occurrences(raw: list[dict[str, Any]]) -> tuple[Any, ...]:
    return sort_history([normalise_stage_occurrence(entry, TODAY) for entry in raw])


def bill(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "billId": 1,
        "shortTitle": "Example Bill",
        "originatingHouse": "Commons",
        "currentHouse": "Commons",
        "billWithdrawn": None,
        "isDefeated": False,
        "isAct": False,
        "billTypeId": 1,
        "introducedSessionId": 40,
        "includedSessionIds": [40],
        "lastUpdate": "2026-08-20T09:15:00.1234567",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Houses and dates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Commons", House.COMMONS),
        ("commons", House.COMMONS),
        ("Lords", House.LORDS),
        ("Unassigned", House.UNASSIGNED),
        ("Something new", House.UNASSIGNED),
        (None, House.UNASSIGNED),
        (7, House.UNASSIGNED),
    ],
)
def test_normalise_house_never_guesses(raw: Any, expected: House) -> None:
    assert normalise_house(raw) is expected


def test_source_datetime_is_reduced_to_a_calendar_date_not_an_instant() -> None:
    """The source emits no offset, so the time part is dropped, not reinterpreted."""
    assert parse_calendar_date("2026-09-07T00:00:00") == "2026-09-07"
    assert parse_calendar_date("2026-09-07T23:30:00.1234567") == "2026-09-07"
    assert parse_calendar_date("not a date") is None
    assert parse_calendar_date(None) is None


def test_sitting_retains_the_verbatim_source_value() -> None:
    sittings = normalise_sittings([{"id": 1, "date": "2026-09-07T00:00:00"}])
    assert sittings[0].date == "2026-09-07"
    assert sittings[0].source_date_time == "2026-09-07T00:00:00"
    # No trailing Z is invented for a value that carries no offset.
    assert not sittings[0].source_date_time.endswith("Z")


def test_next_sitting_date_picks_the_earliest_future_or_today_date() -> None:
    sittings = normalise_sittings(
        [
            {"id": 1, "date": "2026-08-01T00:00:00"},
            {"id": 2, "date": "2026-09-20T00:00:00"},
            {"id": 3, "date": "2026-09-07T00:00:00"},
        ]
    )
    assert next_sitting_date(sittings, TODAY) == "2026-09-07"


def test_next_sitting_date_includes_today() -> None:
    sittings = normalise_sittings([{"id": 1, "date": "2026-08-29T00:00:00"}])
    assert next_sitting_date(sittings, TODAY) == "2026-08-29"


def test_next_sitting_date_is_none_when_every_sitting_is_past() -> None:
    sittings = normalise_sittings(
        [{"id": 1, "date": "2026-01-05T00:00:00"}, {"id": 2, "date": "2026-02-05T00:00:00"}]
    )
    assert next_sitting_date(sittings, TODAY) is None


# ---------------------------------------------------------------------------
# Direct mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage_id", "expected"),
    [
        (6, PipelineNode.COMMONS_FIRST_READING),
        (7, PipelineNode.COMMONS_SECOND_READING),
        (25, PipelineNode.COMMONS_SECOND_READING),
        (8, PipelineNode.COMMONS_COMMITTEE),
        (49, PipelineNode.COMMONS_COMMITTEE),
        (9, PipelineNode.COMMONS_REPORT),
        (10, PipelineNode.COMMONS_THIRD_READING),
        (1, PipelineNode.LORDS_FIRST_READING),
        (2, PipelineNode.LORDS_SECOND_READING),
        (30, PipelineNode.LORDS_SECOND_READING),
        (3, PipelineNode.LORDS_COMMITTEE),
        (46, PipelineNode.LORDS_COMMITTEE),
        (4, PipelineNode.LORDS_REPORT),
        (5, PipelineNode.LORDS_THIRD_READING),
        (12, PipelineNode.PING_PONG),
        (42, PipelineNode.PING_PONG),
        (11, PipelineNode.ROYAL_ASSENT),
    ],
)
def test_direct_stage_mapping(stage_id: int, expected: PipelineNode) -> None:
    current = normalise_stage_occurrence(stage(stage_id, 1), TODAY)
    position = resolve_position(bill(), current, (current,))
    assert position.node is expected
    if stage_id != 11:
        assert position.mapping_mode is MappingMode.DIRECT
        assert position.non_standard_route is False


def test_both_originating_houses_use_the_same_node_vocabulary() -> None:
    """Route selection comes from originatingHouse, never from sortOrder."""
    commons_first = normalise_bill(
        summary_raw=bill(originatingHouse="Commons", currentStage=stage(6, 1)),
        detail_raw=None,
        stages_raw=[stage(6, 1)],
        bill_types={},
        session_id=40,
        today=TODAY,
    )
    lords_first = normalise_bill(
        summary_raw=bill(originatingHouse="Lords", currentStage=stage(1, 1, house="Lords")),
        detail_raw=None,
        stages_raw=[stage(1, 1, house="Lords")],
        bill_types={},
        session_id=40,
        today=TODAY,
    )
    assert commons_first.originating_house is House.COMMONS
    assert commons_first.pipeline_node is PipelineNode.COMMONS_FIRST_READING
    assert lords_first.originating_house is House.LORDS
    assert lords_first.pipeline_node is PipelineNode.LORDS_FIRST_READING


def test_lords_origin_bill_in_the_commons_keeps_commons_nodes() -> None:
    """A Lords-first Bill's second House is the Commons; the node says so."""
    history = occurrences(
        [
            stage(1, 1, house="Lords"),
            stage(2, 2, house="Lords"),
            stage(3, 3, house="Lords"),
            stage(4, 4, house="Lords"),
            stage(5, 5, house="Lords"),
            stage(6, 6),
        ]
    )
    position = resolve_position(bill(originatingHouse="Lords"), history[-1], history)
    assert position.node is PipelineNode.COMMONS_FIRST_READING


# ---------------------------------------------------------------------------
# Ancillary anchoring
# ---------------------------------------------------------------------------


def test_ancillary_stage_anchors_to_the_previous_canonical_stage() -> None:
    history = occurrences(
        [
            stage(6, 1),
            stage(7, 2),
            stage(8, 3),
            stage(14, 4, description="Programme motion"),
        ]
    )
    position = resolve_position(bill(), history[-1], history)
    assert position.node is PipelineNode.COMMONS_COMMITTEE
    assert position.mapping_mode is MappingMode.PREVIOUS_CANONICAL
    assert position.non_standard_route is True
    assert position.stage_detail == "Programme motion"


def test_anchor_reaches_back_into_an_earlier_session() -> None:
    """Carry-over: the canonical stage sits in the previous session."""
    history = occurrences(
        [
            stage(6, 1, session_id=39),
            stage(7, 2, session_id=39),
            stage(8, 3, session_id=39),
            stage(18, 4, session_id=40, description="Carry-over motion"),
        ]
    )
    position = resolve_position(
        bill(introducedSessionId=39, includedSessionIds=[39, 40]), history[-1], history
    )
    assert position.node is PipelineNode.COMMONS_COMMITTEE
    assert position.mapping_mode is MappingMode.PREVIOUS_CANONICAL


def test_ancillary_stage_without_a_canonical_predecessor_is_special_procedure() -> None:
    history = occurrences([stage(15, 1, description="Money resolution")])
    position = resolve_position(bill(), history[-1], history)
    assert position.node is PipelineNode.SPECIAL_PROCEDURE
    assert position.mapping_mode is MappingMode.SPECIAL
    assert position.non_standard_route is True
    assert WarningCode.NO_CANONICAL_PREDECESSOR in position.warnings


def test_private_bill_examination_uses_the_same_anchoring_rule() -> None:
    anchored = occurrences([stage(1, 1, house="Lords"), stage(41, 2, house="Unassigned")])
    assert resolve_position(bill(), anchored[-1], anchored).node is PipelineNode.LORDS_FIRST_READING

    alone = occurrences([stage(41, 1, house="Unassigned")])
    assert resolve_position(bill(), alone[-1], alone).node is PipelineNode.SPECIAL_PROCEDURE


def test_anchor_uses_the_occurrence_id_not_the_stage_reference_id() -> None:
    """A repeated stage must anchor from the right occurrence.

    Committee stage appears twice. The current occurrence is the *second*
    programme motion, so anchoring must look before that occurrence rather
    than before the first occurrence carrying the same stageId.
    """
    history = occurrences(
        [
            stage(6, 1, occurrence=11),
            stage(14, 2, occurrence=12, description="Programme motion"),
            stage(7, 3, occurrence=13),
            stage(14, 4, occurrence=14, description="Programme motion"),
        ]
    )
    current = next(o for o in history if o.bill_stage_id == 14)
    position = resolve_position(bill(), current, history)
    assert position.node is PipelineNode.COMMONS_SECOND_READING


def test_unrecognised_stage_id_becomes_unknown_and_keeps_the_raw_label() -> None:
    history = occurrences([stage(6, 1), stage(9999, 2, description="A brand new stage")])
    position = resolve_position(bill(), history[-1], history)
    assert position.node is PipelineNode.UNKNOWN
    assert position.mapping_mode is MappingMode.UNKNOWN
    assert position.stage_detail == "A brand new stage"
    assert WarningCode.UNKNOWN_STAGE_ID in position.warnings
    # The description said "stage" but nothing was inferred from the words.
    assert position.node is not PipelineNode.COMMONS_COMMITTEE


# ---------------------------------------------------------------------------
# Terminal precedence
# ---------------------------------------------------------------------------


def test_withdrawn_beats_every_other_flag() -> None:
    history = occurrences([stage(6, 1), stage(7, 2)])
    position = resolve_position(
        bill(billWithdrawn="2026-06-02T00:00:00", isDefeated=True, isAct=True),
        history[-1],
        history,
    )
    assert position.status is BillStatus.WITHDRAWN
    assert position.node is PipelineNode.WITHDRAWN
    assert WarningCode.TERMINAL_FLAGS_CONFLICT in position.warnings


def test_defeated_beats_enacted() -> None:
    history = occurrences([stage(6, 1)])
    position = resolve_position(bill(isDefeated=True, isAct=True), history[-1], history)
    assert position.status is BillStatus.FAILED
    assert position.node is PipelineNode.FAILED
    assert WarningCode.TERMINAL_FLAGS_CONFLICT in position.warnings


def test_royal_assent_stage_alone_marks_a_bill_enacted() -> None:
    history = occurrences([stage(6, 1), stage(11, 2, house="Unassigned")])
    position = resolve_position(bill(isAct=False), history[-1], history)
    assert position.status is BillStatus.ENACTED
    assert position.node is PipelineNode.ROYAL_ASSENT
    # isAct false plus a Royal Assent stage is not a conflict; either satisfies the rule.
    assert WarningCode.TERMINAL_FLAGS_CONFLICT not in position.warnings


def test_terminal_bills_retain_where_they_stopped() -> None:
    history = occurrences([stage(6, 1), stage(7, 2), stage(8, 3)])
    position = resolve_position(bill(billWithdrawn="2026-06-02T00:00:00"), history[-1], history)
    assert position.status is BillStatus.WITHDRAWN
    assert position.last_known_node is PipelineNode.COMMONS_COMMITTEE


def test_an_old_quiet_bill_is_active_not_failed() -> None:
    """Only isDefeated makes a Bill failed. Lapsing is not inferred."""
    history = occurrences([stage(6, 1, dates=("2025-01-05",))])
    position = resolve_position(bill(lastUpdate="2025-01-05T00:00:00"), history[-1], history)
    assert position.status is BillStatus.ACTIVE
    assert position.node is PipelineNode.COMMONS_FIRST_READING


def test_missing_current_stage_is_unknown_rather_than_a_guess() -> None:
    position = resolve_position(bill(), None, ())
    assert position.status is BillStatus.UNKNOWN
    assert position.node is PipelineNode.UNKNOWN
    assert WarningCode.NO_CURRENT_STAGE in position.warnings


# ---------------------------------------------------------------------------
# Ping-pong exchanges
# ---------------------------------------------------------------------------


def test_ping_pong_sequence_numbers_each_exchange() -> None:
    """12 then 13 then 42 yields exchanges 1, 2 and 3."""
    raw = [
        stage(10, 1),
        stage(12, 2, occurrence=101),
        stage(13, 3, occurrence=102, house="Lords"),
        stage(42, 4, occurrence=103),
    ]
    history = occurrences(raw)
    expected = {101: 1, 102: 2, 103: 3}
    for occurrence_id, exchange in expected.items():
        current = next(o for o in history if o.bill_stage_id == occurrence_id)
        assert ping_pong_exchange_number(history, current, True) == exchange


def test_exchange_number_is_none_without_complete_history() -> None:
    history = occurrences([stage(12, 1, occurrence=101)])
    current = history[0]
    assert ping_pong_exchange_number(history, current, False) is None


def test_exchange_number_is_none_outside_consideration_stages() -> None:
    history = occurrences([stage(9, 1)])
    assert ping_pong_exchange_number(history, history[0], True) is None


# ---------------------------------------------------------------------------
# Whole-Bill normalisation
# ---------------------------------------------------------------------------


def test_normalise_bill_produces_the_published_shape(bill_types: dict[int, BillType]) -> None:
    source = synthetic.SYNTHETIC_BILLS[3]  # Health Standards Bill, Commons report stage
    result = normalise_bill(
        summary_raw=source.list_entry(),
        detail_raw=source.detail(),
        stages_raw=source.stage_objects(),
        bill_types=bill_types,
        session_id=40,
        today=TODAY,
    ).to_dict()

    assert result["id"] == 9004
    assert result["pipelineNode"] == "commons_report"
    assert result["status"] == "active"
    assert result["mappingMode"] == "direct"
    assert result["parliamentUrl"] == "https://bills.parliament.uk/bills/9004"
    assert result["stage"]["nextSittingDate"] == "2026-09-07"
    assert result["sourceLastUpdate"] == "2026-08-28T18:42:57.9656298"
    assert result["billType"] == {"id": 1, "name": "Government Bill", "category": "Public"}


def test_sponsor_photographs_are_discarded(bill_types: dict[int, BillType]) -> None:
    source = synthetic.SYNTHETIC_BILLS[3]
    result = normalise_bill(
        summary_raw=source.list_entry(),
        detail_raw=source.detail(),
        stages_raw=source.stage_objects(),
        bill_types=bill_types,
        session_id=40,
        today=TODAY,
    ).to_dict()
    rendered = str(result)
    assert "memberPhoto" not in rendered
    assert "Thumbnail" not in rendered
    assert result["sponsors"][0]["name"] == "Wesley Marchant"


def test_carried_over_is_derived_from_the_session_ids() -> None:
    carried = normalise_bill(
        summary_raw=bill(
            introducedSessionId=39, includedSessionIds=[39, 40], currentStage=stage(8, 3)
        ),
        detail_raw=None,
        stages_raw=[stage(6, 1), stage(8, 3)],
        bill_types={},
        session_id=40,
        today=TODAY,
    )
    assert carried.carried_over is True

    fresh = normalise_bill(
        summary_raw=bill(currentStage=stage(6, 1)),
        detail_raw=None,
        stages_raw=[stage(6, 1)],
        bill_types={},
        session_id=40,
        today=TODAY,
    )
    assert fresh.carried_over is False


def test_incomplete_fetches_are_flagged_not_hidden() -> None:
    result = normalise_bill(
        summary_raw=bill(currentStage=stage(6, 1)),
        detail_raw=None,
        stages_raw=None,
        bill_types={},
        session_id=40,
        today=TODAY,
    )
    assert result.details_complete is False
    assert result.history_complete is False
    assert WarningCode.INCOMPLETE_DETAILS in result.warnings
    assert WarningCode.INCOMPLETE_HISTORY in result.warnings


def test_unassigned_origin_is_flagged_and_never_guessed() -> None:
    result = normalise_bill(
        summary_raw=bill(
            originatingHouse="Unassigned", currentHouse="Unassigned", currentStage=stage(6, 1)
        ),
        detail_raw=None,
        stages_raw=[stage(6, 1)],
        bill_types={},
        session_id=40,
        today=TODAY,
    )
    assert result.originating_house is House.UNASSIGNED
    assert WarningCode.UNASSIGNED_ORIGINATING_HOUSE in result.warnings


def test_history_is_ordered_by_sort_order_then_occurrence_id() -> None:
    history = occurrences(
        [stage(8, 2, occurrence=30), stage(6, 1, occurrence=10), stage(7, 2, occurrence=20)]
    )
    assert [o.bill_stage_id for o in history] == [10, 20, 30]


def test_summary_falls_back_to_the_long_title() -> None:
    result = normalise_bill(
        summary_raw=bill(currentStage=stage(6, 1)),
        detail_raw={
            **bill(),
            "summary": None,
            "longTitle": "A Bill to do a thing.",
            "sponsors": [],
        },
        stages_raw=[stage(6, 1)],
        bill_types={},
        session_id=40,
        today=TODAY,
    )
    assert result.summary == "A Bill to do a thing."
