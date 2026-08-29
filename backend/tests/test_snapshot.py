"""Snapshot assembly, hashing, schema contract and publication guards."""

from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import synthetic_source as synthetic

from bill_pipeline.config import Config
from bill_pipeline.models import BillType, SnapshotWarning
from bill_pipeline.normalise import normalise_bill
from bill_pipeline.snapshot import (
    MIN_RETAINED_FRACTION,
    PublicationGuardError,
    archive_key,
    build_snapshot,
    compute_data_hash,
    count_bills,
    detect_session_rollover,
    evaluate_publication_guards,
    is_special_or_unclassified,
    is_stale,
    refresh_derived_fields,
    sort_bills,
    utc_timestamp,
    validate_snapshot,
)
from bill_pipeline.validation import SchemaValidationError, iter_errors

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_SNAPSHOT = REPO_ROOT / "frontend" / "public" / "data" / "current.json"

NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def bills(bill_types: dict[int, BillType]) -> list[dict[str, Any]]:
    details = synthetic.details_by_id()
    histories = synthetic.stages_by_id()
    return [
        normalise_bill(
            summary_raw=entry,
            detail_raw=details[entry["billId"]],
            stages_raw=histories[entry["billId"]],
            bill_types=bill_types,
            session_id=40,
            today=date(2026, 8, 29),
        ).to_dict()
        for entry in synthetic.bills_list()
    ]


