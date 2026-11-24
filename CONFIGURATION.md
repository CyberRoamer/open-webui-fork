# Open WebUI Portable Configuration Reference

This guide details all configurable parameters supported by the Open WebUI Portable Deployment package, including environment variables, tool Valves, and remote HTTPS setups.

---

## 1. Master Configuration Matrix

| Variable Name | Default Value | Description | Component Scope |
| :--- | :--- | :--- | :--- |
| `LITELLM_BASE_URL` | `http://<YOUR_LITELLM_HOST>:4000` | Ingress base URL of the central LiteLLM proxy server. | System Core |
| `LITELLM_API_KEY` | `<YOUR_LITELLM_API_KEY>` | LiteLLM virtual key or master key used for authenticating requests. | System Core |
| `OPENAI_API_BASE_URL` | `${LITELLM_BASE_URL}/v1` | Endpoint for text/chat completions and model discovery (`GET /v1/models`). | Text Inference |
| `OPENAI_API_KEY` | `${LITELLM_API_KEY}` | Auth token forwarded for chat completions. | Text Inference |
| `ENABLE_IMAGE_GENERATION` | `true` | Enables Open WebUI's native image generation subsystem. | Image Studio |
| `IMAGE_GENERATION_ENGINE`| `openai` | Protocol used for image generation (`openai` standard). | Image Studio |
| `IMAGES_OPENAI_API_BASE_URL`| `${LITELLM_BASE_URL}/images/v1` | Dedicated LiteLLM route returning only image models and routing generations. | Image Studio |
| `IMAGES_OPENAI_API_KEY` | `${LITELLM_API_KEY}` | Auth token for image generation and discovery. | Image Studio |
| `IMAGE_GENERATION_MODEL` | `flux1-schnell` | Default checkpoint preselected in image generation controls. | Image Studio |
| `IMAGE_URL_RESPONSE_MODELS_REGEX_PATTERN` | `.*` | Regex matching models that return image URLs rather than base64. | Image Studio |
| `ENABLE_IMAGE_EDIT` | `true` | Enables image-to-image / inpainting editing mode. | Image Studio |
| `IMAGE_EDIT_ENGINE` | `openai` | Engine used for image editing operations. | Image Studio |
| `IMAGES_EDIT_OPENAI_API_BASE_URL` | `${LITELLM_BASE_URL}/images/v1` | Dedicated LiteLLM route for image editing (prevents default `api.openai.com` fallback). | Image Studio |
| `IMAGES_EDIT_OPENAI_API_KEY` | `${LITELLM_API_KEY}` | Auth token for image editing requests. | Image Studio |
| `IMAGE_EDIT_MODEL` | `flux1-schnell` | Default model for image editing. | Image Studio |
| `AUDIO_STT_ENGINE` | `openai` | Turn-based Speech-to-Text backend engine type. | Audio STT |
| `AUDIO_STT_OPENAI_API_BASE_URL` | `${LITELLM_BASE_URL}/v1` | Base URL for STT transcriptions (`POST /v1/audio/transcriptions`). | Audio STT |
| `AUDIO_STT_OPENAI_API_KEY` | `${LITELLM_API_KEY}` | Auth token for STT requests. | Audio STT |
| `AUDIO_STT_MODEL` | `whisper-1` | Model identifier dispatched to Faster-Whisper. | Audio STT |
| `AUDIO_TTS_ENGINE` | `openai` | Turn-based Text-to-Speech backend engine type. | Audio TTS |
| `AUDIO_TTS_OPENAI_API_BASE_URL` | `${LITELLM_BASE_URL}/v1` | Base URL for speech synthesis (`POST /v1/audio/speech`). | Audio TTS |
| `AUDIO_TTS_OPENAI_API_KEY` | `${LITELLM_API_KEY}` | Auth token for TTS requests. | Audio TTS |
| `AUDIO_TTS_MODEL` | `tts-1` | Model identifier dispatched to Piper TTS. | Audio TTS |
| `AUDIO_TTS_VOICE` | `alloy` | Default voice identifier. | Audio TTS |
| `AUDIO_REALTIME_ENABLED` | `true` | Enables low-latency full-duplex realtime voice calls. | Realtime Voice |
| `AUDIO_REALTIME_PROVIDER`| `openai` | Realtime voice protocol provider (`openai`). | Realtime Voice |
| `AUDIO_REALTIME_AUTH_TYPE` | `api_key` | Authentication mode for realtime connections. | Realtime Voice |
| `AUDIO_REALTIME_OPENAI_API_BASE_URL` | `${LITELLM_BASE_URL}/v1` | Base URL used to construct WebSocket URL (`ws(s)://.../v1/realtime`). | Realtime Voice |
| `AUDIO_REALTIME_OPENAI_API_KEY` | `${LITELLM_API_KEY}` | Auth token for realtime WebSocket handshake. | Realtime Voice |
| `AUDIO_REALTIME_MODEL` | `realtime-voice` | Model identifier passed to LiteLLM for realtime dispatch. | Realtime Voice |
| `AUDIO_REALTIME_VOICE` | `en_US-lessac-medium` | Piper voice used during realtime conversations. | Realtime Voice |
| `AUDIO_REALTIME_TRANSCRIPTION_MODEL` | `whisper-1` | STT model used for realtime transcription. | Realtime Voice |
| `SPEECH_COACH_ANALYSIS_PATH` | `/v1/audio/speech-analysis` | API path for Speech Coach audio analysis. | Speech Coach |
| `SPEECH_COACH_VOICES_PATH` | `/v1/audio/voices` | API path for multilingual voice catalog. | Speech Coach |
| `SPEECH_COACH_TIMEOUT` | `60.0` | Timeout in seconds for speech analysis requests. | Speech Coach |
| `PORT` | `3000` | Host port on which Open WebUI listens. | Host Binding |
| `WEBUI_NAME` | `Open WebUI` | Brand title displayed in the top bar. | Customization |
| `OPEN_WEBUI_DATA_DIR` | `./data` | Host directory mounted to `/app/backend/data`. | Storage |
| `CONTAINER_NAME` | `open-webui` | Name of the Docker container. | Runtime |

