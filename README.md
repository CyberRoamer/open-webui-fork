# Open WebUI Portable Deployment Package

## 1. Overview & Architecture

This package provides a self-contained, reproducible, portable deployment of our enhanced **Open WebUI v0.13.4** environment. It enables deploying Open WebUI onto any physical or virtual system—on-premise, cloud, or developer workstation—connecting back to the **existing LiteLLM Proxy** on our central AI Gateway server.

### Target Architecture

```mermaid
flowchart LR
    subgraph Client ["Client Browser"]
        BROWSER["Web Browser / Mobile Client"]
    end

    subgraph New_Node ["New System (Target Host)"]
        direction TB
        OWUI["Open WebUI v0.13.4 (Stock Image)"]
        TOOLS["Custom Tools\n(Speech Coach v2.0.0)"]
        VALVES["Configured Valves\n(LiteLLM URL, Paths, Timeout)"]
        DATA[("Local Data Volume\n(webui.db)")]
        OWUI --- TOOLS
        TOOLS --- VALVES
        OWUI --- DATA
    end

    subgraph Gateway_Server ["AI Gateway Server (Existing Deployment)"]
        direction TB
        LITELLM["LiteLLM Proxy (:4000)\n(Auth, Model Routing & Isolation)"]
        GW["AI Gateway Core (:8000)\n(Mediation & GPU Scheduler)"]
        ENGINES["Execution Engines\n(llama-server, sd-server, Whisper, Piper, Silero VAD)"]
        
        LITELLM -->|"GATEWAY_API_KEY"| GW
        GW --> ENGINES
    end

    BROWSER -->|"HTTP :3000 / WS :3000"| OWUI
    OWUI -->|"Chat (/v1/chat/completions)\nBearer LITELLM_API_KEY"| LITELLM
    OWUI -->|"Image Discovery (/images/v1/models)\nBearer LITELLM_API_KEY"| LITELLM
    OWUI -->|"Image Generation (/images/v1/images/generations)\nBearer LITELLM_API_KEY"| LITELLM
    OWUI -->|"Turn-based Audio STT/TTS (/v1/audio/*)\nBearer LITELLM_API_KEY"| LITELLM
    OWUI -->|"Realtime Voice (WS /v1/realtime)\nBearer LITELLM_API_KEY"| LITELLM
    TOOLS -->|"Speech Analysis (/v1/audio/speech-analysis)\nBearer LITELLM_API_KEY"| LITELLM
    TOOLS -->|"Voice Catalog (/v1/audio/voices)\nBearer LITELLM_API_KEY"| LITELLM
```

### Key Architectural Tenets

1. **Zero Local Inference Infrastructure:** The target machine requires only Docker, Docker Compose, and Python 3. No GPUs, no local LLM engines (`llama.cpp`), no diffusion backends (`sd.cpp`, ComfyUI), and no local STT/TTS models are needed on the target host.
2. **Strict Security Isolation:** The target machine and its Open WebUI deployment possess **zero access to internal Gateway credentials** (`GATEWAY_API_KEY`) and zero access to internal Gateway hostnames (`gateway-api:8000`). All interactions are authenticated with LiteLLM proxy keys (`LITELLM_API_KEY`).
3. **Stock Container Images (Zero Source Patching):** Open WebUI runs strictly from the upstream, unpatched image `ghcr.io/open-webui/open-webui:v0.13.4`. Legacy monkey-patches to frontend JS chunks and backend router files have been completely eliminated.
4. **Isolated Model Discovery:** Text chat models and image generation models are strictly segregated at the proxy level. The chat model selector remains completely unpolluted by diffusion checkpoints, while image connections query the dedicated `/images/v1` routes.
5. **Configurable Endpoint Mobility:** Every endpoint, key, path, port, and timeout is configurable via `.env` or `configure.py` without modifying Python source code.

---

## 2. Inventory of Migrated Custom Capabilities