@pytest.fixture
def document(bills: list[dict[str, Any]], config: Config) -> dict[str, Any]:
    return build_snapshot(
        bills=bills, config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_snapshot_validates_against_the_published_schema(document: dict[str, Any]) -> None:
    validate_snapshot(document)


def test_checked_in_example_snapshot_validates(schema: dict[str, Any]) -> None:
    with EXAMPLE_SNAPSHOT.open(encoding="utf-8") as handle:
        example = json.load(handle)
    assert iter_errors(example, schema) == []
    assert example["synthetic"] is True
    assert example["status"] == "synthetic"


def test_bundled_validator_agrees_with_the_jsonschema_library(
    document: dict[str, Any], schema: dict[str, Any]
) -> None:
    """The Lambda ships a small validator; it must not be more permissive.

    Both validators are run over the same valid document and over a set of
    deliberately broken ones. They have to reach the same verdict every time,
    otherwise the in-Lambda publication guard is weaker than the contract.
    """
    jsonschema.validate(document, schema)
    assert iter_errors(document, schema) == []

    def broken(mutate: Any) -> dict[str, Any]:
        copied = copy.deepcopy(document)
        mutate(copied)
        return copied

    mutations = [
        lambda d: d.__setitem__("schemaVersion", 2),
        lambda d: d.__setitem__("status", "partial"),
        lambda d: d.__setitem__("dataHash", "not-a-hash"),
        lambda d: d.__setitem__("generatedAt", "2026-08-29 12:00:00"),
        lambda d: d.__setitem__("unexpectedField", True),
        lambda d: d["bills"][0].__setitem__("pipelineNode", "commons_fourth_reading"),
        lambda d: d["bills"][0].__setitem__("status", "lapsed"),
        lambda d: d["bills"][0].__setitem__("originatingHouse", "Commons"),
        lambda d: d["bills"][0].__setitem__("id", "9001"),
        lambda d: d["bills"][0].pop("warnings"),
        lambda d: d["bills"][0]["stage"].__setitem__("nextSittingDate", "07/09/2026"),
        lambda d: d["counts"].__setitem__("total", -1),
        lambda d: d["source"].pop("attribution"),
        lambda d: d["bills"][0].__setitem__("pingPongExchangeNumber", 0),
    ]

    for index, mutate in enumerate(mutations):
        candidate = broken(mutate)
        ours = iter_errors(candidate, schema)
        try:
            jsonschema.validate(candidate, schema)
            theirs_failed = False
        except jsonschema.ValidationError:
            theirs_failed = True
        assert bool(ours) == theirs_failed, (
            f"mutation {index} disagreed: bundled validator errors={ours}, "
            f"jsonschema rejected={theirs_failed}"
        )


def test_source_block_carries_the_open_parliament_attribution(document: dict[str, Any]) -> None:
    source = document["source"]
    assert source["attribution"] == (
        "Contains Parliamentary information licensed under the Open Parliament Licence v3.0."
    )
    assert source["licenceUrl"].startswith("https://www.parliament.uk/")
    assert source["sessionId"] == 40
    assert source["sessionLabel"] == "2026-27"


def test_generated_timestamps_are_the_only_ones_labelled_utc(document: dict[str, Any]) -> None:
    assert document["generatedAt"].endswith("Z")
    for bill in document["bills"]:
        if bill["sourceLastUpdate"]:
            assert not bill["sourceLastUpdate"].endswith("Z")
        for sitting in bill["stage"]["sittings"] if bill["stage"] else []:
            if sitting["sourceDateTime"]:
                assert not sitting["sourceDateTime"].endswith("Z")


def test_utc_timestamp_refuses_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        utc_timestamp(datetime(2026, 8, 29, 12, 0, 0))  # noqa: DTZ001


# ---------------------------------------------------------------------------
# Ordering and counts
# ---------------------------------------------------------------------------


def test_bills_are_sorted_by_case_folded_title_then_id() -> None:
    ordered = sort_bills(
        [
            {"id": 3, "title": "beta Bill"},
            {"id": 1, "title": "Alpha Bill"},
            {"id": 2, "title": "Alpha Bill"},
        ]
    )
    assert [b["id"] for b in ordered] == [1, 2, 3]


def test_counts_match_the_published_records(document: dict[str, Any]) -> None:
    counts = document["counts"]
    bills = document["bills"]
    assert counts["total"] == len(bills)
    assert counts["active"] == sum(1 for b in bills if b["status"] == "active")
    assert counts["enacted"] == sum(1 for b in bills if b["status"] == "enacted")
    assert counts["withdrawn"] == sum(1 for b in bills if b["status"] == "withdrawn")
    assert counts["failed"] == sum(1 for b in bills if b["status"] == "failed")
    assert (
        counts["total"]
        == counts["active"]
        + counts["enacted"]
        + counts["withdrawn"]
        + counts["failed"]
        + counts["unknown"]
    )


def test_every_bill_is_placed_exactly_once(document: dict[str, Any]) -> None:
    """A Bill is on a route, in the special section, or concluded. Never twice.

    Enacted Bills sit at Royal Assent, which is the last step of both routes,
    so only withdrawn and defeated Bills form the concluded section.
    """
    for bill in document["bills"]:
        concluded = bill["status"] in {"withdrawn", "failed"}
        special = is_special_or_unclassified(bill)
        on_route = not concluded and not special
        assert sum([concluded, special, on_route]) == 1


def test_acts_are_placed_at_royal_assent_not_in_a_separate_bucket(
    document: dict[str, Any],
) -> None:
    acts = [b for b in document["bills"] if b["status"] == "enacted"]
    assert acts
    for act in acts:
        assert act["pipelineNode"] == "royal_assent"
        assert is_special_or_unclassified(act) is False


def test_special_count_covers_unknown_special_and_unassigned_origin(
    document: dict[str, Any],
) -> None:
    special = [b for b in document["bills"] if is_special_or_unclassified(b)]
    assert document["counts"]["specialOrUnclassified"] == len(special)
    nodes = {b["pipelineNode"] for b in special}
    assert "special_procedure" in nodes
    assert "unknown" in nodes
    assert any(b["originatingHouse"] == "unassigned" for b in special)


def test_terminal_bills_are_never_counted_as_special() -> None:
    enacted = {"status": "enacted", "pipelineNode": "royal_assent", "originatingHouse": "commons"}
    assert is_special_or_unclassified(enacted) is False


def test_counts_helper_matches_the_document(bills: list[dict[str, Any]]) -> None:
    counts = count_bills(bills)
    assert counts.total == len(bills)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def test_hash_is_stable_when_only_generated_timestamps_differ(
    bills: list[dict[str, Any]], config: Config
) -> None:
    first = build_snapshot(
        bills=bills, config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )
    later = build_snapshot(
        bills=bills,
        config=config,
        generated_at=NOW.replace(hour=18),
        last_full_reconciliation_at=NOW.replace(day=28),
    )
    assert first["generatedAt"] != later["generatedAt"]
    assert first["dataHash"] == later["dataHash"]


def test_hash_ignores_the_clock_derived_next_sitting_date(document: dict[str, Any]) -> None:
    """nextSittingDate moves with the calendar, not with Parliament."""
    mutated = copy.deepcopy(document)
    for bill in mutated["bills"]:
        if bill["stage"]:
            bill["stage"]["nextSittingDate"] = "2099-01-01"
    assert compute_data_hash(mutated) == compute_data_hash(document)


def test_hash_changes_when_source_content_changes(document: dict[str, Any]) -> None:
    mutated = copy.deepcopy(document)
    mutated["bills"][0]["title"] = "A Different Title"
    assert compute_data_hash(mutated) != compute_data_hash(document)


def test_hash_changes_when_a_sitting_changes(document: dict[str, Any]) -> None:
    mutated = copy.deepcopy(document)
    target = next(b for b in mutated["bills"] if b["stage"] and b["stage"]["sittings"])
    target["stage"]["sittings"][0]["date"] = "2027-01-01"
    assert compute_data_hash(mutated) != compute_data_hash(document)


def test_archive_key_is_content_addressed() -> None:
    key = archive_key("archive/snapshots/", "sha256:" + "ab" * 32)
    assert key == "archive/snapshots/" + "ab" * 32 + ".json"


def test_duplicate_invocation_produces_the_same_archive_key(
    bills: list[dict[str, Any]], config: Config
) -> None:
    """At-least-once delivery must not create a second archive object."""
    first = build_snapshot(
        bills=bills, config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )
    second = build_snapshot(
        bills=bills,
        config=config,
        generated_at=NOW.replace(minute=30),
        last_full_reconciliation_at=NOW,
    )
    assert archive_key("archive/snapshots/", first["dataHash"]) == archive_key(
        "archive/snapshots/", second["dataHash"]
    )


# ---------------------------------------------------------------------------
# Publication guards
# ---------------------------------------------------------------------------


def test_valid_snapshot_passes_the_guards(document: dict[str, Any], schema: dict[str, Any]) -> None:
    evaluate_publication_guards(document=document, previous=document, session_id=40, schema=schema)


def test_empty_result_is_refused(config: Config, schema: dict[str, Any]) -> None:
    empty = build_snapshot(
        bills=[], config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )
    with pytest.raises(PublicationGuardError, match="empty result"):
        evaluate_publication_guards(document=empty, previous=None, session_id=40, schema=schema)


def test_catastrophic_shrink_is_refused(
    bills: list[dict[str, Any]], config: Config, schema: dict[str, Any]
) -> None:
    previous = build_snapshot(
        bills=bills, config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )
    survivors = bills[: int(len(bills) * MIN_RETAINED_FRACTION) - 1]
    shrunk = build_snapshot(
        bills=survivors, config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )
    with pytest.raises(PublicationGuardError, match="fell from"):
        evaluate_publication_guards(
            document=shrunk, previous=previous, session_id=40, schema=schema
        )


def test_a_modest_drop_is_allowed(
    bills: list[dict[str, Any]], config: Config, schema: dict[str, Any]
) -> None:
    previous = build_snapshot(
        bills=bills, config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )
    smaller = build_snapshot(
        bills=bills[:-1], config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )
    evaluate_publication_guards(document=smaller, previous=previous, session_id=40, schema=schema)


def test_shrink_guard_does_not_fire_across_a_session_change(
    bills: list[dict[str, Any]], config: Config, schema: dict[str, Any]
) -> None:
    previous = build_snapshot(
        bills=bills, config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )
    previous["source"]["sessionId"] = 39
    fresh = build_snapshot(
        bills=bills[:1], config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )
    evaluate_publication_guards(document=fresh, previous=previous, session_id=40, schema=schema)


def test_incompletely_normalised_bill_is_refused(
    bills: list[dict[str, Any]], config: Config, schema: dict[str, Any]
) -> None:
    partial = copy.deepcopy(bills)
    partial[0]["detailsComplete"] = False
    document = build_snapshot(
        bills=partial, config=config, generated_at=NOW, last_full_reconciliation_at=NOW
    )
    with pytest.raises(PublicationGuardError, match="could not be fully"):
        evaluate_publication_guards(document=document, previous=None, session_id=40, schema=schema)


def test_schema_failure_is_refused(document: dict[str, Any], schema: dict[str, Any]) -> None:
    broken = copy.deepcopy(document)
    broken["bills"][0]["pipelineNode"] = "not_a_node"
    with pytest.raises(PublicationGuardError):
        evaluate_publication_guards(document=broken, previous=None, session_id=40, schema=schema)


def test_unknown_stages_do_not_block_publication(
    document: dict[str, Any], schema: dict[str, Any]
) -> None:
    """An unrecognised stage is normal input, not a guard failure."""
    assert any(b["pipelineNode"] == "unknown" for b in document["bills"])
    evaluate_publication_guards(document=document, previous=None, session_id=40, schema=schema)


# ---------------------------------------------------------------------------
# Session rollover canary
# ---------------------------------------------------------------------------


def test_canary_detects_a_newer_session() -> None:
    assert detect_session_rollover({"introducedSessionId": 41}, 40) == 41


def test_canary_is_quiet_for_the_configured_session() -> None:
    assert detect_session_rollover({"introducedSessionId": 40}, 40) is None
    assert detect_session_rollover({"introducedSessionId": 39}, 40) is None
    assert detect_session_rollover(None, 40) is None
    assert detect_session_rollover({}, 40) is None


# ---------------------------------------------------------------------------
# Freshness and cache refresh
# ---------------------------------------------------------------------------


def test_is_stale_uses_the_generated_timestamp() -> None:
    document = {"generatedAt": "2026-08-29T09:00:00Z"}
    assert is_stale(document, NOW, max_age_minutes=180) is False
    assert is_stale(document, NOW, max_age_minutes=120) is True
    assert is_stale({"generatedAt": "nonsense"}, NOW, 180) is True
    assert is_stale({}, NOW, 180) is True


def test_refresh_derived_fields_recomputes_next_sitting() -> None:
    """A cached Bill carried forward still needs its next sitting recalculated."""
    bill = {
        "stage": {
            "sittings": [
                {"id": 1, "date": "2026-08-01"},
                {"id": 2, "date": "2026-09-07"},
            ],
            "nextSittingDate": "2026-08-01",
        }
    }
    refreshed = refresh_derived_fields(bill, date(2026, 8, 29))
    assert refreshed["stage"]["nextSittingDate"] == "2026-09-07"


def test_refresh_derived_fields_clears_a_fully_past_schedule() -> None:
    bill = {
        "stage": {"sittings": [{"id": 1, "date": "2026-01-01"}], "nextSittingDate": "2026-01-01"}
    }
    assert refresh_derived_fields(bill, date(2026, 8, 29))["stage"]["nextSittingDate"] is None


def test_refresh_derived_fields_tolerates_a_missing_stage() -> None:
    assert refresh_derived_fields({"stage": None}, date(2026, 8, 29)) == {"stage": None}


def test_validation_error_message_lists_the_problems(schema: dict[str, Any]) -> None:
    with pytest.raises(SchemaValidationError) as excinfo:
        validate_snapshot({"schemaVersion": 1}, schema)
    assert excinfo.value.errors


def test_snapshot_warnings_are_published_for_the_ui(
    bills: list[dict[str, Any]], config: Config
) -> None:
    document = build_snapshot(
        bills=bills,
        config=config,
        generated_at=NOW,
        last_full_reconciliation_at=NOW,
        warnings=[SnapshotWarning(code="example", message="Example warning", severity="info")],
    )
    validate_snapshot(document)
    assert document["warnings"][0]["code"] == "example"
