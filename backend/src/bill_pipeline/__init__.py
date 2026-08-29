"""Scheduled ingestion for the UK Bill Pipeline.

This package retrieves UK Parliament Bills API data for one configured
Parliamentary session, normalises it onto a fixed legislative process model,
and publishes a self-contained JSON snapshot to S3.

Parliamentary information handled by this package is licensed under the
Open Parliament Licence v3.0 and is not covered by the repository MIT licence.
See THIRD_PARTY_NOTICES.md.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
