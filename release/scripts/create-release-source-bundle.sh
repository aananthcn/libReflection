#!/usr/bin/env bash
# Bundles the repository's source tree into a versioned zip archive
# under release/artifacts/ -- a source snapshot, not a build (see
# package.sh for that). See release/README.md.
#
# Usage: release/scripts/create-release-source-bundle.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

VERSION="$(tr -d '[:space:]' < "${ROOT_DIR}/version.txt")"
ARTIFACTS_DIR="${ROOT_DIR}/release/artifacts"
ZIP_PATH="${ARTIFACTS_DIR}/libReflection-${VERSION}.zip"

mkdir -p "${ARTIFACTS_DIR}"
rm -f "${ZIP_PATH}"

# git is the source of truth for what .gitignore excludes -- asking IT
# (rather than reimplementing gitignore's pattern syntax by hand here)
# means this can never silently disagree with what `git status` shows.
# --cached (already tracked) + --others --exclude-standard (untracked
# but NOT ignored) together give exactly "every file that isn't
# ignored", whether committed yet or not -- so an in-progress,
# uncommitted change (like a version.txt bump) is still bundled using
# its real, current content on disk, not a stale committed one.
git ls-files --cached --others --exclude-standard \
    | zip -X -q "${ZIP_PATH}" -@

echo "Bundled: ${ZIP_PATH}"
