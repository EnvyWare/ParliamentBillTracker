"""S3 reads, writes, cache metadata and archive idempotency."""

from __future__ import annotations

import json
from typing import Any

import pytest

from bill_pipeline.storage import (
    ARCHIVE_CACHE_CONTROL,
    CONTENT_TYPE,
    CURRENT_CACHE_CONTROL,
    SnapshotStorage,
)
from conftest import InMemoryS3, NoSuchKey

DOCUMENT: dict[str, Any] = {"schemaVersion": 1, "bills": [], "dataHash": "sha256:" + "aa" * 32}


def test_missing_current_object_is_a_normal_cold_start(storage: SnapshotStorage) -> None:
    assert storage.read_current() is None


def test_round_trip(storage: SnapshotStorage, s3: InMemoryS3) -> None:
    storage.write_current(DOCUMENT)
    assert storage.read_current() == DOCUMENT


def test_current_object_carries_the_data_cache_headers(
    storage: SnapshotStorage, s3: InMemoryS3
) -> None:
    """These must match the /data/* CloudFront behaviour."""
    storage.write_current(DOCUMENT)
    metadata = s3.metadata["data/current.json"]
    assert metadata["CacheControl"] == CURRENT_CACHE_CONTROL
    assert metadata["ContentType"] == CONTENT_TYPE
    assert "max-age=60" in CURRENT_CACHE_CONTROL
    assert "s-maxage=300" in CURRENT_CACHE_CONTROL
    assert "must-revalidate" in CURRENT_CACHE_CONTROL


def test_corrupt_current_object_reads_as_missing(storage: SnapshotStorage, s3: InMemoryS3) -> None:
    """A corrupt cache must not be trusted; the caller reconciles fully instead."""
    s3.objects["data/current.json"] = b"{ this is not json"
    assert storage.read_current() is None


def test_non_object_current_reads_as_missing(storage: SnapshotStorage, s3: InMemoryS3) -> None:
    s3.objects["data/current.json"] = b"[1, 2, 3]"
    assert storage.read_current() is None


def test_unexpected_s3_error_is_not_swallowed(storage: SnapshotStorage, s3: InMemoryS3) -> None:
    """Only the codes that genuinely mean "absent" are treated as absent.

    Note this is deliberately not AccessDenied: see the missing-object tests
    below for why a 403 has to be read as absent on a role with no ListBucket.
    """

    class InternalError(Exception):
        def __init__(self) -> None:
            super().__init__("InternalError")
            self.response = {
                "Error": {"Code": "InternalError"},
                "ResponseMetadata": {"HTTPStatusCode": 500},
            }

    def boom(**_: Any) -> dict[str, Any]:
        raise InternalError

    s3.get_object = boom  # type: ignore[method-assign]
    with pytest.raises(InternalError):
        storage.read_current()


def test_archive_is_written_once_for_the_same_content(
    storage: SnapshotStorage, s3: InMemoryS3
) -> None:
    key = "archive/snapshots/" + "aa" * 32 + ".json"
    assert storage.write_archive(key, DOCUMENT) is True
    assert storage.write_archive(key, DOCUMENT) is False
    assert s3.put_calls.count(key) == 1


def test_archive_object_is_immutable_and_private(storage: SnapshotStorage, s3: InMemoryS3) -> None:
    key = "archive/snapshots/" + "bb" * 32 + ".json"
    storage.write_archive(key, DOCUMENT)
    metadata = s3.metadata[key]
    assert metadata["CacheControl"] == ARCHIVE_CACHE_CONTROL
    assert "private" in ARCHIVE_CACHE_CONTROL


def test_stored_json_is_compact_utf8(storage: SnapshotStorage, s3: InMemoryS3) -> None:
    storage.write_current({"title": "Café Bill", "bills": []})
    raw = s3.objects["data/current.json"]
    assert raw.decode("utf-8").startswith('{"title":"Café Bill"')
    assert json.loads(raw.decode("utf-8"))["title"] == "Café Bill"


def test_missing_key_detection_recognises_botocore_shapes() -> None:
    from bill_pipeline.storage import _is_missing

    assert _is_missing(NoSuchKey()) is True

    class NotFound(Exception):
        def __init__(self) -> None:
            super().__init__("404")
            self.response = {
                "Error": {"Code": "404"},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            }

    assert _is_missing(NotFound()) is True
    assert _is_missing(ValueError("unrelated")) is False


def test_storage_only_ever_writes_within_its_configured_keys(
    storage: SnapshotStorage, s3: InMemoryS3
) -> None:
    """Nothing here can reach the frontend bucket or delete anything."""
    storage.write_current(DOCUMENT)
    storage.write_archive("archive/snapshots/x.json", DOCUMENT)
    assert all(key.startswith(("data/current.json", "archive/snapshots/")) for key in s3.put_calls)
    assert not hasattr(storage, "delete_object")


def test_access_denied_is_treated_as_a_missing_object() -> None:
    """S3 answers 403, not 404, for an absent object when ListBucket is absent.

    The execution role deliberately has no s3:ListBucket, so S3 cannot say
    whether current.json is missing or forbidden. A cold start therefore
    arrives as AccessDenied and must be handled as "nothing published yet".
    """
    from bill_pipeline.storage import _is_missing

    class AccessDenied(Exception):
        def __init__(self) -> None:
            super().__init__("AccessDenied")
            self.response = {
                "Error": {"Code": "AccessDenied"},
                "ResponseMetadata": {"HTTPStatusCode": 403},
            }

    assert _is_missing(AccessDenied()) is True


def test_cold_start_against_a_list_less_role_reads_as_no_snapshot(
    storage: SnapshotStorage, s3: InMemoryS3
) -> None:
    class AccessDenied(Exception):
        def __init__(self) -> None:
            super().__init__("AccessDenied")
            self.response = {
                "Error": {"Code": "AccessDenied"},
                "ResponseMetadata": {"HTTPStatusCode": 403},
            }

    def denied(**_: Any) -> dict[str, Any]:
        raise AccessDenied

    s3.get_object = denied  # type: ignore[method-assign]
    assert storage.read_current() is None
