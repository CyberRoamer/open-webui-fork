# Deploying Open WebUI Portable from GitHub (Coolify / Dockge / Portainer)

This repository includes a self-contained [`Dockerfile`](Dockerfile) and [`docker-compose.coolify.yml`](docker-compose.coolify.yml) so you can deploy and upgrade Open WebUI directly from GitHub without SSH access or manual script runs.

---

## Option A: Coolify Dockerfile Build Pack (Recommended)

1. In Coolify, create a **New Resource -> Public/Private Repository (GitHub)**.
2. Set:
   - **Build Pack:** `Dockerfile`
   - **Dockerfile Location:** `/Dockerfile`
   - **Port Exposes:** `8080`
3. Under **Persistent Storage**, add a volume mount:
   - **Destination Path:** `/app/backend/data`
4. Under **Environment Variables**, set at minimum:
   - `LITELLM_BASE_URL` = `https://litellm.example.com` (or internal URL reachable by Coolify)
   - `LITELLM_API_KEY` = `sk-...`
   - `OPENAI_API_BASE_URL` = `${LITELLM_BASE_URL}/v1`
   - `OPENAI_API_KEY` = `${LITELLM_API_KEY}`
   - `IMAGES_OPENAI_API_BASE_URL` = `${LITELLM_BASE_URL}/images/v1`
   - `IMAGES_OPENAI_API_KEY` = `${LITELLM_API_KEY}`
   - `ENABLE_IMAGE_GENERATION` = `true`
   - `IMAGE_GENERATION_ENGINE` = `openai`
   - `IMAGE_GENERATION_MODEL` = `flux1-schnell`
   - `IMAGE_URL_RESPONSE_MODELS_REGEX_PATTERN` = `.*`
   - `AUDIO_STT_ENGINE` = `openai`
   - `AUDIO_STT_OPENAI_API_BASE_URL` = `${LITELLM_BASE_URL}/v1`
   - `AUDIO_STT_OPENAI_API_KEY` = `${LITELLM_API_KEY}`
   - `AUDIO_STT_MODEL` = `whisper-1`
   - `AUDIO_TTS_ENGINE` = `openai`
   - `AUDIO_TTS_OPENAI_API_BASE_URL` = `${LITELLM_BASE_URL}/v1`
   - `AUDIO_TTS_OPENAI_API_KEY` = `${LITELLM_API_KEY}`
   - `AUDIO_TTS_MODEL` = `tts-1`
   - `AUDIO_TTS_VOICE` = `alloy`
   - `AUDIO_REALTIME_ENABLED` = `true`
   - `AUDIO_REALTIME_PROVIDER` = `openai`
   - `AUDIO_REALTIME_AUTH_TYPE` = `api_key`
   - `AUDIO_REALTIME_OPENAI_API_BASE_URL` = `${LITELLM_BASE_URL}/v1`
   - `AUDIO_REALTIME_OPENAI_API_KEY` = `${LITELLM_API_KEY}`
   - `AUDIO_REALTIME_MODEL` = `realtime-voice`
   - `AUDIO_REALTIME_VOICE` = `en_US-lessac-medium`
   - `AUDIO_REALTIME_TRANSCRIPTION_MODEL` = `whisper-1`
   - `WEBUI_NAME` = `Open WebUI`
5. Click **Deploy**.
   - At image build time, `Dockerfile` verifies upstream Open WebUI SHA-256 fingerprints and bakes in the `v0.13.5` mobile realtime (`B1EqPYAs.js`), `ask_user` (`ask_user.py`, `builtin.py`), and voice pipeline (`middleware.py`, `headers.py`, `audio_init.py`, `audio_realtime.py`) patches.
   - At startup, `coolify_entrypoint.sh` automatically registers the **Speech Coach** tool and syncs `images.connections` in `/app/backend/data/webui.db` once Open WebUI reports healthy.

---

## Option B: Coolify Docker Compose Build Pack

1. In Coolify, select **Build Pack:** `Docker Compose`.
2. Set **Docker Compose Location:** `/docker-compose.coolify.yml`.
3. Set only **`LITELLM_BASE_URL`** and **`LITELLM_API_KEY`** in Coolify's Environment Variables UI (all derived endpoints default automatically inside `docker-compose.coolify.yml`).
4. Assign your HTTPS domain in Coolify (needed for mobile microphone access in Realtime Voice) and click **Deploy**.

---

## Upgrading Open WebUI via GitHub

1. Update the version tag & verified patch artifacts in this repository.
2. Push to `main` (or trigger **Redeploy** / GitHub webhook in Coolify).
3. Coolify rebuilds the image, preserves `/app/backend/data`, runs Alembic DB migrations automatically, and re-syncs tools on boot.
