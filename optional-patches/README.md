# Open WebUI Optional Patches & Architectural Evolution

This directory contains legacy and optional patch artifacts from earlier iterations of our Open WebUI deployment (specifically Open WebUI v0.11.1), retained for auditability, historical reference, and emergency backward compatibility.

> [!IMPORTANT]
> **Production Open WebUI v0.13.4 retires all legacy v0.11.1 backend/frontend patches** (`audio.py`, `images.py`, `D5GoHi-U.js`, `34.DRvNJD_W.js`, `fwivdHaq.js`).
> For v0.13.4 mobile realtime voice compatibility (44.1/48 kHz native AudioContext resampling + user-gesture audio unlock), the active deployment uses the single SHA-256-verified patch in `patches/v0.13.4/` (`BnHPywC-.js` + `openwebui_realtime_entrypoint.sh`). All model separation, speech coaching, realtime signaling, image generation, and audio routing are mediated cleanly through LiteLLM.

---

## 1. Architectural Evolution: v0.11.1 Patches vs. v0.13.4 Native Capabilities

| Subsystem / Feature | Legacy Approach (v0.11.1 Patches) | Modern Approach (v0.13.4 Native + LiteLLM) |
| :--- | :--- | :--- |
| **Realtime Voice Calls** | Frontend monkey-patch in `D5GoHi-U.js` injecting custom `RealtimeVoiceClient` class connecting to `/api/v1/audio/realtime/ws`. | **Native + Mobile Resampler Patch:** Built-in OpenAI Realtime API bridge (`routers/audio/realtime.py`) routing via LiteLLM (`ws://<litellm>:4000/v1/realtime?model=realtime-voice`), plus SHA-256-verified `patches/v0.13.4/BnHPywC-.js` for native 44.1/48 kHz AudioWorklet resampling and mobile gesture unlock. |
| **Image Model Discovery** | Frontend patches `34.DRvNJD_W.js` and `fwivdHaq.js` modifying DOM dropdown selectors and API client model forwarding. | **3-Tier Proxy Separation:** LiteLLM isolates routes: `GET /images/v1/models` returns strictly image models; `GET /v1/models` returns strictly text chat models. Open WebUI natively connects to `IMAGES_OPENAI_API_BASE_URL`. |
| **Image Generation Backend** | Patch in `images.py` overriding backend router logic and query routing. | **Native Multi-Engine:** Open WebUI v0.13.4 natively supports multiple image connection configurations via `images.connections` and standard OpenAI image endpoints. |
| **Speech Coach Tool** | Python tool connecting directly to internal gateway `http://gateway-api:8000/v1`. | **Portable Custom Tool (v2.0.0):** Native Open WebUI Custom Tool utilizing `Valves` (`litellm_base_url`, `speech_analysis_path`, `voices_path`, `api_key`, `timeout`) routing through LiteLLM proxy (`/v1/audio/speech-analysis` & `/v1/audio/voices`). |
| **Audio STT & TTS** | Patch in `audio.py` for routing. | **Native Endpoints:** Standard OpenAI-compatible `/v1/audio/transcriptions` and `/v1/audio/speech` configured through standard environment variables. |

---

## 2. Inventory of Archived Legacy Patches (`legacy_v0.11.1/`)

1. **`34.DRvNJD_W.js`**
   - *Target:* Open WebUI v0.11.1 frontend bundle chunk `_app/immutable/chunks/34.DRvNJD_W.js`.
   - *Purpose:* Injected model-selector DOM dropdown into the image generation settings and chat input interface.
   - *Status:* **Retired.** Open WebUI v0.13.4 includes native image model selection in the chat and settings UI.

2. **`fwivdHaq.js`**
   - *Target:* Open WebUI v0.11.1 frontend bundle chunk `_app/immutable/chunks/fwivdHaq.js`.
   - *Purpose:* Ensured client-side API requests included explicit model parameters for image requests.
   - *Status:* **Retired.** Open WebUI v0.13.4 client-side code natively forwards selected model IDs.

3. **`D5GoHi-U.js`**
   - *Target:* Open WebUI v0.11.1 frontend bundle chunk `_app/immutable/chunks/D5GoHi-U.js` (CallOverlay).
   - *Purpose:* Embedded `RealtimeVoiceClient` providing 16kHz PCM audio streaming, Silero VAD coordination, streaming playback deltas, and client-side barge-in cancellation.
   - *Status:* **Retired.** Open WebUI v0.13.4 possesses built-in realtime audio call support connecting to OpenAI-compatible realtime WebSocket servers.

4. **`images.py`**
   - *Target:* Open WebUI v0.11.1 backend router `open_webui/routers/images.py`.
   - *Purpose:* Custom image generation handling and model override logic.
   - *Status:* **Retired.** Open WebUI v0.13.4 includes updated image router supporting connection pools (`images.connections`).

5. **`audio.py`**
   - *Target:* Open WebUI v0.11.1 backend router `open_webui/routers/audio.py`.
   - *Purpose:* Experimental audio routing and speech coach parameter handling.
   - *Status:* **Retired.** Speech coaching is now cleanly decoupled into a portable custom tool (`speech_coach_tool.py`), eliminating all backend router edits.

---

## 3. Realtime Voice Fallback Patcher (`realtime_voice/patch_openwebui_realtime.py`)

If you are forced to deploy against an older Open WebUI installation (v0.11.x) that lacks native OpenAI Realtime API support, this utility script can patch the CallOverlay chunk in that target build:

```bash
# Check if target file requires patching
python3 optional-patches/realtime_voice/patch_openwebui_realtime.py --check

# Apply RealtimeVoiceClient patch
python3 optional-patches/realtime_voice/patch_openwebui_realtime.py --patch

# Rollback to unpatched .orig backup
python3 optional-patches/realtime_voice/patch_openwebui_realtime.py --rollback
```

For Open WebUI v0.13.4+, **do not run this script**. Standard environment configuration is all that is required.
