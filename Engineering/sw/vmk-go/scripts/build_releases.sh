#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${DIST_DIR:-${ROOT_DIR}/dist}"
BUILD_TMP="${DIST_DIR}/.gotmp"

rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}" "${BUILD_TMP}"
trap 'rm -rf "${BUILD_TMP}"' EXIT

export GOTMPDIR="${GOTMPDIR:-${BUILD_TMP}}"
export TMPDIR="${TMPDIR:-${BUILD_TMP}}"

TARGETS=(
  "linux:amd64:vmk-linux-amd64"
  "linux:arm64:vmk-linux-arm64"
  "darwin:arm64:vmk-darwin-arm64"
  "darwin:amd64:vmk-darwin-amd64"
  "windows:amd64:vmk-windows-amd64.exe"
)

cd "${ROOT_DIR}"

for entry in "${TARGETS[@]}"; do
  IFS=":" read -r goos goarch out_name <<< "${entry}"
  echo "[build_releases] Building ${out_name} (GOOS=${goos} GOARCH=${goarch} CGO_ENABLED=0 -tags public)..."
  GOOS="${goos}" GOARCH="${goarch}" CGO_ENABLED=0 \
    go build -tags public -trimpath -ldflags="-s -w" -o "${DIST_DIR}/${out_name}" ./cmd/vmk
done

rm -rf "${BUILD_TMP}"

(
  cd "${DIST_DIR}"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum vmk-* > SHA256SUMS
  else
    shasum -a 256 vmk-* > SHA256SUMS
  fi
)

echo "[build_releases] Built 5 static public binaries and generated SHA256SUMS:"
cat "${DIST_DIR}/SHA256SUMS"
