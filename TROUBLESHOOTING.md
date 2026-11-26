# Open WebUI Portable Troubleshooting Guide

This guide covers common installation, configuration, networking, and runtime issues encountered when deploying Open WebUI against a central LiteLLM proxy.

---

## 1. Quick Diagnostic Checklist

Run these commands on the target host to assess operational health:

```bash
# 1. Check container running status and health
docker compose ps

# 2. Inspect recent Open WebUI logs
docker compose logs --tail 50 open-webui

# 3. Test Open WebUI health endpoint directly
curl -i http://localhost:3000/health

# 4. Test LiteLLM liveliness from host
curl -i $(grep LITELLM_BASE_URL .env | cut -d= -f2)/health/liveliness

# 5. Run full integration validation
python3 validate.py
```

---

## 2. Common Issues & Resolutions

### Issue 1: `Database registration failed: attempt to write a readonly database`

* **Symptom:** During installation, `register_tool.py` fails with SQLite readonly error.
* **Root Cause:** When Open WebUI initializes for the first time, its internal process creates `webui.db` with root ownership. If `register_tool.py` is executed on the host under a non-root user account, write access is denied.
* **Resolution:**
  Use container-native execution via `docker exec`:
  ```bash
  docker cp tools/ open-webui:/tmp/
  docker exec open-webui python3 /tmp/tools/register_tool.py \
      --db /app/backend/data/webui.db \
      --source /tmp/tools/speech_coach_tool.py \
      --litellm-url "$(grep LITELLM_BASE_URL .env | cut -d= -f2)" \
      --api-key "$(grep LITELLM_API_KEY .env | cut -d= -f2)"
  docker exec open-webui rm -rf /tmp/tools
  ```
  *(Note: `install.sh` in this package automatically uses this container-native execution).*

---

### Issue 2: `Health check timed out after 45s / 120s`

* **Symptom:** Initial run of `./install.sh` fails waiting for health check.
* **Root Cause:** On pristine installations with an empty data directory, Open WebUI downloads Hugging Face embedding model weights (`sentence-transformers/all-MiniLM-L6-v2`, ~120 MB) upon first boot. On slower connections, this download can take 45–90 seconds before the web server begins listening.
* **Resolution:**
  1. Inspect download progress:
     ```bash
     docker logs -f open-webui
     ```
  2. Once the log displays `Application startup complete` and `Uvicorn running on http://0.0.0.0:8080`, simply re-run `./install.sh`. The script is completely idempotent and will detect the running healthy container immediately.

---

### Issue 3: LiteLLM Authentication Fails (HTTP 401 / 403)

* **Symptom:** `validate.py` reports `[FAIL] LiteLLM Authentication` or models fail to populate in Open WebUI.
* **Root Cause:**
  1. `LITELLM_API_KEY` in `.env` is incorrect, revoked, or contains extra spaces/quotes.
  2. The LiteLLM proxy server was restarted without persistent PostgreSQL or its keys were modified.
* **Resolution:**
  1. Verify the key by running:
     ```bash
     curl -i -H "Authorization: Bearer <YOUR_KEY>" <LITELLM_BASE_URL>/v1/models
     ```
  2. If connecting from another host, ensure the key is the LiteLLM `master_key` or a valid generated virtual key (`sk-...`).
  3. Re-run `python3 configure.py --api-key "<VALID_KEY>"` and `./install.sh`.

---

### Issue 4: Docker Container Cannot Reach LiteLLM (`Connection refused`)

* **Symptom:** Host can curl `http://localhost:4000`, but Open WebUI container fails to connect.
* **Root Cause:** Inside a Docker container, `localhost` refers to the container itself, NOT the host machine.
* **Resolution:**
  - If LiteLLM is running on the **same physical host**:
    Set `LITELLM_BASE_URL=http://host.docker.internal:4000`. The template includes `extra_hosts: ["host.docker.internal:host-gateway"]` to route container requests to the host gateway.
  - If LiteLLM is on **another machine**:
    Use the actual LAN IP or hostname (e.g. `http://192.168.1.50:4000` or `https://litellm.example.com`). Never use `127.0.0.1` or `localhost` across different machines.

