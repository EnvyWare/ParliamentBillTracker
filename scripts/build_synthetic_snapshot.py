#!/usr/bin/env python3
"""Generate ``frontend/public/data/current.json`` from synthetic source data.

The checked-in snapshot exists so the frontend runs locally with no AWS
account and no internet access. It is built by pushing invented Bills through
the real normalisation and assembly code, so it can never drift from the
published contract, and it is marked ``synthetic`` so the running application
labels it as example data rather than presenting it as live Parliamentary
information.

Deterministic by construction: the generated timestamp and the ingestion date
are both fixed constants, so re-running this produces an identical file.

Usage::

    python scripts/build_synthetic_snapshot.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "backend" / "tests" / "fixtures"))

from bill_pipeline.config import Config  # noqa: E402
from bill_pipeline.models import BillType, SnapshotWarning, WarningCode  # noqa: E402
from bill_pipeline.normalise import normalise_bill  # noqa: E402
from bill_pipeline.snapshot import build_snapshot, validate_snapshot  # noqa: E402

import synthetic_source as synthetic  # noqa: E402  isort:skip

OUTPUT = REPO_ROOT / "frontend" / "public" / "data" / "current.json"


def example_config() -> Config:
    return Config(
        data_bucket="example-bucket",
        current_key="data/current.json",
        snapshot_prefix="archive/snapshots/",
        bills_api_base="https://bills-api.parliament.uk/api/v1",
        parliament_session_id=synthetic.SESSION_ID,
        parliament_session_label=synthetic.SESSION_LABEL,
        refresh_interval_minutes=30,
        http_timeout_seconds=15.0,
        max_concurrent_requests=5,
        full_reconcile_after_days=7,
        schema_version=1,
        log_level="INFO",
        repository_url="https://github.com/EnvyWare/ParliamentBillTracker",
    )


def build() -> dict[str, object]:
    types = {
        entry["id"]: BillType(
            id=entry["id"], name=str(entry["name"]), category=str(entry["category"])
        )
        for entry in synthetic.bill_types()
    }
    details = synthetic.details_by_id()
    histories = synthetic.stages_by_id()

    bills = [
        normalise_bill(
            summary_raw=entry,
            detail_raw=details[entry["billId"]],
            stages_raw=histories[entry["billId"]],
            bill_types=types,
            session_id=synthetic.SESSION_ID,
            today=synthetic.TODAY,
        ).to_dict()
        for entry in synthetic.bills_list()
    ]

    warnings = [
        SnapshotWarning(
            code="synthetic_example_data",
            message=(
                "This is example data generated for local development. It does not "
                "describe any real Bill before the UK Parliament."
            ),
            severity="info",
        )
    ]
    unknown_stage_bills = tuple(
        sorted(
            int(bill["id"])
            for bill in bills
            if WarningCode.UNKNOWN_STAGE_ID.value in bill["warnings"]
        )
    )
    if unknown_stage_bills:
        warnings.append(
            SnapshotWarning(
                code=WarningCode.UNKNOWN_STAGE_ID,
                message=(
                    "Some Bills are at a stage this build does not recognise and are "
                    "shown as unclassified rather than being placed by guesswork."
                ),
                severity="info",
                bill_ids=unknown_stage_bills,
            )
        )

    generated = datetime.strptime(synthetic.GENERATED_AT, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    document = build_snapshot(
        bills=bills,
        config=example_config(),
        generated_at=generated,
        last_full_reconciliation_at=generated,
        warnings=warnings,
        synthetic=True,
    )
    validate_snapshot(document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the checked-in file differs from freshly generated output.",
    )
    args = parser.parse_args()

    document = build()
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if not OUTPUT.is_file():
            print(f"{OUTPUT} is missing; run 'make fixtures'", file=sys.stderr)
            return 1
        if OUTPUT.read_text(encoding="utf-8") != rendered:
            print(
                f"{OUTPUT} is out of date with scripts/build_synthetic_snapshot.py; "
                "run 'make fixtures'",
                file=sys.stderr,
            )
            return 1
        print(f"{OUTPUT.relative_to(REPO_ROOT)} is up to date")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    counts = document["counts"]
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