---

## 2. Speech Coach Valves Configuration

Open WebUI tools use **Valves** for dynamic, user-configurable parameters that can be changed through the WebUI without code modifications.

### Valves Schema (`speech_coach_tool.py`)

```python
class Valves(BaseModel):
    litellm_base_url: str = Field(
        default="http://litellm:4000",
        description="Base URL for the LiteLLM proxy instance (e.g. http://litellm:4000 or https://ai.example.com).",
    )
    speech_analysis_path: str = Field(
        default="/v1/audio/speech-analysis",
        description="API endpoint path for Speech Coach audio analysis.",
    )
    voices_path: str = Field(
        default="/v1/audio/voices",
        description="API endpoint path for TTS voices and language catalog.",
    )
    api_key: str = Field(
        default="",
        description="API key for LiteLLM proxy authentication. If left blank, falls back to server environment variables.",
    )
    timeout: float = Field(
        default=60.0,
        description="Request timeout in seconds for speech analysis and catalog requests.",
    )
```

### Precedence Order

When making outbound requests, the Speech Coach tool resolves credentials and endpoints as follows:
1. **Valves `api_key`**: If explicitly set in the tool settings UI, this takes first priority.
2. **Container `LITELLM_MASTER_KEY`**: Sourced from the container environment.
3. **Container `IMAGES_OPENAI_API_KEY`**: Sourced from the container environment.
4. **Container `OPENAI_API_KEY`**: Fallback from the container environment.

This ensures that administrators can change the LiteLLM key globally via `.env` without needing to reconfigure individual tool valves, while still allowing per-instance overrides.

---

## 3. Remote HTTPS Deployment Example

To connect Open WebUI to a LiteLLM proxy deployed behind an HTTPS reverse proxy (e.g., Cloudflare, NGINX, or Traefik with TLS):

### Example `.env` Configuration

```bash
# LiteLLM HTTPS Endpoint
LITELLM_BASE_URL=https://litellm.example.com
LITELLM_API_KEY=sk-litellm-prod-secure-virtual-key-2026

# Derived Endpoints
OPENAI_API_BASE_URL=https://litellm.example.com/v1
OPENAI_API_KEY=sk-litellm-prod-secure-virtual-key-2026

IMAGES_OPENAI_API_BASE_URL=https://litellm.example.com/images/v1
IMAGES_OPENAI_API_KEY=sk-litellm-prod-secure-virtual-key-2026

AUDIO_STT_OPENAI_API_BASE_URL=https://litellm.example.com/v1
AUDIO_STT_OPENAI_API_KEY=sk-litellm-prod-secure-virtual-key-2026

AUDIO_TTS_OPENAI_API_BASE_URL=https://litellm.example.com/v1
AUDIO_TTS_OPENAI_API_KEY=sk-litellm-prod-secure-virtual-key-2026

AUDIO_REALTIME_OPENAI_API_BASE_URL=https://litellm.example.com/v1
AUDIO_REALTIME_OPENAI_API_KEY=sk-litellm-prod-secure-virtual-key-2026

# Instance Settings
PORT=443
WEBUI_NAME="Global Enterprise AI Studio"
OPEN_WEBUI_DATA_DIR=/var/lib/open-webui/data
CONTAINER_NAME=open-webui-prod
```

### Applying with `configure.py`

```bash
python3 configure.py \
    --litellm-url "https://litellm.example.com" \
    --api-key "sk-litellm-prod-secure-virtual-key-2026" \
    --port 443 \
    --webui-name "Global Enterprise AI Studio" \
    --data-dir "/var/lib/open-webui/data"
```

Then deploy:
```bash
./install.sh
```

---

## 4. Security & Credential Isolation

To ensure complete credential isolation:
- **Never expose `GATEWAY_API_KEY`:** Open WebUI must never be given `GATEWAY_API_KEY`. Only LiteLLM uses this key to talk to the AI Gateway.
- **Never use internal container names:** The target host cannot reach `gateway-api:8000` or `litellm:4000` unless on the same Docker bridge network. Use external DNS, host IPs, or domain names.
- **Client Bundle Isolation:** Open WebUI's client-facing browser bundles contain only session tokens; all outbound API keys remain server-side inside the container.
- **Realtime Mobile Patch Verification:** `docker-compose.yml.template` mounts `patches/v0.13.4/BnHPywC-.js` and `patches/v0.13.4/openwebui_realtime_entrypoint.sh` read-only at `/opt/realtime-patch/`. At container startup, the entrypoint checks SHA-256 fingerprints (`d2359a68...` upstream v0.13.4, `d5e4d07c...` patched), backs up `.orig`, stages atomically, and refuses to overwrite unknown upstream bundles.
