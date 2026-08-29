#!/usr/bin/env python3
"""Validate a published snapshot against the schema, and check its age.

Used by the post-deployment smoke test and by the deployment workflow. It
reuses the same validator the ingestion function runs before publishing, so a
snapshot that passes here passed the identical check on the way out.

Usage::

    python scripts/validate_snapshot.py current.json [--max-age-minutes 180]
    curl -s https://example.com/data/current.json | python scripts/validate_snapshot.py -
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from bill_pipeline.validation import (  # noqa: E402
    SchemaValidationError,
    load_schema,
    validate,
)

SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.schema.json"


def read_document(source: str) -> object:
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Path to the snapshot, or - to read standard input.")
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=None,
        help="Fail if the snapshot was generated longer ago than this.",
    )
    parser.add_argument(
        "--expect-session",
        type=int,
        default=None,
        help="Fail if the snapshot is not for this session id.",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Permit the synthetic example snapshot. A deployment should not.",
    )
    args = parser.parse_args()

    try:
        document = read_document(args.source)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read the snapshot: {exc}", file=sys.stderr)
        return 1

    try:
        validate(document, load_schema(SCHEMA_PATH))
    except SchemaValidationError as exc:
        print(f"Schema validation failed: {exc}", file=sys.stderr)
        return 1

    assert isinstance(document, dict)
    counts = document["counts"]
    source_block = document["source"]

    if document.get("synthetic") and not args.allow_synthetic:
        print(
            "This is the synthetic example snapshot, not live data. "
            "The ingestion function has probably not run yet.",
            file=sys.stderr,
        )
        return 1

    if args.expect_session is not None and source_block["sessionId"] != args.expect_session:
        print(
            f"Snapshot is for session {source_block['sessionId']}, "
            f"expected {args.expect_session}.",
            file=sys.stderr,
        )
        return 1

    generated_raw = document["generatedAt"]
    generated = datetime.strptime(generated_raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    age_minutes = (datetime.now(tz=UTC) - generated).total_seconds() / 60

    if args.max_age_minutes is not None and age_minutes > args.max_age_minutes:
        print(
            f"Snapshot is {age_minutes:.0f} minutes old, "
            f"which is beyond the {args.max_age_minutes}-minute threshold.",
            file=sys.stderr,
        )
        return 1

    warnings = document.get("warnings", [])
    print(
        f"Snapshot valid: session {source_block['sessionId']} "
        f"({source_block['sessionLabel']}), {counts['total']} Bills "
        f"({counts['active']} in progress, {counts['enacted']} Acts, "
        f"{counts['specialOrUnclassified']} unclassified), "
        f"generated {age_minutes:.0f} minutes ago."
    )
    for warning in warnings:
        print(f"  warning [{warning['severity']}] {warning['code']}: {warning['message']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
