#!/usr/bin/env bash
#
# Upload the built frontend to the site bucket with correct cache metadata.
#
# The three object classes get different Cache-Control headers, and getting
# them the wrong way round is the classic static-site bug:
#
#   fingerprinted assets  immutable for a year - the filename changes when the
#                         content does, so it can never go stale
#   index.html and roots  always revalidated - it is the file that points at
#                         the fingerprinted assets
#   data/current.json     written by the ingestion function, never from here
#
# This uploads the immutable assets first. If it were the other way round, a
# browser could fetch a new index.html and then ask for an asset that had not
# finished uploading.
#
# Usage: scripts/deploy_frontend.sh <site-bucket> [distribution-id]
#
# Requires the AWS CLI and credentials with write access to the site bucket.

set -euo pipefail

# Git Bash rewrites arguments that look like absolute paths, which turns a
# CloudFront invalidation path of "/" into a Windows directory. Harmless
# elsewhere; essential on Windows.
export MSYS_NO_PATHCONV=1

BUCKET="${1:-}"
DISTRIBUTION_ID="${2:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${REPO_ROOT}/frontend/dist"

if [ -z "${BUCKET}" ]; then
  echo "Usage: scripts/deploy_frontend.sh <site-bucket> [distribution-id]" >&2
  exit 2
fi

if [ ! -f "${DIST}/index.html" ]; then
  echo "No build found at ${DIST}. Run 'make build-frontend' first." >&2
  exit 1
fi

echo "Uploading fingerprinted assets to s3://${BUCKET}/assets/"
aws s3 sync "${DIST}/assets" "s3://${BUCKET}/assets" \
  --cache-control "public,max-age=31536000,immutable" \
  --delete \
  --no-progress

# Fonts are versioned in the filename rather than fingerprinted by the build,
# because index.html preloads them by a path it has to know in advance. A new
# cut of a face is a new filename, so immutable is as safe here as it is for
# assets/, and without it a preloaded font revalidates on every page load.
if [ -d "${DIST}/fonts" ]; then
  echo "Uploading fonts to s3://${BUCKET}/fonts/"
  aws s3 sync "${DIST}/fonts" "s3://${BUCKET}/fonts" \
    --cache-control "public,max-age=31536000,immutable" \
    --delete \
    --no-progress
fi

echo "Uploading root documents to s3://${BUCKET}/"
# --exclude assets/* and fonts/* leave the immutable uploads above untouched.
# The --delete here is scoped to the site bucket, which is a different bucket
# from the one holding the published snapshot: this command cannot reach the
# data.
#
# data/* is excluded because the build tree contains the synthetic development
# fixture at dist/data/current.json. CloudFront routes /data/* to the data
# origin, so an uploaded copy would not be served, but a file of invented Bills
# has no business sitting in the production site bucket at all.
aws s3 sync "${DIST}" "s3://${BUCKET}" \
  --cache-control "public,max-age=0,must-revalidate" \
  --exclude "assets/*" \
  --exclude "fonts/*" \
  --exclude "data/*" \
  --delete \
  --no-progress

if [ -n "${DISTRIBUTION_ID}" ]; then
  # Only the documents that are revalidated anyway. Invalidating /* on every
  # deployment would be wasteful and is never necessary here, because every
  # other object is either fingerprinted or short-lived by policy.
  echo "Invalidating / and /index.html on ${DISTRIBUTION_ID}"
  aws cloudfront create-invalidation \
    --distribution-id "${DISTRIBUTION_ID}" \
    --paths "/" "/index.html" \
    --query 'Invalidation.Id' \
    --output text
fi

echo "Frontend deployed."
