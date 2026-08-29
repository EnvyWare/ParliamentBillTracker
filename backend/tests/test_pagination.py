"""Pagination must never yield a partial session list."""

from __future__ import annotations

from typing import Any

import pytest

from bill_pipeline.parliament_client import MAX_PAGES, PaginationError, ParliamentClient
from conftest import ScriptedHttp

BASE = "https://bills-api.parliament.uk/api/v1"
BILLS = f"{BASE}/Bills"


def items(*ids: int) -> list[dict[str, Any]]:
    return [{"billId": i, "shortTitle": f"Bill {i}"} for i in ids]


def client(pages: list[dict[str, Any]]) -> tuple[ParliamentClient, ScriptedHttp]:
    http = ScriptedHttp({BILLS: pages})
    return ParliamentClient(http=http, base_url=BASE), http  # type: ignore[arg-type]


def test_single_page_completes() -> None:
    api, http = client([{"totalResults": 2, "items": items(1, 2)}])
    assert [b["billId"] for b in api.list_session_bills(40)] == [1, 2]
    assert http.calls[0][1]["Skip"] == 0


def test_multiple_pages_are_concatenated() -> None:
    api, http = client(
        [
            {"totalResults": 5, "items": items(1, 2)},
            {"totalResults": 5, "items": items(3, 4)},
            {"totalResults": 5, "items": items(5)},
        ]
    )
    assert [b["billId"] for b in api.list_session_bills(40)] == [1, 2, 3, 4, 5]
    assert [call[1]["Skip"] for call in http.calls] == [0, 2, 4]


def test_skip_advances_by_items_returned_when_the_server_clamps_the_page() -> None:
    """Take=100 is requested but the server returns 2; Skip must follow reality."""
    api, http = client(
        [
            {"totalResults": 4, "items": items(1, 2)},
            {"totalResults": 4, "items": items(3, 4)},
        ]
    )
    api.list_session_bills(40)
    assert [call[1]["Take"] for call in http.calls] == [100, 100]
    assert [call[1]["Skip"] for call in http.calls] == [0, 2]


def test_empty_page_before_the_total_is_reached_fails() -> None:
    api, _ = client([{"totalResults": 5, "items": items(1, 2)}, {"totalResults": 5, "items": []}])
    with pytest.raises(PaginationError, match="empty page"):
        api.list_session_bills(40)


def test_duplicate_identifier_across_pages_fails() -> None:
    api, _ = client(
        [
            {"totalResults": 4, "items": items(1, 2)},
            {"totalResults": 4, "items": items(2, 3)},
        ]
    )
    with pytest.raises(PaginationError, match="duplicate billId"):
        api.list_session_bills(40)


def test_mismatched_total_fails() -> None:
    api, _ = client([{"totalResults": 9, "items": items(1, 2)}, {"totalResults": 9, "items": []}])
    with pytest.raises(PaginationError):
        api.list_session_bills(40)


def test_total_changing_mid_pagination_fails() -> None:
    api, _ = client(
        [
            {"totalResults": 4, "items": items(1, 2)},
            {"totalResults": 6, "items": items(3, 4)},
        ]
    )
    with pytest.raises(PaginationError, match="totalResults changed"):
        api.list_session_bills(40)


@pytest.mark.parametrize(
    "page",
    [
        {"totalResults": 2, "items": "not a list"},
        {"totalResults": "two", "items": []},
        {"items": []},
        {"totalResults": 1, "items": ["not an object"]},
        {"totalResults": 1, "items": [{"noIdentifier": True}]},
        {"totalResults": -1, "items": []},
    ],
    ids=[
        "items-not-list",
        "total-not-int",
        "no-total",
        "item-not-object",
        "item-no-id",
        "negative",
    ],
)
def test_malformed_pages_fail(page: dict[str, Any]) -> None:
    api, _ = client([page])
    with pytest.raises(PaginationError):
        api.list_session_bills(40)


def test_boolean_total_is_rejected() -> None:
    """True is an int in Python but is not a count."""
    api, _ = client([{"totalResults": True, "items": []}])
    with pytest.raises(PaginationError):
        api.list_session_bills(40)


def test_page_ceiling_stops_a_server_that_never_advances() -> None:
    """A server that keeps serving fresh pages forever is still bounded.

    Each page carries a distinct identifier so the duplicate guard does not
    fire first and the ceiling itself is what stops the walk.
    """
    api, _ = client([{"totalResults": 10_000, "items": items(i)} for i in range(1, MAX_PAGES + 6)])
    with pytest.raises(PaginationError, match="page ceiling"):
        api.list_session_bills(40)


def test_zero_results_is_a_valid_complete_read() -> None:
    api, _ = client([{"totalResults": 0, "items": []}])
    assert api.list_session_bills(40) == []


def test_stage_history_paginates_on_its_own_identifier() -> None:
    url = f"{BASE}/Bills/7/Stages"
    http = ScriptedHttp({url: [{"totalResults": 2, "items": [{"id": 1}, {"id": 2}]}]})
    api = ParliamentClient(http=http, base_url=BASE)  # type: ignore[arg-type]
    assert len(api.get_bill_stages(7)) == 2


def test_canary_requests_a_single_most_recently_updated_bill() -> None:
    http = ScriptedHttp(
        {BILLS: [{"totalResults": 4035, "items": [{"billId": 1, "introducedSessionId": 41}]}]}
    )
    api = ParliamentClient(http=http, base_url=BASE)  # type: ignore[arg-type]
    latest = api.latest_updated_bill()
    assert latest is not None
    assert latest["introducedSessionId"] == 41
    assert http.calls[0][1] == {"Skip": 0, "Take": 1, "SortOrder": "DateUpdatedDescending"}
    # The canary is deliberately not filtered by session.
    assert "Session" not in http.calls[0][1]


def test_canary_tolerates_an_empty_response() -> None:
    http = ScriptedHttp({BILLS: [{"totalResults": 0, "items": []}]})
    api = ParliamentClient(http=http, base_url=BASE)  # type: ignore[arg-type]
    assert api.latest_updated_bill() is None