---

### Issue 5: Realtime Voice WebSocket Connection Fails (HTTP 403)

* **Symptom:** Clicking the Realtime Call button displays "Call disconnected" or WebSocket closes immediately.
* **Root Cause:**
  LiteLLM requires the `model` query parameter during the WebSocket handshake (`ws://<host>:<port>/v1/realtime?model=realtime-voice`). If `AUDIO_REALTIME_MODEL` is missing or blank, LiteLLM rejects the handshake with HTTP 403.
* **Resolution:**
  Verify `.env` has:
  ```bash
  AUDIO_REALTIME_ENABLED=true
  AUDIO_REALTIME_PROVIDER=openai
  AUDIO_REALTIME_AUTH_TYPE=api_key
  AUDIO_REALTIME_OPENAI_API_BASE_URL=${LITELLM_BASE_URL}/v1
  AUDIO_REALTIME_OPENAI_API_KEY=${LITELLM_API_KEY}
  AUDIO_REALTIME_MODEL=realtime-voice
  ```

---

### Issue 6: Speech Coach Tool Reports `502 Bad Gateway`

* **Symptom:** Invoking Speech Coach in chat returns:
  `{"error": "Failed to call speech analysis API: 502 Bad Gateway"}`
* **Root Cause:**
  LiteLLM proxy is running, but the upstream AI Gateway speech analysis service (`gateway-api:8000/v1/audio/speech-analysis`) on the central server is either restarting, busy, or unreachable from LiteLLM.
* **Resolution:**
  1. On the central AI Gateway server, verify gateway health:
     ```bash
     curl http://localhost:8000/health
     ```
  2. Verify Faster-Whisper and Piper TTS in-memory modules are initialized.
  3. Verify LiteLLM proxy routes speech analysis by running `python3 validate.py`.

---

### Issue 7: Image Models Not Appearing in Chat Model Selector

* **Symptom:** User expects diffusion models (e.g., `flux1-schnell`) in the text model dropdown.
* **Explanation:** **This is intended behavior by design!**
  Text chat models and image generation models are strictly segregated. Image models appear in **Image Generation Settings** and can be invoked with the image generation button or prompts, but do not pollute the text chat dropdown.
### Issue 8: Realtime Voice Audio Fails on Mobile Browsers (44.1 / 48 kHz or Suspended AudioContext)

* **Symptom:** Desktop realtime calls work, but mobile Safari / Chrome throws an AudioWorklet sample-rate error or plays no audio until tapped.
* **Root Cause:** Upstream Open WebUI v0.13.4 hardcodes `new AudioContext({sampleRate: 24000})`, which fails or requires gesture unlock on mobile hardware locked to 44.1/48 kHz.
* **Verification & Resolution:**
  1. Confirm the v0.13.5 compatibility patches are active in the container:
     ```bash
     python3 patches/v0.13.5/patch_openwebui_v0135.py --status
     ```
     Expected: `[PATCHED] B1EqPYAs.js (sha256=9e5e7c554ede4572644a53c7b839ab9e371b91a6a3194161d6734c6863f2c0e9, ...)` plus `[PATCHED]` for `ask_user.py`, `builtin.py`, `middleware.py`, `headers.py`, `audio_init.py`, and `audio_realtime.py`.
  2. Check startup hook logs (`docker logs open-webui | grep v0135-patch`) and ensure `docker-compose.yml` mounts all 7 patch files plus `openwebui_v0135_entrypoint.sh` from `./patches/v0.13.5/`.
  3. If `validate.py` fails the bundle checksum check on a non-v0.13.5 image, verify whether the container image tag was changed from `ghcr.io/open-webui/open-webui:v0.13.5`; the patcher intentionally refuses to overwrite unknown bundles.
