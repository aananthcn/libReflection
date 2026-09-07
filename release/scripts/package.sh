#!/usr/bin/env bash
# Packages a build of libReflection into a versioned, distributable
# tarball under release/dist/. See release/README.md.
#
# Usage: release/scripts/package.sh <build-dir> [platform-tag]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="${1:?usage: package.sh <build-dir> [platform-tag]}"
PLATFORM_TAG="${2:-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)}"

VERSION="$(tr -d '[:space:]' < "${ROOT_DIR}/version.txt")"
PACKAGE_NAME="libReflection-${VERSION}-${PLATFORM_TAG}"
DIST_DIR="${ROOT_DIR}/release/dist/${PACKAGE_NAME}"

rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}"

cmake --install "${BUILD_DIR}" --prefix "${DIST_DIR}"
cp "${ROOT_DIR}/version.txt" "${DIST_DIR}/"

tar -C "${ROOT_DIR}/release/dist" -czf "${DIST_DIR}.tar.gz" "${PACKAGE_NAME}"
echo "Packaged: ${DIST_DIR}.tar.gz"
