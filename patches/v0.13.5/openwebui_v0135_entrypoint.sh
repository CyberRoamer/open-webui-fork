#!/usr/bin/env bash
set -euo pipefail

# Applies SHA-256-verified patches for Open WebUI v0.13.5:
# 1. B1EqPYAs.js : Mobile realtime AudioWorklet 44.1/48 kHz resampler + gesture unlock
# 2. ask_user.py : Allow 0 or more options (forcing free-form text input when 0)
# 3. builtin.py  : Allow 0 or more options in ask_user builtin tool + docstring

apply_verified_patch() {
  local label="$1"
  local target_file="$2"
  local backup_file="$3"
  local patched_source="$4"
  local expected_orig_sha256="$5"
  local expected_patched_sha256="$6"

  if [[ ! -f "$target_file" ]]; then
    echo "[v0135-patch] Target $label not found at $target_file; skipping patch." >&2
    return 0
  fi

  local current_sha
  current_sha="$(sha256sum "$target_file" | awk '{print $1}')"

  if [[ "$current_sha" == "$expected_patched_sha256" ]]; then
    echo "[v0135-patch] $label already matches expected patched sha256 ($expected_patched_sha256)."
    return 0
  fi

  if [[ "$current_sha" != "$expected_orig_sha256" ]]; then
    echo "[v0135-patch] WARNING: Unexpected $label sha256=$current_sha (expected $expected_orig_sha256). Refusing to overwrite." >&2
    return 0
  fi

  if [[ ! -f "$patched_source" ]]; then
    echo "[v0135-patch] ERROR: Patched source missing at $patched_source." >&2
    return 1
  fi

  local source_sha
  source_sha="$(sha256sum "$patched_source" | awk '{print $1}')"
  if [[ "$source_sha" != "$expected_patched_sha256" ]]; then
    echo "[v0135-patch] ERROR: Patched source sha256 mismatch for $label ($source_sha != $expected_patched_sha256)." >&2
    return 1
  fi

  if [[ ! -f "$backup_file" ]]; then
    local bak_tmp="${backup_file}.tmp.$$"
    cp -p "$target_file" "$bak_tmp"
    mv -f "$bak_tmp" "$backup_file"
  fi

  local stage_tmp="${target_file}.tmp.$$"
  cp "$patched_source" "$stage_tmp"
  chmod 0644 "$stage_tmp"
  local staged_sha
  staged_sha="$(sha256sum "$stage_tmp" | awk '{print $1}')"
  if [[ "$staged_sha" != "$expected_patched_sha256" ]]; then
    rm -f "$stage_tmp"
    echo "[v0135-patch] ERROR: Staged $label sha256 mismatch ($staged_sha)." >&2
    return 1
  fi
  mv -f "$stage_tmp" "$target_file"
  echo "[v0135-patch] Applied verified $label patch (sha256=$expected_patched_sha256)."
}

apply_verified_patch \
  "B1EqPYAs.js" \
  "/app/build/_app/immutable/chunks/B1EqPYAs.js" \
  "/app/build/_app/immutable/chunks/B1EqPYAs.js.orig" \
  "/opt/realtime-patch/B1EqPYAs.js" \
  "29d6b2a2e76eff38c3bd7602c006459ed8d19c405eeaa06b28da52b81347e31c" \
  "b2644911f0aeb9c7786f004f6b725cef71bfc8363aa083be98e58371cdd3d86c"

apply_verified_patch \
  "ask_user.py" \
  "/app/backend/open_webui/utils/ask_user.py" \
  "/app/backend/open_webui/utils/ask_user.py.orig" \
  "/opt/realtime-patch/ask_user.py" \
  "8538e5effbda42c310573e6a5be718b8ea655ddb90c5360b25bf1386a74e5c5d" \
  "984e19f255f7cadc6839147acee4502d58fd80f4c75ef7c90c61cb4fae89b16b"

apply_verified_patch \
  "builtin.py" \
  "/app/backend/open_webui/tools/builtin.py" \
  "/app/backend/open_webui/tools/builtin.py.orig" \
  "/opt/realtime-patch/builtin.py" \
  "1bd4ce2bd8a8aaf180a5a0783a616519968de62eaea1c87b54536c51e560d59c" \
  "7e0134597c37b08deb79845d84435c94b6fef3c0c342b58237934ddef18045b0"

exec bash /app/backend/start.sh "$@"
