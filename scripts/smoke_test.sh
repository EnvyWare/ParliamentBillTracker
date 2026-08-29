#!/usr/bin/env bash
#
# Post-deployment smoke test.
#
# Checks the properties that matter and that only a live deployment can show:
# the site is served, the snapshot is served with the right cache headers and
# is schema-valid and fresh, and the buckets are not reachable directly.
#
# Usage:
#   scripts/smoke_test.sh <site-url> [site-bucket] [data-bucket]
#
# The bucket arguments are optional. When given, the script also confirms that
# anonymous access to S3 is refused, which is the check that proves CloudFront
# is genuinely the only way in.

set -euo pipefail

SITE_URL="${1:-}"
SITE_BUCKET="${2:-}"
DATA_BUCKET="${3:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

# The frontend treats a snapshot older than this as stale.
MAX_AGE_MINUTES="${MAX_AGE_MINUTES:-180}"

# The bucket region matters. Addressed through the global S3 endpoint, a
# bucket outside us-east-1 answers 307 rather than 403, which would make the
# privacy check below report a false failure.
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-eu-west-2}}"

if [ -z "${SITE_URL}" ]; then
  echo "Usage: scripts/smoke_test.sh <site-url> [site-bucket] [data-bucket]" >&2
  exit 2
fi

SITE_URL="${SITE_URL%/}"
FAILURES=0

# A real temporary directory rather than a hard-coded /tmp, which is not the
# same location for every tool on Windows.
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

pass() { echo "  ok    $1"; }
fail() {
  echo "  FAIL  $1" >&2
  FAILURES=$((FAILURES + 1))
}

echo "Smoke testing ${SITE_URL}"

# ---------------------------------------------------------------------------
# The application itself
# ---------------------------------------------------------------------------

STATUS="$(curl -fsS -o "${WORK}/index.html" -w '%{http_code}' "${SITE_URL}/" || echo 000)"
if [ "${STATUS}" = "200" ]; then
  pass "GET / returns 200"
else
  fail "GET / returned ${STATUS}"
fi

if grep -q 'id="root"' "${WORK}/index.html" 2>/dev/null; then
  pass "index.html contains the application root"
else
  fail "index.html does not look like the built application"
fi

# The compiled bundle the page actually references, rather than a guess.
ASSET="$(grep -oE '/assets/[A-Za-z0-9._-]+\.js' "${WORK}/index.html" 2>/dev/null | head -1 || true)"
if [ -n "${ASSET}" ]; then
  ASSET_HEADERS="$(curl -fsS -D - -o /dev/null "${SITE_URL}${ASSET}" || true)"
  if grep -qi '^HTTP/.* 200' <<<"${ASSET_HEADERS}"; then
    pass "the compiled asset ${ASSET} is served"
  else
    fail "the compiled asset ${ASSET} was not served"
  fi
  if grep -qi 'cache-control:.*immutable' <<<"${ASSET_HEADERS}"; then
    pass "fingerprinted assets are immutable for a year"
  else
    fail "fingerprinted assets are missing their immutable cache header"
  fi
else
  fail "index.html references no compiled asset"
fi

# ---------------------------------------------------------------------------
# The published snapshot
# ---------------------------------------------------------------------------

DATA_HEADERS="$(curl -fsS -D - -o "${WORK}/current.json" "${SITE_URL}/data/current.json" || true)"
if grep -qi '^HTTP/.* 200' <<<"${DATA_HEADERS}"; then
  pass "GET /data/current.json returns 200"
else
  fail "GET /data/current.json did not return 200"
fi

if grep -qi 'cache-control:.*max-age=60' <<<"${DATA_HEADERS}"; then
  pass "the snapshot carries its short cache header"
else
  fail "the snapshot is missing the expected max-age=60 cache header"
fi

if [ -s "${WORK}/current.json" ]; then
  if "${PYTHON}" "${REPO_ROOT}/scripts/validate_snapshot.py" "${WORK}/current.json" \
    --max-age-minutes "${MAX_AGE_MINUTES}"; then
    pass "the snapshot is schema-valid, live and fresh"
  else
    fail "the snapshot failed validation, is synthetic, or is stale"
  fi
else
  fail "the snapshot response was empty"
fi

# ---------------------------------------------------------------------------
# The buckets must not be reachable directly
# ---------------------------------------------------------------------------

check_bucket_is_private() {
  local bucket="$1"
  local label="$2"
  local status
  status="$(curl -s -o /dev/null -w '%{http_code}' \
    "https://${bucket}.s3.${REGION}.amazonaws.com/index.html" || echo 000)"
  if [ "${status}" = "403" ] || [ "${status}" = "404" ]; then
    pass "anonymous access to the ${label} bucket is refused (${status})"
  else
    fail "anonymous access to the ${label} bucket returned ${status}, expected 403"
  fi
}

if [ -n "${SITE_BUCKET}" ]; then
  check_bucket_is_private "${SITE_BUCKET}" "site"
fi

if [ -n "${DATA_BUCKET}" ]; then
  check_bucket_is_private "${DATA_BUCKET}" "data"
fi

echo
if [ "${FAILURES}" -gt 0 ]; then
  echo "${FAILURES} smoke check(s) failed." >&2
  exit 1
fi

echo "All smoke checks passed."
