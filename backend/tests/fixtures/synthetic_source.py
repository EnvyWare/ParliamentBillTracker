"""Synthetic Bills API responses.

Every Bill, member, party and identifier here is invented. Nothing in this
module is Parliamentary information, so it carries the repository's MIT
licence and can be published as the example snapshot the frontend uses for
local development.

The shapes mirror the real API exactly (verified against the live endpoints on
29 August 2026), including the two identifiers that are easy to confuse:
``currentStage.id`` is the per-Bill occurrence and ``currentStage.stageId`` is
the reusable stage reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

SESSION_ID = 40
SESSION_LABEL = "2026-27"
PREVIOUS_SESSION_ID = 39

#: Fixed so the generated example snapshot is byte-for-byte reproducible.
GENERATED_AT = "2026-08-29T12:00:00Z"
TODAY = date(2026, 8, 29)

BILL_TYPES: list[dict[str, Any]] = [
    {"id": 1, "category": "Public", "name": "Government Bill", "description": "<p>Example.</p>"},
    {
        "id": 2,
        "category": "Public",
        "name": "Private Members' Bill (Starting in the House of Lords)",
        "description": "Example.",
    },
    {"id": 4, "category": "Hybrid", "name": "Hybrid Bill", "description": "Example."},
    {"id": 6, "category": "Private", "name": "Private Bill", "description": "Example."},
    {
        "id": 7,
        "category": "Public",
        "name": "Private Members' Bill (Ballot Bill)",
        "description": "Example.",
    },
]


@dataclass(frozen=True, slots=True)
class StageStep:
    """One stage occurrence in a synthetic Bill's history."""

    stage_id: int
    description: str
    house: str
    abbreviation: str | None = None
    sitting_dates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SyntheticBill:
    bill_id: int
    short_title: str
    bill_type_id: int
    originating_house: str
    current_house: str
    steps: tuple[StageStep, ...]
    long_title: str = "A Bill to make example provision for demonstration purposes."
    former_short_title: str | None = None
    summary: str | None = None
    is_act: bool = False
    is_defeated: bool = False
    bill_withdrawn: str | None = None
    introduced_session_id: int = SESSION_ID
    included_session_ids: tuple[int, ...] = (SESSION_ID,)
    last_update: str = "2026-08-20T09:15:00.1234567"
    sponsors: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    #: Session id applied to every stage occurrence; carry-over Bills override
    #: the earliest steps so anchoring across sessions can be exercised.
    first_steps_in_previous_session: int = 0

    # -- API projections ---------------------------------------------------

    def stage_objects(self) -> list[dict[str, Any]]:
        stages: list[dict[str, Any]] = []
        sitting_id = self.bill_id * 100
        for index, step in enumerate(self.steps):
            occurrence_id = self.bill_id * 1000 + index
            session_id = (
                PREVIOUS_SESSION_ID if index < self.first_steps_in_previous_session else SESSION_ID
            )
            sittings = []
            for day in step.sitting_dates:
                sitting_id += 1
                sittings.append(
                    {
                        "id": sitting_id,
                        "stageId": step.stage_id,
                        "billStageId": occurrence_id,
                        "billId": self.bill_id,
                        "date": f"{day}T00:00:00",
                    }
                )
            stages.append(
                {
                    "id": occurrence_id,
                    "stageId": step.stage_id,
                    "sessionId": session_id,
                    "description": step.description,
                    "abbreviation": step.abbreviation,
                    "house": step.house,
                    "stageSittings": sittings,
                    "sortOrder": index + 1,
                }
            )
        return stages

    def current_stage(self) -> dict[str, Any] | None:
        stages = self.stage_objects()
        return stages[-1] if stages else None

    def list_entry(self) -> dict[str, Any]:
        """The shape returned by ``GET /Bills?Session=...``."""
        return {
            "billId": self.bill_id,
            "shortTitle": self.short_title,
            "formerShortTitle": self.former_short_title,
            "currentHouse": self.current_house,
            "originatingHouse": self.originating_house,
            "lastUpdate": self.last_update,
            "billWithdrawn": self.bill_withdrawn,
            "isDefeated": self.is_defeated,
            "billTypeId": self.bill_type_id,
            "introducedSessionId": self.introduced_session_id,
            "includedSessionIds": list(self.included_session_ids),
            "isAct": self.is_act,
            "currentStage": self.current_stage(),
        }

    def detail(self) -> dict[str, Any]:
        """The shape returned by ``GET /Bills/{id}``."""
        return {
            **self.list_entry(),
            "longTitle": self.long_title,
            "summary": self.summary,
            "sponsors": list(self.sponsors),
            "promoters": [],
            "petitioningPeriod": None,
            "petitionInformation": None,
            "agent": None,
        }


