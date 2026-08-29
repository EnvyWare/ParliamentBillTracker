"""Typed access to the UK Parliament Bills API.

Pagination is implemented exactly once here and reused by every paged
endpoint. The rules are deliberately strict: a partial session list must never
reach the published snapshot, so anything ambiguous is an error rather than a
silently short result.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from .http_client import HttpClient

PAGE_SIZE: Final = 100

#: A session list of a few hundred Bills needs a handful of pages. This ceiling
#: exists only to stop a server that never advances from looping forever.
MAX_PAGES: Final = 200


class PaginationError(RuntimeError):
    """The paged source response was incomplete, inconsistent or malformed."""


@dataclass(frozen=True, slots=True)
class ParliamentClient:
    """Read-only client for the endpoints this project needs."""

    http: HttpClient
    base_url: str

    # -- paged endpoints ---------------------------------------------------

    def list_session_bills(self, session_id: int) -> list[dict[str, Any]]:
        """Every Bill in one session, in a stable order."""
        return self.paginate(
            "/Bills",
            {"Session": session_id, "SortOrder": "TitleAscending"},
            id_key="billId",
        )

    def list_bill_types(self) -> list[dict[str, Any]]:
        return self.paginate("/BillTypes", {}, id_key="id")

    def list_stages(self) -> list[dict[str, Any]]:
        """The published stage catalogue, used to detect unmapped stage ids."""
        return self.paginate("/Stages", {}, id_key="id")

    def get_bill_stages(self, bill_id: int) -> list[dict[str, Any]]:
        return self.paginate(f"/Bills/{bill_id}/Stages", {}, id_key="id")

    # -- single-object endpoints -------------------------------------------

    def get_bill(self, bill_id: int) -> dict[str, Any]:
        return self.http.get_json(f"{self.base_url}/Bills/{bill_id}")

    def latest_updated_bill(self) -> dict[str, Any] | None:
        """The single most recently updated Bill across all sessions.

        Used as a session-rollover canary. Deliberately unfiltered by session.
        """
        page = self.http.get_json(
            f"{self.base_url}/Bills",
            {"Skip": 0, "Take": 1, "SortOrder": "DateUpdatedDescending"},
        )
        items = page.get("items")
        if not isinstance(items, list) or not items:
            return None
        first = items[0]
        return first if isinstance(first, dict) else None

    # -- pagination --------------------------------------------------------

    def paginate(
        self,
        path: str,
        params: Mapping[str, object],
        *,
        id_key: str,
        take: int = PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        """Walk a paged endpoint to completion or fail loudly.

        ``Skip`` advances by the number of items actually returned rather than
        by ``take``, because the server is free to clamp the requested page
        size.
        """
        url = f"{self.base_url}{path}"
        collected: list[dict[str, Any]] = []
        seen: set[object] = set()
        expected_total: int | None = None
        skip = 0

        for _ in range(MAX_PAGES):
            page = self.http.get_json(url, {**params, "Skip": skip, "Take": take})
            items = page.get("items")
            total = page.get("totalResults")

            if not isinstance(items, list):
                raise PaginationError(f"{url}: 'items' was {type(items).__name__}, expected a list")
            if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                raise PaginationError(f"{url}: 'totalResults' was {total!r}, expected a count")

            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise PaginationError(
                    f"{url}: totalResults changed from {expected_total} to {total} mid-pagination"
                )

            if not items:
                if len(collected) < expected_total:
                    raise PaginationError(
                        f"{url}: empty page at Skip={skip} with only "
                        f"{len(collected)} of {expected_total} results collected"
                    )
                break

            for item in items:
                if not isinstance(item, dict):
                    raise PaginationError(
                        f"{url}: page item was {type(item).__name__}, expected an object"
                    )
                identifier = item.get(id_key)
                if not isinstance(identifier, int | str):
                    raise PaginationError(
                        f"{url}: page item is missing a usable {id_key!r} identifier"
                    )
                if identifier in seen:
                    raise PaginationError(f"{url}: duplicate {id_key} {identifier!r} across pages")
                seen.add(identifier)
                collected.append(item)

            skip += len(items)
            if len(collected) >= expected_total:
                break
        else:
            raise PaginationError(f"{url}: exceeded the {MAX_PAGES}-page ceiling")

        assert expected_total is not None
        if len(collected) != expected_total or len(seen) != expected_total:
            raise PaginationError(
                f"{url}: collected {len(collected)} unique results but the API "
                f"advertised {expected_total}"
            )
        return collected
