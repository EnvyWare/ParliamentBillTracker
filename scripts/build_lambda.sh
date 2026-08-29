#!/usr/bin/env bash
#
# Build the ingestion Lambda package.
#
# Terraform zips the directory this produces, so the contents must be complete
# and reproducible. Three things go in:
#
#   1. the handler package itself
#   2. the snapshot schema, so the function can validate before it publishes
#   3. tzdata, so Europe/London resolves without depending on the base image
#
# Everything else the function needs is either the Python standard library or
# boto3, which the AWS runtime already provides. No compiled wheel is
# involved, so this builds for arm64 from any machine.
#
# Usage: scripts/build_lambda.sh [python-executable]
#
# On Windows, run it from Git Bash, or run the same three steps by hand as
# described in docs/deployment.md.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${REPO_ROOT}/backend/build/lambda"
PYTHON="${1:-python3}"

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "Python executable '${PYTHON}' not found." >&2
  echo "Pass one explicitly, for example: scripts/build_lambda.sh python" >&2
  exit 1
fi

echo "Building the Lambda package into ${BUILD_DIR}"
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

# 1. The handler package.
cp -R "${REPO_ROOT}/backend/src/bill_pipeline" "${BUILD_DIR}/bill_pipeline"

# 2. The schema, placed beside the module so find_schema_path() picks up the
#    packaged copy rather than walking up to the repository.
cp "${REPO_ROOT}/schema/snapshot.schema.json" "${BUILD_DIR}/bill_pipeline/snapshot.schema.json"

# 3. The time zone database. Pure data, so --no-deps keeps it to exactly this.
"${PYTHON}" -m pip install \
  --quiet \
  --disable-pip-version-check \
  --no-compile \
  --no-deps \
  --target "${BUILD_DIR}" \
  "tzdata>=2025.2"

# Bytecode is machine-specific and would make the zip non-reproducible.
find "${BUILD_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "${BUILD_DIR}" -type f -name '*.pyc' -delete 2>/dev/null || true

if [ ! -f "${BUILD_DIR}/bill_pipeline/handler.py" ]; then
  echo "Build failed: handler.py is missing from the package." >&2
  exit 1
fi

if [ ! -f "${BUILD_DIR}/bill_pipeline/snapshot.schema.json" ]; then
  echo "Build failed: the snapshot schema is missing from the package." >&2
  exit 1
fi

if [ ! -d "${BUILD_DIR}/tzdata" ]; then
  echo "Build failed: tzdata is missing, so Europe/London would not resolve." >&2
  exit 1
fi

SIZE="$(du -sk "${BUILD_DIR}" | cut -f1)"
echo "Package built: ${SIZE} KB uncompressed."
echo "Terraform will zip ${BUILD_DIR} on the next plan."