def _sponsor(
    member_id: int, name: str, party: str, house: str, org: str | None = None
) -> dict[str, Any]:
    return {
        "member": {
            "memberId": member_id,
            "name": name,
            "party": party,
            "partyColour": "336699",
            "house": house,
            # Present in the real API and deliberately discarded by normalisation.
            "memberPhoto": f"https://members-api.parliament.uk/api/Members/{member_id}/Thumbnail",
            "memberPage": f"https://members.parliament.uk/member/{member_id}/contact",
            "memberFrom": "Example Constituency",
        },
        "organisation": {"name": org, "url": "https://example.invalid"} if org else None,
        "sortOrder": 1,
    }


# Commons-first stage vocabulary, matching the live catalogue wording.
C1R = StageStep(6, "1st reading", "Commons", "1R")
C2R = StageStep(7, "2nd reading", "Commons", "2R")
CCS = StageStep(8, "Committee stage", "Commons", "CS")
CRS = StageStep(9, "Report stage", "Commons", "RS")
C3R = StageStep(10, "3rd reading", "Commons", "3R")
L1R = StageStep(1, "1st reading", "Lords", "1R")
L2R = StageStep(2, "2nd reading", "Lords", "2R")
LCS = StageStep(3, "Committee stage", "Lords", "CS")
LRS = StageStep(4, "Report stage", "Lords", "RS")
L3R = StageStep(5, "3rd reading", "Lords", "3R")
ROYAL_ASSENT = StageStep(11, "Royal Assent", "Unassigned", "RA")


