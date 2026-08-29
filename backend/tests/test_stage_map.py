"""The stage table must classify everything the API publishes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bill_pipeline.models import CANONICAL_NODES, PipelineNode
from bill_pipeline.stage_map import (
    KNOWN_STAGE_IDS,
    STAGE_RULES,
    StageCategory,
    rule_for,
    unmapped_ids,
)

CATALOGUE = Path(__file__).parent / "fixtures" / "stages_catalogue.json"


def published_catalogue() -> list[dict[str, Any]]:
    with CATALOGUE.open(encoding="utf-8") as handle:
        payload: dict[str, Any] = json.load(handle)
    items: list[dict[str, Any]] = payload["items"]
    return items


def test_catalogue_fixture_matches_its_advertised_total() -> None:
    with CATALOGUE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["totalResults"] == len(payload["items"]) == 49


def test_every_published_stage_id_is_classified() -> None:
    """No stage the API publishes may be silently omitted from the table.

    This is the test that fails when Parliament adds a stage id. Live
    ingestion keeps working by publishing that Bill as unknown; this failure
    is the prompt to classify it deliberately.
    """
    published = {entry["id"] for entry in published_catalogue()}
    assert unmapped_ids(published) == (), (
        "The Bills API publishes stage ids that bill_pipeline.stage_map does not "
        "classify. Add them to the table and to docs/stage-mapping.md."
    )
    assert published <= KNOWN_STAGE_IDS


@pytest.mark.parametrize("entry", published_catalogue(), ids=lambda e: f"stage-{e['id']}")
def test_each_published_stage_maps_to_exactly_one_outcome(entry: dict[str, Any]) -> None:
    """Table-driven coverage of all 49 currently published stage ids."""
    rule = rule_for(entry["id"])
    assert rule is not None, f"stage {entry['id']} ({entry['name']}) is unclassified"

    if rule.category is StageCategory.DIRECT:
        assert rule.node is not None
        assert rule.node in CANONICAL_NODES
    else:
        # Ancillary and examination stages never carry a node of their own;
        # they anchor to the previous canonical stage at normalisation time.
        assert rule.node is None


def test_table_records_the_source_wording_for_documentation() -> None:
    """docs/stage-mapping.md is generated from these fields."""
    for entry in published_catalogue():
        rule = rule_for(entry["id"])
        assert rule is not None
        assert rule.source_name == entry["name"], (
            f"stage {entry['id']} is recorded as {rule.source_name!r} but the API "
            f"now calls it {entry['name']!r}"
        )
        assert rule.source_house.value == entry["house"].lower()


def test_stage_38_is_classified_with_an_explanatory_note() -> None:
    """Legislative Grand Committee was absent from the original specification.

    It is published by the API but appears in none of the specification's
    mapping tables. Classifying it as ancillary keeps affected Bills on the
    chart instead of dropping them into the unclassified section.
    """
    rule = rule_for(38)
    assert rule is not None
    assert rule.category is StageCategory.ANCILLARY
    assert rule.node is None
    assert "specification" in rule.note


def test_consideration_stages_all_map_to_ping_pong() -> None:
    for stage_id in (12, 13, 39, 40, 42):
        rule = rule_for(stage_id)
        assert rule is not None
        assert rule.node is PipelineNode.PING_PONG


def test_royal_assent_is_its_own_final_node() -> None:
    rule = rule_for(11)
    assert rule is not None
    assert rule.node is PipelineNode.ROYAL_ASSENT
    assert rule.node is not PipelineNode.PING_PONG


def test_unknown_stage_id_has_no_rule() -> None:
    assert rule_for(9999) is None
    assert rule_for(None) is None


def test_no_duplicate_stage_ids_in_the_table() -> None:
    assert len(STAGE_RULES) == len(KNOWN_STAGE_IDS) == 49
