"""Shared fakes. No test in this suite opens a socket or touches AWS."""

from __future__ import annotations

import io
import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))

import synthetic_source as synthetic  # noqa: E402  isort:skip

from bill_pipeline.config import Config  # noqa: E402
from bill_pipeline.models import BillType  # noqa: E402
from bill_pipeline.parliament_client import ParliamentClient  # noqa: E402
from bill_pipeline.storage import SnapshotStorage  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.schema.json"

NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> Config:
    return Config(
        data_bucket="test-data-bucket",
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
        repository_url="https://github.com/EnvyWare/uk-bill-pipeline",
    )


@pytest.fixture(scope="session")
def schema() -> dict[str, Any]:
    with SCHEMA_PATH.open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = json.load(handle)
    return loaded


@pytest.fixture
def bill_types() -> dict[int, BillType]:
    return {
        entry["id"]: BillType(id=entry["id"], name=entry["name"], category=entry["category"])
        for entry in synthetic.bill_types()
    }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class ScriptedHttp:
    """Stands in for :class:`HttpClient`, serving canned pages by URL."""

    def __init__(self, pages: Mapping[str, list[dict[str, Any]]] | None = None) -> None:
        self.pages = dict(pages or {})
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.request_count = 0
        self.retry_count = 0

    def get_json(self, url: str, params: Mapping[str, object] | None = None) -> dict[str, Any]:
        self.request_count += 1
        self.calls.append((url, dict(params or {})))
        queue = self.pages.get(url)
        if queue is None:
            raise AssertionError(f"No scripted response for {url}")
        if not queue:
            raise AssertionError(f"Scripted responses for {url} were exhausted")
        return queue.pop(0)


class SyntheticApiHttp:
    """Serves the synthetic dataset through the real pagination code path."""

    def __init__(
        self,
        *,
        bills: list[dict[str, Any]] | None = None,
        canary_session_id: int = synthetic.SESSION_ID,
        page_size: int = 100,
    ) -> None:
        self.bills = bills if bills is not None else synthetic.bills_list()
        self.details = synthetic.details_by_id()
        self.histories = synthetic.stages_by_id()
        self.canary_session_id = canary_session_id
        self.page_size = page_size
        self.request_count = 0
        self.retry_count = 0
        #: Bill ids whose detail or history were actually retrieved.
        self.detail_fetches: list[int] = []
        self.history_fetches: list[int] = []

    def get_json(self, url: str, params: Mapping[str, object] | None = None) -> dict[str, Any]:
        self.request_count += 1
        query = dict(params or {})
        path = url.split("/api/v1", 1)[1]

        if path == "/Bills" and query.get("SortOrder") == "DateUpdatedDescending":
            return {
                "totalResults": 1,
                "items": [
                    {
                        "billId": 1,
                        "shortTitle": "Canary Bill",
                        "introducedSessionId": self.canary_session_id,
                    }
                ],
            }
        if path == "/Bills":
            return self._page(self.bills, query)
        if path == "/BillTypes":
            return self._page(synthetic.bill_types(), query)
        if path == "/Stages":
            return self._page(_stage_catalogue(), query)
        if path.endswith("/Stages"):
            bill_id = int(path.split("/")[2])
            self.history_fetches.append(bill_id)
            return self._page(self.histories[bill_id], query)

        bill_id = int(path.split("/")[2])
        self.detail_fetches.append(bill_id)
        return self.details[bill_id]

    def _page(self, items: list[dict[str, Any]], query: Mapping[str, object]) -> dict[str, Any]:
        skip = int(query.get("Skip", 0) or 0)
        take = min(int(query.get("Take", self.page_size) or self.page_size), self.page_size)
        return {"totalResults": len(items), "items": items[skip : skip + take]}


def _stage_catalogue() -> list[dict[str, Any]]:
    with (FIXTURES / "stages_catalogue.json").open(encoding="utf-8") as handle:
        payload: dict[str, Any] = json.load(handle)
    items: list[dict[str, Any]] = payload["items"]
    return items


@pytest.fixture
def api_http() -> SyntheticApiHttp:
    return SyntheticApiHttp()


@pytest.fixture
def client(api_http: SyntheticApiHttp, config: Config) -> ParliamentClient:
    return ParliamentClient(http=api_http, base_url=config.bills_api_base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------


class NoSuchKey(Exception):
    """Mirrors the shape of a botocore ClientError for a missing object."""

    def __init__(self) -> None:
        super().__init__("NoSuchKey")
        self.response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }


class InMemoryS3:
    """The narrow slice of the S3 API this project uses."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict[str, Any]] = {}
        self.put_calls: list[str] = []

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        if key not in self.objects:
            raise NoSuchKey
        return {"Body": io.BytesIO(self.objects[key])}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        self.objects[key] = kwargs["Body"]
        self.metadata[key] = {
            "ContentType": kwargs.get("ContentType"),
            "CacheControl": kwargs.get("CacheControl"),
        }
        self.put_calls.append(key)
        return {}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["Key"] not in self.objects:
            raise NoSuchKey
        return {}

    # -- test helpers ------------------------------------------------------

    def load(self, key: str) -> dict[str, Any]:
        parsed: dict[str, Any] = json.loads(self.objects[key].decode("utf-8"))
        return parsed

    def store(self, key: str, document: dict[str, Any]) -> None:
        self.objects[key] = json.dumps(document).encode("utf-8")


@pytest.fixture
def s3() -> InMemoryS3:
    return InMemoryS3()


@pytest.fixture
def storage(s3: InMemoryS3, config: Config) -> SnapshotStorage:
    return SnapshotStorage(
        client=s3,  # type: ignore[arg-type]
        bucket=config.data_bucket,
        current_key=config.current_key,
        snapshot_prefix=config.snapshot_prefix,
    )
