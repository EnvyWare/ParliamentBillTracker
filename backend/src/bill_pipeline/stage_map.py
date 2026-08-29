"""The single table that maps Parliament stage ids onto pipeline nodes.

Mapping is by numeric ``stageId`` only. Free-text matching on a stage
description is never used: a renamed stage must not silently change a Bill's
position, and a newly introduced stage must surface as ``unknown`` rather than
being guessed from words that happen to look familiar.

``source_name`` and ``source_house`` are recorded purely so
``docs/stage-mapping.md`` can be generated from this table and so the
catalogue test can prove the checked-in fixture still matches what the API
publishes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .models import House, PipelineNode

#: Date the published ``/Stages`` catalogue was last reviewed against this table.
CATALOGUE_REVIEWED = "2026-08-29"


class StageCategory(StrEnum):
    """How a stage id participates in the process chart."""

    #: Replaces the Bill's position with a canonical node.
    DIRECT = "direct"
    #: Runs alongside the process; anchors back to the previous canonical stage.
    ANCILLARY = "ancillary"
    #: Private-Bill examination; anchors back, otherwise special procedure.
    PRIVATE_EXAMINATION = "private_examination"


@dataclass(frozen=True, slots=True)
class StageRule:
    stage_id: int
    category: StageCategory
    source_name: str
    source_house: House
    node: PipelineNode | None = None
    note: str = ""


def _direct(stage_id: int, name: str, house: House, node: PipelineNode) -> StageRule:
    return StageRule(stage_id, StageCategory.DIRECT, name, house, node)


def _ancillary(stage_id: int, name: str, house: House, note: str = "") -> StageRule:
    return StageRule(stage_id, StageCategory.ANCILLARY, name, house, None, note)


def _examination(stage_id: int, name: str, house: House) -> StageRule:
    return StageRule(stage_id, StageCategory.PRIVATE_EXAMINATION, name, house, None)


_RULES: Final[tuple[StageRule, ...]] = (
    # -- Lords main stages -------------------------------------------------
    _direct(1, "1st reading", House.LORDS, PipelineNode.LORDS_FIRST_READING),
    _direct(2, "2nd reading", House.LORDS, PipelineNode.LORDS_SECOND_READING),
    _direct(30, "Second reading committee", House.LORDS, PipelineNode.LORDS_SECOND_READING),
    _direct(3, "Committee stage", House.LORDS, PipelineNode.LORDS_COMMITTEE),
    _direct(24, "Order of Commitment discharged", House.LORDS, PipelineNode.LORDS_COMMITTEE),
    _direct(27, "Committee negatived", House.LORDS, PipelineNode.LORDS_COMMITTEE),
    _direct(35, "Instruction to Committee on the Bill", House.LORDS, PipelineNode.LORDS_COMMITTEE),
    _direct(46, "Lords Special Public Bill Committee", House.LORDS, PipelineNode.LORDS_COMMITTEE),
    _direct(4, "Report stage", House.LORDS, PipelineNode.LORDS_REPORT),
    _direct(5, "3rd reading", House.LORDS, PipelineNode.LORDS_THIRD_READING),
    # -- Commons main stages -----------------------------------------------
    _direct(6, "1st reading", House.COMMONS, PipelineNode.COMMONS_FIRST_READING),
    _direct(7, "2nd reading", House.COMMONS, PipelineNode.COMMONS_SECOND_READING),
    _direct(25, "Second reading committee", House.COMMONS, PipelineNode.COMMONS_SECOND_READING),
    _direct(8, "Committee stage", House.COMMONS, PipelineNode.COMMONS_COMMITTEE),
    _direct(26, "Order of Commitment discharged", House.COMMONS, PipelineNode.COMMONS_COMMITTEE),
    _direct(43, "Select Committee stage", House.COMMONS, PipelineNode.COMMONS_COMMITTEE),
    _direct(47, "Committal (to a Select Committee)", House.COMMONS, PipelineNode.COMMONS_COMMITTEE),
    _direct(
        48,
        "Committee stage (re-committed clauses and schedules)",
        House.COMMONS,
        PipelineNode.COMMONS_COMMITTEE,
    ),
    _direct(49, "Committee of the whole House", House.COMMONS, PipelineNode.COMMONS_COMMITTEE),
    _direct(
        50,
        "Power of public bill committee to send for persons, papers and records",
        House.COMMONS,
        PipelineNode.COMMONS_COMMITTEE,
    ),
    _direct(9, "Report stage", House.COMMONS, PipelineNode.COMMONS_REPORT),
    _direct(10, "3rd reading", House.COMMONS, PipelineNode.COMMONS_THIRD_READING),
    # -- Shared stages -----------------------------------------------------
    _direct(12, "Consideration of Lords amendments", House.COMMONS, PipelineNode.PING_PONG),
    _direct(
        13,
        "Consideration of Commons amendments and / or reasons",
        House.LORDS,
        PipelineNode.PING_PONG,
    ),
    _direct(39, "Reconsideration", House.COMMONS, PipelineNode.PING_PONG),
    _direct(40, "Consequential consideration", House.COMMONS, PipelineNode.PING_PONG),
    _direct(42, "Consideration of Lords message", House.COMMONS, PipelineNode.PING_PONG),
    _direct(11, "Royal Assent", House.UNASSIGNED, PipelineNode.ROYAL_ASSENT),
    # -- Ancillary stages --------------------------------------------------
    _ancillary(14, "Programme motion", House.COMMONS),
    _ancillary(15, "Money resolution", House.COMMONS),
    _ancillary(18, "Carry-over motion", House.COMMONS),
    _ancillary(19, "Carry-over motion", House.LORDS),
    _ancillary(20, "Motion to suspend Bill till next session considered", House.COMMONS),
    _ancillary(21, "Bill reintroduced", House.COMMONS),
    _ancillary(22, "Bill reintroduced", House.LORDS),
    _ancillary(28, "Guillotine motion", House.COMMONS),
    _ancillary(29, "Allocation of time motion", House.COMMONS),
    _ancillary(31, "Motion to suspend Bill till next session approved", House.COMMONS),
    _ancillary(32, "Motion to revive Bill", House.COMMONS),
    _ancillary(33, "Motion to suspend Bill till next session approved", House.LORDS),
    _ancillary(34, "Motion to revive Bill", House.LORDS),
    _ancillary(36, "Ways and Means resolution", House.COMMONS),
    _ancillary(37, "Instruction", House.COMMONS),
    _ancillary(
        38,
        "Legislative Grand Committee",
        House.COMMONS,
        note=(
            "Not enumerated in the original specification tables, which covered 48 of the 49 "
            "published stage ids. Classified as ancillary by the implementation because it "
            "runs alongside the main stages rather than replacing one, matching the "
            "specification's own definition of the ancillary category. See docs/stage-mapping.md."
        ),
    ),
    _ancillary(44, "Second House Examination", House.COMMONS),
    # -- Private-Bill examination ------------------------------------------
    _examination(16, "Lords Examiners", House.UNASSIGNED),
    _examination(17, "Commons Examiners", House.UNASSIGNED),
    _examination(
        23, "Petition to introduce a Private Bill presented to Parliament", House.UNASSIGNED
    ),
    _examination(41, "Examination for compliance with Standing Orders", House.UNASSIGNED),
)

STAGE_RULES: Final[dict[int, StageRule]] = {rule.stage_id: rule for rule in _RULES}

KNOWN_STAGE_IDS: Final[frozenset[int]] = frozenset(STAGE_RULES)

#: Stage ids that count as one consideration-of-amendments exchange.
CONSIDERATION_STAGE_IDS: Final[frozenset[int]] = frozenset(
    stage_id for stage_id, rule in STAGE_RULES.items() if rule.node is PipelineNode.PING_PONG
)

ROYAL_ASSENT_STAGE_ID: Final = 11


def rule_for(stage_id: int | None) -> StageRule | None:
    """Return the rule for ``stage_id``, or ``None`` if it is not mapped.

    An unmapped id is a normal, visible condition. Callers publish the Bill as
    ``unknown`` and raise a run warning; they never fall back to the stage
    description.
    """
    if stage_id is None:
        return None
    return STAGE_RULES.get(stage_id)


def unmapped_ids(catalogue_stage_ids: frozenset[int] | set[int]) -> tuple[int, ...]:
    """Stage ids published by the API that this table does not classify."""
    return tuple(sorted(set(catalogue_stage_ids) - KNOWN_STAGE_IDS))
