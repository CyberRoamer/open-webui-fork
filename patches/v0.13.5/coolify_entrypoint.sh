#!/usr/bin/env bash
set -euo pipefail

# Coolify / standalone container entrypoint for Open WebUI v0.13.5.
# 1. Ensures SHA-256-verified v0.13.5 patches are active.
# 2. Optionally bootstraps Speech Coach tool + image connections once webui.db is ready.

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

bootstrap_tools_and_connections() {
  local litellm_url="${LITELLM_BASE_URL:-}"
  local litellm_key="${LITELLM_API_KEY:-${LITELLM_MASTER_KEY:-${OPENAI_API_KEY:-}}}"
  local target_port="${PORT:-8080}"

  if [[ "${AUTO_BOOTSTRAP_TOOLS:-true}" != "true" ]]; then
    return 0
  fi
  if [[ -z "$litellm_url" || "$litellm_url" == *"<YOUR_LITELLM_HOST>"* ]]; then
    return 0
  fi
  if [[ -z "$litellm_key" || "$litellm_key" == *"<YOUR_LITELLM_API_KEY>"* ]]; then
    return 0
  fi
  if [[ ! -f "/opt/openwebui-tools/register_tool.py" ]]; then
    return 0
  fi

  (
    local waited=0
    while [[ $waited -lt 180 ]]; do
      if curl -s -f "http://127.0.0.1:${target_port}/health" >/dev/null 2>&1 && [[ -f "/app/backend/data/webui.db" ]]; then
        break
      fi
      sleep 3
      waited=$((waited + 3))
    done

    if [[ ! -f "/app/backend/data/webui.db" ]]; then
      echo "[bootstrap] webui.db not found after ${waited}s; skipping auto-bootstrap." >&2
      exit 0
    fi

    python3 /opt/openwebui-tools/register_tool.py \
      --db /app/backend/data/webui.db \
      --source /opt/openwebui-tools/speech_coach_tool.py \
      --litellm-url "$litellm_url" \
      --api-key "$litellm_key" \
      --timeout "${SPEECH_COACH_TIMEOUT:-60.0}" \
      --speech-path "${SPEECH_COACH_ANALYSIS_PATH:-/v1/audio/speech-analysis}" \
      --voices-path "${SPEECH_COACH_VOICES_PATH:-/v1/audio/voices}" || true

    IMG_DISCOVERY_URL="${IMAGES_OPENAI_API_BASE_URL:-${litellm_url%/}/images/v1}" \
    IMG_DISCOVERY_KEY="${IMAGES_OPENAI_API_KEY:-$litellm_key}" \
    IMG_DEFAULT_MODEL="${IMAGE_GENERATION_MODEL:-flux1-schnell}" \
    IMG_EDIT_MODEL="${IMAGE_EDIT_MODEL:-flux1-schnell}" \
    python3 -c '
import json, os, sqlite3, time, uuid

db_path = "/app/backend/data/webui.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT value FROM config WHERE key = '\''images.connections'\''")
row = c.fetchone()
img_url = os.environ["IMG_DISCOVERY_URL"].rstrip("/")
img_key = os.environ["IMG_DISCOVERY_KEY"]
default_model = os.environ["IMG_DEFAULT_MODEL"]
edit_model = os.environ["IMG_EDIT_MODEL"]
now = int(time.time())

existing_conns = json.loads(row[0]) if (row and row[0]) else []
if not isinstance(existing_conns, list):
    existing_conns = []

updated = False
for conn_item in existing_conns:
    if isinstance(conn_item, dict) and conn_item.get("url", "").rstrip("/") == img_url:
        conn_item["key"] = img_key
        conn_item["enabled"] = True
        updated = True
        break

if not updated:
    existing_conns.append({
        "id": str(uuid.uuid4()),
        "url": img_url,
        "key": img_key,
        "enabled": True,
        "config": {
            "enable_image_generation": True,
            "default_model": default_model,
            "edit_model": edit_model,
        },
    })

new_val = json.dumps(existing_conns)
if row:
    c.execute("UPDATE config SET value = ?, updated_at = ? WHERE key = '\''images.connections'\''", (new_val, now))
else:
    c.execute("INSERT INTO config (key, value, created_at, updated_at) VALUES ('\''images.connections'\'', ?, ?, ?)", (new_val, now, now))
conn.commit()
conn.close()
print("[bootstrap] Image model connection synced:", img_url)
' || true
  ) &
}

apply_verified_patch \
  "B1EqPYAs.js" \
  "/app/build/_app/immutable/chunks/B1EqPYAs.js" \
  "/app/build/_app/immutable/chunks/B1EqPYAs.js.orig" \
  "/opt/realtime-patch/B1EqPYAs.js" \
  "29d6b2a2e76eff38c3bd7602c006459ed8d19c405eeaa06b28da52b81347e31c" \
  "a39794ef60a0d0c0571ff17499b458338f933ba8fc6c2e7761cba5bcafe72d90"

apply_verified_patch \
  "CaoI0pp2.js" \
  "/app/build/_app/immutable/chunks/CaoI0pp2.js" \
  "/app/build/_app/immutable/chunks/CaoI0pp2.js.orig" \
  "/opt/realtime-patch/CaoI0pp2.js" \
  "7611058e08d300631a1d481bea550389eba07a5ac873611e814139f86f5bdd94" \
  "4ba267e48e304c3d5f4c720f665f397952863ea6ea5d4d762b137af3840e939e"

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

apply_verified_patch \
  "middleware.py" \
  "/app/backend/open_webui/utils/middleware.py" \
  "/app/backend/open_webui/utils/middleware.py.orig" \
  "/opt/realtime-patch/middleware.py" \
  "919b4dc69c6356d65ed1198467710f00933de3b08825f5c5b96a5f3d5f066f7d" \
  "7fac507d50b85c8296318876cd914402954eaa200c8678e64e244852c32ebccd"

apply_verified_patch \
  "headers.py" \
  "/app/backend/open_webui/utils/headers.py" \
  "/app/backend/open_webui/utils/headers.py.orig" \
  "/opt/realtime-patch/headers.py" \
  "2601a71db5eadd258d5dc89b40023d4c470063357bdeafe939cbcda45a32a432" \
  "7a158f28d1b8f6b9efd6510686f95d4bc0d9a1d8b782dfb0e7f664d0b85bbc51"

apply_verified_patch \
  "audio_init.py" \
  "/app/backend/open_webui/routers/audio/__init__.py" \
  "/app/backend/open_webui/routers/audio/__init__.py.orig" \
  "/opt/realtime-patch/audio_init.py" \
  "f22233f795444da1773f07043e478b77f915bde5633580a9f231b4eed864dd40" \
  "9265128cdb8f15ec5c9c0327a67bd9f7de2ac78ff3f65129199c6aa8c3567f17"

apply_verified_patch \
  "audio_realtime.py" \
  "/app/backend/open_webui/routers/audio/realtime.py" \
  "/app/backend/open_webui/routers/audio/realtime.py.orig" \
  "/opt/realtime-patch/audio_realtime.py" \
  "0226a1501401e08804c3501474de847e454d12f98ae938eb83cfc678e1b4a830" \
  "442197a929490256ff5ad1fe74652950214550b500f083dc298414a83d578d09"

if [[ -f /opt/realtime-patch/asset_versioner.py ]]; then
  python3 /opt/realtime-patch/asset_versioner.py --build-dir /app/build --seeds B1EqPYAs.js CaoI0pp2.js
fi

bootstrap_tools_and_connections

exec bash /app/backend/start.sh "$@"
