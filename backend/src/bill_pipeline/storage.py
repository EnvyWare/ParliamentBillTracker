"""S3 persistence for the published snapshot and its immutable archive.

``current.json`` is written last and written whole. Replacing an S3 object is
atomic for readers, so a browser either sees the previous complete snapshot or
the new complete snapshot, never a half-written one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final, Protocol

#: Matches the CloudFront behaviour for /data/*: browsers revalidate after a
#: minute, the CDN holds it for five.
CURRENT_CACHE_CONTROL: Final = "public,max-age=60,s-maxage=300,must-revalidate"

#: Archive objects are content-addressed and never change, but they are private
#: and are not served through CloudFront.
ARCHIVE_CACHE_CONTROL: Final = "private,max-age=31536000,immutable"

CONTENT_TYPE: Final = "application/json; charset=utf-8"


class S3Client(Protocol):
    """The narrow slice of the boto3 S3 client this project uses."""

    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...


#: Codes that mean "this object is not there".
#:
#: AccessDenied is included deliberately. This role holds s3:GetObject on
#: exactly the two key patterns it reads and, by design, no s3:ListBucket at
#: all. Without listing rights S3 cannot reveal whether an object is absent or
#: merely forbidden, so it answers 403 for both - which means a cold start,
#: before the first snapshot exists, arrives here as AccessDenied rather than
#: NoSuchKey.
#:
#: Treating it as absent is safe because it cannot hide a broken policy: the
#: run goes on to write the same key, and a genuine permissions fault fails
#: loudly there instead.
_MISSING_CODES = frozenset({"NoSuchKey", "NotFound", "404", "AccessDenied", "403"})


def _is_missing(error: Exception) -> bool:
    """Whether a boto3 error means the object is not readable as an object."""
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False
    code = str(response.get("Error", {}).get("Code", ""))
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in _MISSING_CODES or status in {403, 404}


@dataclass(frozen=True, slots=True)
class SnapshotStorage:
    """Reads and writes the snapshot objects in the private data bucket."""

    client: S3Client
    bucket: str
    current_key: str
    snapshot_prefix: str

    def read_current(self) -> dict[str, Any] | None:
        """Return the previously published snapshot, or ``None``.

        A missing object is the normal cold-start case. A present but
        unreadable object returns ``None`` too: the caller then performs a full
        reconciliation rather than trusting a corrupt cache.
        """
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.current_key)
        except Exception as exc:  # boto3 raises client-specific error types
            if _is_missing(exc):
                return None
            raise
        try:
            body = response["Body"].read()
            parsed = json.loads(body.decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def write_current(self, document: dict[str, Any]) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self.current_key,
            Body=_encode(document),
            ContentType=CONTENT_TYPE,
            CacheControl=CURRENT_CACHE_CONTROL,
        )

    def write_archive(self, key: str, document: dict[str, Any]) -> bool:
        """Write an immutable archive object unless it already exists.

        Returns ``True`` when an object was written. The key is content
        addressed, so a duplicate at-least-once invocation finds the object
        already present and writes nothing.
        """
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # boto3 raises client-specific error types
            if not _is_missing(exc):
                raise
        else:
            return False

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=_encode(document),
            ContentType=CONTENT_TYPE,
            CacheControl=ARCHIVE_CACHE_CONTROL,
        )
        return True


def _encode(document: dict[str, Any]) -> bytes:
    return json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
