# Open WebUI Upgrade Runbook & Maintenance Guide

This runbook describes the procedure for upgrading Open WebUI container images while retaining all custom tools, valves, image connections, and user data.

---

## 1. Upgrade Philosophy & Compatibility

Because our deployment uses **stock container images with zero source-tree patch mounts**, upgrading Open WebUI is vastly simplified:

1. **No Source Patch Merge Conflicts:** No JS bundles or Python router files in `/app/build` or `/app/backend` are monkey-patched. Upgrading does not require reapplying diffs to minified chunks.
2. **Database Backward Compatibility:** Open WebUI uses Alembic for automatic schema migrations upon startup.
3. **Persistent Custom Tools:** Custom tools (`speech_coach`) and their Valves reside in `webui.db` inside the persistent volume (`OPEN_WEBUI_DATA_DIR`).
4. **Idempotent Re-registration:** Running `install.sh` or `register_tool.py` ensures that any new parameters or updated tool code are safely synced without creating duplicates.

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
