#!/usr/bin/env bash
set -euo pipefail

TARGET_BUNDLE="/app/build/_app/immutable/chunks/BnHPywC-.js"
BACKUP_BUNDLE="/app/build/_app/immutable/chunks/BnHPywC-.js.orig"
PATCHED_SOURCE="/opt/realtime-patch/BnHPywC-.js"

EXPECTED_ORIG_SHA256="d2359a68d087ee9a7ab52895653e4f27f40b64f90f0ede8a0eb5c77729dbf33c"
EXPECTED_PATCHED_SHA256="d5e4d07cfd5d13b4dfe0aa0d0dcb261ef2296d0ca6484f8ffcc7ac89187f67ab"

apply_realtime_patch_if_compatible() {
  if [[ ! -f "$TARGET_BUNDLE" ]]; then
    echo "[realtime-patch] Target bundle not found at $TARGET_BUNDLE; skipping patch." >&2
    return 0
  fi

  local current_sha
  current_sha="$(sha256sum "$TARGET_BUNDLE" | awk '{print $1}')"

  if [[ "$current_sha" == "$EXPECTED_PATCHED_SHA256" ]]; then
    echo "[realtime-patch] BnHPywC-.js already matches expected patched sha256 ($EXPECTED_PATCHED_SHA256)."
    return 0
  fi

  if [[ "$current_sha" != "$EXPECTED_ORIG_SHA256" ]]; then
    echo "[realtime-patch] WARNING: Unexpected bundle sha256=$current_sha (expected $EXPECTED_ORIG_SHA256). Refusing to overwrite." >&2
    return 0
  fi

  if [[ ! -f "$PATCHED_SOURCE" ]]; then
    echo "[realtime-patch] ERROR: Patched source missing at $PATCHED_SOURCE." >&2
    return 1
  fi

  local source_sha
  source_sha="$(sha256sum "$PATCHED_SOURCE" | awk '{print $1}')"
  if [[ "$source_sha" != "$EXPECTED_PATCHED_SHA256" ]]; then
    echo "[realtime-patch] ERROR: Patched source sha256 mismatch ($source_sha != $EXPECTED_PATCHED_SHA256)." >&2
    return 1
  fi

  if [[ ! -f "$BACKUP_BUNDLE" ]]; then
    local bak_tmp="${BACKUP_BUNDLE}.tmp.$$"
    cp -p "$TARGET_BUNDLE" "$bak_tmp"
    mv -f "$bak_tmp" "$BACKUP_BUNDLE"
  fi

  local stage_tmp="${TARGET_BUNDLE}.tmp.$$"
  cp "$PATCHED_SOURCE" "$stage_tmp"
  chmod 0644 "$stage_tmp"
  local staged_sha
  staged_sha="$(sha256sum "$stage_tmp" | awk '{print $1}')"
  if [[ "$staged_sha" != "$EXPECTED_PATCHED_SHA256" ]]; then
    rm -f "$stage_tmp"
    echo "[realtime-patch] ERROR: Staged bundle sha256 mismatch ($staged_sha)." >&2
    return 1
  fi
  mv -f "$stage_tmp" "$TARGET_BUNDLE"
  echo "[realtime-patch] Applied verified BnHPywC-.js realtime patch (sha256=$EXPECTED_PATCHED_SHA256)."
}

apply_realtime_patch_if_compatible
exec bash /app/backend/start.sh "$@"
