#!/usr/bin/env python3
"""Run a real ingestion against the live Bills API, publishing nothing.

This exercises the whole pipeline - pagination, retries, normalisation, the
publication guards and schema validation - against real Parliamentary data,
and reports what it found. Storage is in memory, so nothing is written to S3
and nothing is served.

It is deliberately polite to Parliament's public API: the same bounded
concurrency and descriptive User-Agent the deployed function uses.

Usage::

    python scripts/live_smoke.py
    python scripts/live_smoke.py --session 40 --label 2026-27
    python scripts/live_smoke.py --out snapshot.json
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from bill_pipeline.config import DEFAULT_BILLS_API_BASE, Config  # noqa: E402
from bill_pipeline.handler import run_ingestion  # noqa: E402
from bill_pipeline.http_client import HttpClient, StdlibTransport  # noqa: E402
from bill_pipeline.parliament_client import ParliamentClient  # noqa: E402
from bill_pipeline.storage import SnapshotStorage  # noqa: E402


class NoSuchKey(Exception):
    """Shaped like a botocore ClientError, which is what storage expects."""

    def __init__(self) -> None:
        super().__init__("NoSuchKey")
        self.response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }


class InMemoryS3:
    """Stands in for S3. Nothing leaves this process."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        if key not in self.objects:
            raise NoSuchKey
        return {"Body": io.BytesIO(self.objects[key])}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["Key"] not in self.objects:
            raise NoSuchKey
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=int, default=40, help="Session id to fetch.")
    parser.add_argument("--label", default="2026-27", help="Session label.")
    parser.add_argument("--out", default=None, help="Optional path to write the snapshot to.")
    parser.add_argument("--verbose", action="store_true", help="Show the structured run logs.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    config = Config(
        data_bucket="live-smoke-not-a-real-bucket",
        current_key="data/current.json",
        snapshot_prefix="archive/snapshots/",
        bills_api_base=DEFAULT_BILLS_API_BASE,
        parliament_session_id=args.session,
        parliament_session_label=args.label,
        refresh_interval_minutes=30,
        http_timeout_seconds=15.0,
        max_concurrent_requests=5,
        full_reconcile_after_days=7,
        schema_version=1,
        log_level="INFO",
        repository_url="https://github.com/EnvyWare/uk-bill-pipeline",
    )

    http = HttpClient(transport=StdlibTransport(read_timeout=15.0), user_agent=config.user_agent)
    client = ParliamentClient(http=http, base_url=config.bills_api_base)
    store = InMemoryS3()
    storage = SnapshotStorage(
        client=store,  # type: ignore[arg-type]
        bucket=config.data_bucket,
        current_key=config.current_key,
        snapshot_prefix=config.snapshot_prefix,
    )

    print(f"Fetching session {args.session} ({args.label}) from {config.bills_api_base}")
    print("Nothing is published; storage is in memory.\n")

    started = datetime.now(tz=UTC)
    try:
        summary = run_ingestion(
            config=config,
            client=client,
            storage=storage,
            now=started,
            invocation_id="live-smoke",
        )
    except Exception as exc:
        print(f"\nIngestion failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "This is the behaviour a real run would have: the previously "
            "published snapshot would be left in place.",
            file=sys.stderr,
        )
        return 1

    document = json.loads(store.objects[config.current_key].decode("utf-8"))
    bills = document["bills"]

    print("Run summary")
    print(f"  status                {summary.status}")
    print(f"  duration              {summary.duration_ms / 1000:.1f}s")
    print(f"  source requests       {summary.source_request_count}")
    print(f"  retries               {summary.retry_count}")
    print(f"  Bills in session      {summary.source_record_count}")
    print(f"  published             {summary.published_record_count}")
    print(f"  content hash          {summary.content_hash}")
    if summary.unmapped_stage_ids:
        print(f"  UNMAPPED STAGE IDS    {summary.unmapped_stage_ids}")
    else:
        print("  unmapped stage ids    none")

    print("\nCounts")
    for key, value in document["counts"].items():
        print(f"  {key:<22}{value}")

    print("\nBills by pipeline stage")
    for node, count in sorted(Counter(bill["pipelineNode"] for bill in bills).items()):
        print(f"  {node:<26}{count}")

    print("\nBills by mapping mode")
    for mode, count in sorted(Counter(bill["mappingMode"] for bill in bills).items()):
        print(f"  {mode:<26}{count}")

    warning_counts = Counter(code for bill in bills for code in bill["warnings"])
    if warning_counts:
        print("\nBill warnings")
        for code, count in sorted(warning_counts.items()):
            print(f"  {code:<26}{count}")

    if document["warnings"]:
        print("\nRun warnings")
        for warning in document["warnings"]:
            print(f"  [{warning['severity']}] {warning['code']}: {warning['message']}")

    unclassified = [b for b in bills if b["pipelineNode"] in ("unknown", "special_procedure")]
    if unclassified:
        print(f"\nUnclassified Bills ({len(unclassified)})")
        for bill in unclassified[:15]:
            detail = bill["stage"]["detail"] if bill["stage"] else "no current stage"
            print(f"  {bill['id']:<7}{bill['title'][:48]:<50}{detail}")

    if args.out:
        Path(args.out).write_text(json.dumps(document, indent=2), encoding="utf-8")
        print(f"\nSnapshot written to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
