# Open WebUI Upgrade Runbook & Maintenance Guide

This runbook describes the procedure for upgrading Open WebUI container images while retaining all custom tools, valves, image connections, and user data.

---

## 1. Upgrade Philosophy & Compatibility

Open WebUI v0.13.4 runs on the pinned upstream image `ghcr.io/open-webui/open-webui:v0.13.4` paired with a **single SHA-256-verified frontend compatibility patch** (`patches/v0.13.4/BnHPywC-.js`) for mobile realtime voice (44.1/48 kHz native AudioContext resampling and user-gesture audio unlock):

1. **Automatic Startup Patching & Upstream Safety:** `patches/v0.13.4/openwebui_realtime_entrypoint.sh` checks the container bundle's SHA-256 at boot. It patches only the exact known v0.13.4 bundle (`d2359a68d087ee9a7ab52895653e4f27f40b64f90f0ede8a0eb5c77729dbf33c` → `d5e4d07cfd5d13b4dfe0aa0d0dcb261ef2296d0ca6484f8ffcc7ac89187f67ab`), backs up `.orig`, and swaps atomically. When upgrading to a newer Open WebUI release (e.g., `v0.14.0+`) where `BnHPywC-.js` is absent or has a different hash, the entrypoint **refuses to overwrite** any unexpected bundle.
2. **Legacy v0.11.1 Patches Retired:** No Python routers (`audio.py`, `images.py`) or v0.11.1 JS chunks (`D5GoHi-U.js`, `34.DRvNJD_W.js`, `fwivdHaq.js`) are patched in v0.13.4.
3. **Database Backward Compatibility:** Open WebUI uses Alembic for automatic schema migrations upon startup.
4. **Persistent Custom Tools:** Custom tools (`speech_coach` v2.0.0) and their Valves reside in `webui.db` inside the persistent volume (`OPEN_WEBUI_DATA_DIR`).
5. **Idempotent Re-registration:** Running `install.sh` or `register_tool.py` safely syncs tool code, metadata (`2.0.0`), and Valves without creating duplicates.

---

## 2. Pre-Upgrade Backup Procedure

Always perform a snapshot backup of your persistent data before initiating an upgrade:

```bash
# 1. Navigate to the portable package directory
cd /opt/open-webui-portable

# 2. Identify your data directory
DATA_DIR=$(grep OPEN_WEBUI_DATA_DIR .env | cut -d= -f2 || echo "./data")
BACKUP_DIR="./backups/backup_$(date +%Y%m%d_%H%M%S)"

# 3. Create timestamped backup
mkdir -p "$BACKUP_DIR"
cp -r "$DATA_DIR/webui.db" "$BACKUP_DIR/"
cp -r "$DATA_DIR/uploads" "$BACKUP_DIR/" 2>/dev/null || true
cp .env "$BACKUP_DIR/"
cp docker-compose.yml "$BACKUP_DIR/"

echo "Backup created at $BACKUP_DIR"
```

---

## 3. Step-by-Step Upgrade Procedure

### Step 1: Update the Target Image Tag

In `docker-compose.yml` (or `docker-compose.yml.template`), update the image tag:

```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:<NEW_VERSION_TAG>
    # e.g., ghcr.io/open-webui/open-webui:v0.14.0
```

### Step 2: Pull the New Image

```bash
docker compose pull
```

### Step 3: Restart the Service

```bash
docker compose up -d
```

### Step 4: Monitor Container Startup & Database Migration

Open WebUI automatically runs Alembic database migrations during initial startup:

```bash
docker compose logs -f open-webui
```

Look for:
```
INFO: Applying alembic migrations...
INFO: Migrations complete.
INFO: Application startup complete.
```

### Step 5: Verify Tool & Valves State

Execute `register_tool.py` in check mode:

```bash
python3 tools/register_tool.py --db "$DATA_DIR/webui.db" --check
```

If needed, update the tool to the latest canonical version:
```bash
python3 tools/register_tool.py \
    --db "$DATA_DIR/webui.db" \
    --litellm-url "$(grep LITELLM_BASE_URL .env | cut -d= -f2)" \
    --api-key "$(grep LITELLM_API_KEY .env | cut -d= -f2)"
```

### Step 6: Execute Integration Validation

Run the 14-point validation suite to verify complete functionality:

```bash
python3 validate.py
```

All 14 tests must pass:
- Text completion
- Image model discovery & generation routing
- Audio STT / TTS
- Speech Coach speaking practice & pronunciation assessment
- Realtime voice WebSocket handshake

---

## 4. Rollback Procedure

### A. Rollback Only the v0.13.4 Mobile Realtime Frontend Patch (Live Container)

```bash
python3 patches/v0.13.4/patch_openwebui_v0134_realtime.py --status
python3 patches/v0.13.4/patch_openwebui_v0134_realtime.py --rollback
# Reapply if needed:
python3 patches/v0.13.4/patch_openwebui_v0134_realtime.py --patch
```
Note: `--rollback` verifies the preserved `.orig` backup (`d2359a68...`), swaps atomically, and fails nonzero if no valid original backup is available. To disable automatic patching across container recreations, remove the `entrypoint` and `/opt/realtime-patch/*` mounts from `docker-compose.yml`.

### B. Full Container & Database Rollback

If the new Open WebUI image encounters incompatibilities or bugs:

```bash
# 1. Stop the container
docker compose down

# 2. Restore database from backup
cp "$BACKUP_DIR/webui.db" "$DATA_DIR/webui.db"

# 3. Revert image tag in docker-compose.yml
# (Change back to previous known good image, e.g. v0.13.4)

# 4. Relaunch container
docker compose up -d

# 5. Verify health
curl -s http://localhost:3000/health && echo "Rollback successful"
```