| Subsystem | Component | Implementation in Portable Package |
| :--- | :--- | :--- |
| **Speech Coach** | Pronunciation & Fluency Assessment | `tools/speech_coach_tool.py` (v2.0.0 with native Valves) providing `analyze_speech_attempt`, `get_supported_languages_and_voices`, and `start_pronunciation_practice`. |
| **Speech Coach Valves** | Endpoint Configuration | Native Open WebUI Valves exposing `litellm_base_url`, `speech_analysis_path`, `voices_path`, `api_key`, and `timeout`. Configurable dynamically via UI or database. |
| **Realtime Voice Calls** | Full-Duplex Voice Subsystem | Open WebUI v0.13.4 native OpenAI Realtime WebSocket client configured to connect to `ws://<litellm_base_url>/v1/realtime?model=realtime-voice`. Handled natively without frontend patches. |
| **Image Generation** | OpenAI-Compatible Image Pipeline | OpenAI-compatible image endpoint routing to `${LITELLM_BASE_URL}/images/v1/images/generations` with default model `flux1-schnell` and native `images.connections` registration. |
| **Image Model Separation** | Dedicated Image Catalog | Isolated discovery via `GET ${LITELLM_BASE_URL}/images/v1/models` and `GET ${LITELLM_BASE_URL}/images/v1/model/info`. |
| **Text Model Routing** | Chat Completions | Clean chat model discovery via `GET ${LITELLM_BASE_URL}/v1/models` and streaming completions via `POST ${LITELLM_BASE_URL}/v1/chat/completions`. |
| **Turn-Based Audio STT** | Faster-Whisper Transcription | OpenAI-compatible multipart audio transcription targeting `${LITELLM_BASE_URL}/v1/audio/transcriptions` (model: `whisper-1`). |
| **Turn-Based Audio TTS** | Piper Speech Synthesis | OpenAI-compatible speech synthesis targeting `${LITELLM_BASE_URL}/v1/audio/speech` (model: `tts-1`, voice: `alloy` / installed Piper voices). |
| **Custom Tools Management** | Deterministic Registration | `tools/register_tool.py` providing idempotent, container-native registration for custom tools into Open WebUI's SQLite database without duplicate entries. |

---

## 3. Package File Tree

```
open-webui-portable/
├── README.md                      # Architecture overview and capability inventory (this file)
├── INSTALL.md                     # Step-by-step installation instructions for a new system
├── CONFIGURATION.md               # Detailed configuration guide for all parameters
├── UPGRADE.md                     # Version upgrade runbook and regression checklist
├── TROUBLESHOOTING.md             # Common deployment and connectivity issues with resolutions
├── env.example                    # Template environment file with variable definitions
├── docker-compose.yml.template    # Docker Compose template for Open WebUI v0.13.4
├── install.sh                     # Automated, idempotent installer script
├── configure.py                   # CLI and interactive configuration manager
├── validate.py                    # 14-target automated integration validation suite
├── tools/
│   ├── speech_coach_tool.py       # Speech Coach v2.0.0 custom tool source with Valves
│   ├── register_tool.py           # Tool registration script (DB & API modes)
│   └── valves.example.json        # Reference Valves configuration JSON
└── optional-patches/
    ├── README.md                  # Evolution report: why v0.13.4 operates unpatched
    ├── legacy_v0.11.1/            # Archived v0.11.1 patches (for reference/audit)
    │   ├── 34.DRvNJD_W.js
    │   ├── fwivdHaq.js
    │   ├── D5GoHi-U.js
    │   ├── images.py
    │   └── audio.py
    └── realtime_voice/
        └── patch_openwebui_realtime.py  # Standalone legacy CallOverlay patcher
```

---

## 4. Quick Start

### 1. Configure Target LiteLLM Connection
```bash
python3 configure.py \
    --litellm-url "https://litellm.example.com" \
    --api-key "your-litellm-master-key" \
    --port 3000
```

### 2. Run the Portable Installer
```bash
./install.sh
```

### 3. Verify All Endpoints
```bash
python3 validate.py
```

For complete instructions, consult [INSTALL.md](file:///mnt/ai-docker/open-webui-portable/INSTALL.md).
