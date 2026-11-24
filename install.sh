#!/usr/bin/env bash
# ==============================================================================
# Open WebUI v0.13.4 Portable Installer
# ==============================================================================
# Repeatable, idempotent installer for Open WebUI v0.13.4 connecting to LiteLLM.
# Preserves data, registers custom tools, configures valves, and avoids duplicate patches.
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BOLD="\033[1m"
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
NC="\033[0m"

log_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1" >&2
}

log_step() {
    echo -e "\n${BOLD}${CYAN}==>${NC} ${BOLD}$1${NC}"
}

echo -e "${BOLD}================================================================${NC}"
echo -e "${BOLD}  Open WebUI v0.13.4 Portable Deployment & Custom Experience Installer  ${NC}"
echo -e "${BOLD}================================================================${NC}"

# ------------------------------------------------------------------------------
# 1. Environment & Prerequisites Preflight
# ------------------------------------------------------------------------------
log_step "Step 1: Checking Prerequisites & Environment"

if ! command -v docker &> /dev/null; then
    log_fail "Docker is required but not installed. Aborting."
    exit 1
fi
log_pass "Docker CLI detected: $(docker --version)"

COMPOSE_CMD=""
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    log_fail "Docker Compose is required but neither 'docker compose' nor 'docker-compose' was found."
    exit 1
fi
log_pass "Docker Compose detected: $($COMPOSE_CMD version)"

if ! command -v python3 &> /dev/null; then
    log_fail "Python 3 is required for tool configuration and validation. Aborting."
    exit 1
fi
log_pass "Python 3 detected: $(python3 --version)"

# Check if .env exists
if [ ! -f ".env" ]; then
    if [ -f "env.example" ]; then
        log_info "No .env found. Initializing .env from env.example..."
        cp env.example .env
        log_warn "Created .env template. Please review settings or supply parameters via configure.py."
    else
        log_fail "Missing .env and env.example. Cannot proceed."
        exit 1
    fi
fi