SYNTHETIC_BILLS: tuple[SyntheticBill, ...] = (
    # -- Commons-first route, one Bill per stage ---------------------------
    SyntheticBill(
        bill_id=9001,
        short_title="Coastal Erosion (Monitoring) Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Commons",
        steps=(StageStep(6, "1st reading", "Commons", "1R", ("2026-08-18",)),),
        long_title="A Bill to make provision about the monitoring of coastal erosion.",
        sponsors=(
            _sponsor(1001, "Rowan Ashfield", "Example Party A", "Commons", "Example Department"),
        ),
        last_update="2026-08-18T14:02:11.7654321",
    ),
    SyntheticBill(
        bill_id=9002,
        short_title="Community Energy Bill",
        bill_type_id=7,
        originating_house="Commons",
        current_house="Commons",
        steps=(C1R, StageStep(7, "2nd reading", "Commons", "2R", ("2026-09-11",))),
        long_title="A Bill to support community-owned energy generation.",
        sponsors=(_sponsor(1002, "Imogen Blackwood", "Example Party B", "Commons"),),
        last_update="2026-08-21T10:30:00.0000000",
    ),
    SyntheticBill(
        bill_id=9003,
        short_title="Digital Identity Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Commons",
        steps=(
            C1R,
            C2R,
            StageStep(8, "Committee stage", "Commons", "CS", ("2026-09-02", "2026-09-03")),
        ),
        long_title="A Bill to make provision about digital identity verification.",
        summary="Establishes a framework for voluntary digital identity credentials.",
        sponsors=(
            _sponsor(1003, "Nadia Okonjo", "Example Party A", "Commons", "Example Department"),
            _sponsor(1004, "Peter Vance", "Example Party A", "Commons"),
        ),
        last_update="2026-08-27T16:45:33.2222222",
    ),
    SyntheticBill(
        bill_id=9004,
        short_title="Health Standards Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Commons",
        steps=(
            C1R,
            C2R,
            CCS,
            StageStep(9, "Report stage", "Commons", "RS", ("2026-09-07", "2026-09-08")),
        ),
        long_title="A Bill to make provision about health and social care standards.",
        sponsors=(
            _sponsor(1005, "Wesley Marchant", "Example Party A", "Commons", "Example Department"),
        ),
        last_update="2026-08-28T18:42:57.9656298",
    ),
    SyntheticBill(
        bill_id=9005,
        short_title="Rural Transport Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Commons",
        steps=(C1R, C2R, CCS, CRS, StageStep(10, "3rd reading", "Commons", "3R", ("2026-09-15",))),
        long_title="A Bill to make provision about rural transport funding.",
        sponsors=(_sponsor(1006, "Adaeze Fairbairn", "Example Party A", "Commons"),),
        last_update="2026-08-26T11:11:11.1111111",
    ),
    SyntheticBill(
        bill_id=9006,
        short_title="Schools Funding Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Lords",
        steps=(
            C1R,
            C2R,
            CCS,
            CRS,
            C3R,
            StageStep(1, "1st reading", "Lords", "1R", ("2026-08-25",)),
        ),
        long_title="A Bill to make provision about the funding of schools.",
        sponsors=(
            _sponsor(1007, "Bridget Calloway", "Example Party A", "Commons", "Example Department"),
        ),
        last_update="2026-08-25T09:00:00.0000000",
    ),
    SyntheticBill(
        bill_id=9007,
        short_title="Water Quality Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Lords",
        steps=(
            C1R,
            C2R,
            CCS,
            CRS,
            C3R,
            L1R,
            StageStep(2, "2nd reading", "Lords", "2R", ("2026-09-09",)),
        ),
        long_title="A Bill to make provision about the quality of inland waters.",
        sponsors=(
            _sponsor(1008, "Steven Reedman", "Example Party A", "Commons", "Example Department"),
        ),
        last_update="2026-08-24T13:20:00.0000000",
    ),
    SyntheticBill(
        bill_id=9008,
        short_title="Employment Rights Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Lords",
        steps=(
            C1R,
            C2R,
            CCS,
            CRS,
            C3R,
            L1R,
            L2R,
            StageStep(3, "Committee stage", "Lords", "CS", ("2026-09-04",)),
        ),
        long_title="A Bill to make provision about employment rights and enforcement.",
        sponsors=(
            _sponsor(1009, "Angela Thorne", "Example Party A", "Commons", "Example Department"),
        ),
        last_update="2026-08-28T08:05:00.0000000",
    ),
    SyntheticBill(
        bill_id=9009,
        short_title="Planning Reform Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Lords",
        steps=(
            C1R,
            C2R,
            CCS,
            CRS,
            C3R,
            L1R,
            L2R,
            LCS,
            StageStep(4, "Report stage", "Lords", "RS", ("2026-09-16",)),
        ),
        long_title="A Bill to reform the planning system.",
        sponsors=(_sponsor(1010, "Matthew Pennington", "Example Party A", "Commons"),),
        last_update="2026-08-22T15:00:00.0000000",
    ),
    SyntheticBill(
        bill_id=9010,
        short_title="Border Security Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Lords",
        steps=(
            C1R,
            C2R,
            CCS,
            CRS,
            C3R,
            L1R,
            L2R,
            LCS,
            LRS,
            StageStep(5, "3rd reading", "Lords", "3R", ("2026-09-18",)),
        ),
        long_title="A Bill to make provision about border security.",
        sponsors=(
            _sponsor(1011, "Yvette Hallam", "Example Party A", "Commons", "Example Department"),
        ),
        last_update="2026-08-23T12:00:00.0000000",
    ),
    # -- Consideration of amendments, third exchange -----------------------
    SyntheticBill(
        bill_id=9011,
        short_title="Data Protection Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Commons",
        steps=(
            C1R,
            C2R,
            CCS,
            CRS,
            C3R,
            L1R,
            L2R,
            LCS,
            LRS,
            L3R,
            StageStep(12, "Consideration of Lords amendments", "Commons", "CLA"),
            StageStep(13, "Consideration of Commons amendments and / or reasons", "Lords", "CCA"),
            StageStep(42, "Consideration of Lords message", "Commons", "CLM", ("2026-09-01",)),
        ),
        long_title="A Bill to make provision about the processing of personal data.",
        summary="Both Houses are exchanging amendments on the final wording.",
        sponsors=(
            _sponsor(1012, "Chi Ravensworth", "Example Party A", "Commons", "Example Department"),
        ),
        last_update="2026-08-29T07:30:00.0000000",
    ),
    # -- Lords-first route -------------------------------------------------
    SyntheticBill(
        bill_id=9012,
        short_title="Arbitration Bill",
        bill_type_id=2,
        originating_house="Lords",
        current_house="Lords",
        steps=(StageStep(1, "1st reading", "Lords", "1R", ("2026-08-19",)),),
        long_title="A Bill to consolidate the law relating to arbitration.",
        sponsors=(_sponsor(1013, "Lord Example of Westhaven", "Crossbench", "Lords"),),
        last_update="2026-08-19T17:00:00.0000000",
    ),
    SyntheticBill(
        bill_id=9013,
        short_title="Heritage Railways Bill",
        bill_type_id=2,
        originating_house="Lords",
        current_house="Lords",
        steps=(L1R, StageStep(2, "2nd reading", "Lords", "2R", ("2026-09-12",))),
        long_title="A Bill to make provision about heritage railway operations.",
        sponsors=(_sponsor(1014, "Baroness Example of Marlow", "Example Party B", "Lords"),),
        last_update="2026-08-20T11:00:00.0000000",
    ),
    SyntheticBill(
        bill_id=9014,
        short_title="Museums and Galleries Bill",
        bill_type_id=2,
        originating_house="Lords",
        current_house="Lords",
        steps=(L1R, L2R, StageStep(3, "Committee stage", "Lords", "CS", ("2026-09-05",))),
        long_title="A Bill to make provision about the governance of museums and galleries.",
        sponsors=(_sponsor(1015, "Lord Example of Aldergate", "Crossbench", "Lords"),),
        last_update="2026-08-26T14:30:00.0000000",
    ),
    SyntheticBill(
        bill_id=9015,
        short_title="Statute Law Revision Bill",
        bill_type_id=2,
        originating_house="Lords",
        current_house="Commons",
        steps=(
            L1R,
            L2R,
            LCS,
            LRS,
            L3R,
            StageStep(6, "1st reading", "Commons", "1R", ("2026-08-27",)),
        ),
        long_title="A Bill to repeal enactments that are no longer of practical utility.",
        sponsors=(_sponsor(1016, "Lord Example of Fenwick", "Crossbench", "Lords"),),
        last_update="2026-08-27T10:00:00.0000000",
    ),
    SyntheticBill(
        bill_id=9016,
        short_title="Charities Regulation Bill",
        bill_type_id=2,
        originating_house="Lords",
        current_house="Commons",
        steps=(
            L1R,
            L2R,
            LCS,
            LRS,
            L3R,
            C1R,
            StageStep(7, "2nd reading", "Commons", "2R", ("2026-09-19",)),
        ),
        long_title="A Bill to make provision about the regulation of charities.",
        sponsors=(_sponsor(1017, "Baroness Example of Thurloe", "Example Party A", "Lords"),),
        last_update="2026-08-21T16:00:00.0000000",
    ),
    # -- Carry-over anchoring back across a session boundary ---------------
    SyntheticBill(
        bill_id=9017,
        short_title="Infrastructure (Delivery) Bill",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Commons",
        steps=(
            C1R,
            C2R,
            CCS,
            StageStep(18, "Carry-over motion", "Commons", "CO", ("2026-08-15",)),
        ),
        long_title="A Bill to make provision about the delivery of national infrastructure.",
        former_short_title="National Infrastructure Bill",
        introduced_session_id=PREVIOUS_SESSION_ID,
        included_session_ids=(PREVIOUS_SESSION_ID, SESSION_ID),
        first_steps_in_previous_session=3,
        sponsors=(
            _sponsor(1018, "Louise Kettering", "Example Party A", "Commons", "Example Department"),
        ),
        last_update="2026-08-15T09:45:00.0000000",
    ),
    # -- Private Bill with no canonical predecessor -> special procedure ----
    SyntheticBill(
        bill_id=9018,
        short_title="Westhaven Harbour Bill",
        bill_type_id=6,
        originating_house="Lords",
        current_house="Lords",
        steps=(
            StageStep(
                41,
                "Examination for compliance with Standing Orders",
                "Unassigned",
                "EX",
                ("2026-09-10",),
            ),
        ),
        long_title="A Bill to confer powers on the Westhaven Harbour Authority.",
        sponsors=(),
        last_update="2026-08-14T10:00:00.0000000",
    ),
    # -- Stage id this build does not classify -----------------------------
    SyntheticBill(
        bill_id=9019,
        short_title="Example Procedure Bill",
        bill_type_id=4,
        originating_house="Commons",
        current_house="Commons",
        steps=(
            C1R,
            StageStep(
                9999, "A stage introduced after this build", "Commons", "NEW", ("2026-09-20",)
            ),
        ),
        long_title="A Bill used to demonstrate an unrecognised stage id.",
        sponsors=(),
        last_update="2026-08-13T10:00:00.0000000",
    ),
    # -- Unassigned originating House --------------------------------------
    SyntheticBill(
        bill_id=9020,
        short_title="Unattributed Origin Bill",
        bill_type_id=4,
        originating_house="Unassigned",
        current_house="Unassigned",
        steps=(StageStep(6, "1st reading", "Commons", "1R", ("2026-08-12",)),),
        long_title="A Bill whose originating House is not stated by the source.",
        sponsors=(),
        last_update="2026-08-12T10:00:00.0000000",
    ),
    # -- Concluded Bills ---------------------------------------------------
    SyntheticBill(
        bill_id=9021,
        short_title="Finance Act 2026",
        bill_type_id=1,
        originating_house="Commons",
        current_house="Commons",
        steps=(
            C1R,
            C2R,
            CCS,
            CRS,
            C3R,
            L1R,
            L2R,
            LCS,
            LRS,
            L3R,
            StageStep(11, "Royal Assent", "Unassigned", "RA", ("2026-07-30",)),
        ),
        long_title="An Act to grant certain duties and to amend the law relating to the public revenue.",
        is_act=True,
        sponsors=(
            _sponsor(1019, "Rachel Enderby", "Example Party A", "Commons", "Example Department"),
        ),
        last_update="2026-07-30T15:00:00.0000000",
    ),
    SyntheticBill(
        bill_id=9022,
        short_title="Small Business Support Bill",
        bill_type_id=7,
        originating_house="Commons",
        current_house="Commons",
        steps=(C1R, C2R, CCS, ROYAL_ASSENT),
        long_title="An Act to make provision about support for small businesses.",
        is_act=True,
        sponsors=(_sponsor(1020, "Kwame Latimer", "Example Party B", "Commons"),),
        last_update="2026-06-11T15:00:00.0000000",
    ),
    SyntheticBill(
        bill_id=9023,
        short_title="Local Referendums Bill",
        bill_type_id=7,
        originating_house="Commons",
        current_house="Commons",
        steps=(C1R, StageStep(7, "2nd reading", "Commons", "2R", ("2026-05-22",))),
        long_title="A Bill to make provision for local referendums.",
        bill_withdrawn="2026-06-02T00:00:00",
        sponsors=(_sponsor(1021, "Priya Nandakumar", "Example Party B", "Commons"),),
        last_update="2026-06-02T12:00:00.0000000",
    ),
    SyntheticBill(
        bill_id=9024,
        short_title="Fixed Odds Betting Bill",
        bill_type_id=7,
        originating_house="Lords",
        current_house="Lords",
        steps=(L1R, StageStep(2, "2nd reading", "Lords", "2R", ("2026-04-17",))),
        long_title="A Bill to restrict fixed odds betting terminals.",
        is_defeated=True,
        sponsors=(_sponsor(1022, "Lord Example of Brambleton", "Crossbench", "Lords"),),
        last_update="2026-04-17T19:00:00.0000000",
    ),
)


def bills_list() -> list[dict[str, Any]]:
    """``GET /Bills?Session=40`` items, in the API's title-ascending order."""
    return sorted((bill.list_entry() for bill in SYNTHETIC_BILLS), key=lambda b: b["shortTitle"])


def details_by_id() -> dict[int, dict[str, Any]]:
    return {bill.bill_id: bill.detail() for bill in SYNTHETIC_BILLS}


def stages_by_id() -> dict[int, list[dict[str, Any]]]:
    return {bill.bill_id: bill.stage_objects() for bill in SYNTHETIC_BILLS}


def bill_types() -> list[dict[str, Any]]:
    return [dict(entry) for entry in BILL_TYPES]