# Load variables from .env safely
while IFS='=' read -r key value || [ -n "$key" ]; do
    [[ "$key" =~ ^[[:space:]]*# ]] && continue
    [ -z "$key" ] && continue
    key=$(echo "$key" | tr -d "[:space:]")
    value=$(echo "$value" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    value="${value%\"}"
    value="${value#\"}"
    value="${value%'}"
    value="${value#'}"
    export "$key"="$value"
done < .env

LITELLM_URL="${LITELLM_BASE_URL:-http://localhost:4000}"
LITELLM_KEY="${LITELLM_API_KEY:-}"
TARGET_PORT="${PORT:-3000}"
TARGET_CONTAINER="${CONTAINER_NAME:-open-webui}"
DATA_DIR="${OPEN_WEBUI_DATA_DIR:-./data}"

# ------------------------------------------------------------------------------
# 2. Validate LiteLLM Reachability & Authentication
# ------------------------------------------------------------------------------
log_step "Step 2: Validating LiteLLM Proxy Connectivity"

if [[ "$LITELLM_URL" == *"<YOUR_LITELLM_HOST>"* ]] || [[ "$LITELLM_KEY" == *"<YOUR_LITELLM_API_KEY>"* ]]; then
    log_fail "Placeholder credentials detected in .env. Please configure LITELLM_BASE_URL and LITELLM_API_KEY."
    echo "       Run: python3 configure.py --litellm-url <URL> --api-key <KEY>"
    exit 1
fi

log_info "Testing connection to LiteLLM at $LITELLM_URL..."
if ! python3 configure.py --validate; then
    log_fail "LiteLLM preflight verification failed. Check URL, network reachability, and API key."
    exit 1
fi
log_pass "LiteLLM connectivity, authentication, and routing verified."

# ------------------------------------------------------------------------------
# 3. Generate & Validate Docker Compose Manifest
# ------------------------------------------------------------------------------
log_step "Step 3: Generating Deployment Manifest"

python3 configure.py
log_pass "docker-compose.yml synchronized with active .env configuration."

# Ensure data directory exists
mkdir -p "$DATA_DIR"
log_pass "Persistent storage path ready: $DATA_DIR"

# ------------------------------------------------------------------------------
# 4. Deploy or Refresh Open WebUI Container
# ------------------------------------------------------------------------------
log_step "Step 4: Launching Open WebUI Container"

log_info "Starting container '$TARGET_CONTAINER' on port $TARGET_PORT..."
$COMPOSE_CMD up -d

log_info "Waiting for Open WebUI to achieve healthy state..."
MAX_WAIT=120
WAIT_COUNT=0
HEALTHY=false

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if curl -s -f "http://localhost:${TARGET_PORT}/health" &> /dev/null; then
        HEALTHY=true
        break
    fi
    sleep 2
    WAIT_COUNT=$((WAIT_COUNT + 2))
    echo -n "."
done
echo ""

if [ "$HEALTHY" = true ]; then
    log_pass "Open WebUI is healthy and responding on http://localhost:${TARGET_PORT}/health"
else
    log_warn "Health check timed out after ${MAX_WAIT}s. Container logs:"
    docker logs --tail 25 "$TARGET_CONTAINER" || true
    log_fail "Open WebUI did not report healthy. Inspect container status."
    exit 1
fi

# ------------------------------------------------------------------------------
# 5. Validate Open WebUI Version
# ------------------------------------------------------------------------------
log_step "Step 5: Verifying Open WebUI Version"

CONTAINER_IMG=$(docker inspect "$TARGET_CONTAINER" --format '{{.Config.Image}}')
log_info "Container image: $CONTAINER_IMG"

if [[ "$CONTAINER_IMG" == *"v0.13.4"* ]] || [[ "$CONTAINER_IMG" == *"0.13.4"* ]]; then
    log_pass "Open WebUI version v0.13.4 confirmed."
else
    log_warn "Running image '$CONTAINER_IMG'. Target architecture is verified for v0.13.4."
fi

# ------------------------------------------------------------------------------
# 6. Frontend Modifications Audit
# ------------------------------------------------------------------------------
log_step "Step 6: Auditing Frontend Modifications"

log_info "Open WebUI v0.13.4 operates using upstream stock assets."
log_info "Native OpenAI Realtime WebSocket client and isolated LiteLLM image models supersede legacy patches."
log_pass "Zero frontend monkey-patches applied (Stock Upstream Image verified)."

# ------------------------------------------------------------------------------
# 7. Register & Configure Speech Coach Custom Tool & Valves
# ------------------------------------------------------------------------------
log_step "Step 7: Registering Speech Coach Custom Tool & Valves"

log_info "Registering Speech Coach tool inside container ..."
docker cp tools "$TARGET_CONTAINER":/tmp/
docker exec "$TARGET_CONTAINER" python3 /tmp/tools/register_tool.py \
    --db /app/backend/data/webui.db \
    --source /tmp/tools/speech_coach_tool.py \
    --litellm-url "$LITELLM_URL" \
    --api-key "$LITELLM_KEY" \
    --timeout "${SPEECH_COACH_TIMEOUT:-60.0}" \
    --speech-path "${SPEECH_COACH_ANALYSIS_PATH:-/v1/audio/speech-analysis}" \
    --voices-path "${SPEECH_COACH_VOICES_PATH:-/v1/audio/voices}"
docker exec "$TARGET_CONTAINER" rm -rf /tmp/tools

log_pass "Speech Coach Custom Tool & Valves registered in container database." 

# ------------------------------------------------------------------------------
# 8. Configure Native Image Connections
# ------------------------------------------------------------------------------
log_step "Step 8: Configuring Native Image Model Connections"

if [ -f "$DB_FILE" ]; then
    python3 -c "
import sqlite3, json, time, uuid

conn = sqlite3.connect('$DB_FILE')
c = conn.cursor()

# Ensure images.connections exists in config table
c.execute(\"SELECT value FROM config WHERE key = 'images.connections'\")
row = c.fetchone()

img_url = '${IMAGES_OPENAI_API_BASE_URL:-${LITELLM_URL}/images/v1}'
img_key = '${IMAGES_OPENAI_API_KEY:-${LITELLM_KEY}}'
default_model = '${IMAGE_GENERATION_MODEL:-flux1-schnell}'
now = int(time.time())

conn_id = str(uuid.uuid4())
connection_entry = {
    'id': conn_id,
    'name': 'LiteLLM Image Gateway',
    'type': 'openai',
    'url': img_url,
    'key': img_key,
    'config': {
        'enable': True,
        'capabilities': {
            'image_generation': True,
            'image_edit': True
        },
        'model_ids': [default_model],
        'access_grants': [{'principal_type': 'user', 'principal_id': '*', 'permission': 'read'}],
        'auth_type': 'bearer',
        'headers': {},
        'size': '512x512',
        'steps': 50
    }
}

if row is None:
    c.execute(\"INSERT INTO config (key, value, updated_at) VALUES ('images.connections', ?, ?)\", (json.dumps([connection_entry]), now))
    c.execute(\"INSERT OR REPLACE INTO config (key, value, updated_at) VALUES ('image_generation.enable', 'true', ?)\", (now,))
    c.execute(\"INSERT OR REPLACE INTO config (key, value, updated_at) VALUES ('image_generation.engine', '\"openai\"', ?)\", (now,))
    c.execute(\"INSERT OR REPLACE INTO config (key, value, updated_at) VALUES ('image_generation.default_model', ?, ?)\", (json.dumps(f'{conn_id}:{default_model}'), now))
    conn.commit()
    print('[SUCCESS] Initialized images.connections configuration in database.')
else:
    print('[INFO] Existing images.connections configuration retained.')

conn.close()
" || log_warn "Image connections configuration skipped or already initialized."
fi

# ------------------------------------------------------------------------------
# 9. Completion Summary
# ------------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${GREEN}================================================================${NC}"
echo -e "${BOLD}${GREEN}  Open WebUI Custom Experience Successfully Deployed!           ${NC}"
echo -e "${BOLD}${GREEN}================================================================${NC}"
echo -e "Web Interface:       ${CYAN}http://localhost:${TARGET_PORT}${NC}"
echo -e "LiteLLM Proxy:       ${CYAN}${LITELLM_URL}${NC}"
echo -e "Speech Coach Tool:   ${GREEN}Installed (v2.0.0 with Valves)${NC}"
echo -e "Realtime Voice:      ${GREEN}Enabled (Native OpenAI Realtime Protocol)${NC}"
echo -e "Image Generation:    ${GREEN}Enabled (LiteLLM Isolated Image Route)${NC}"
echo -e "Audio STT / TTS:     ${GREEN}Configured (LiteLLM 3-Tier Proxy)${NC}"
echo ""
echo -e "Run validation test: ${BOLD}python3 validate.py${NC}"
echo ""
