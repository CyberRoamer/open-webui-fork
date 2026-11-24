# Open WebUI Portable Deployment Package & Setup Guide

This repository contains the complete, reusable, production-tested deployment package for our enhanced **Open WebUI v0.13.4** implementation. It enables deploying Open WebUI onto any physical or virtual system—on-premise, cloud VM, or developer workstation—connecting back to the **existing LiteLLM Proxy** on our central AI Gateway server.

---

## 1. Architectural Topology

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

### Core Architecture Principles

1. **Zero Local Inference Infrastructure:** The target machine requires only Docker, Docker Compose, and Python 3. No local GPUs, Vulkan/ROCm drivers, or inference engines (`llama.cpp`, `sd.cpp`, Faster-Whisper, Piper) are needed.
2. **Complete Credential & Network Isolation:** Open WebUI possesses **zero knowledge of Gateway credentials** (`GATEWAY_API_KEY`) and no direct network route to internal Gateway services (`gateway-api:8000`). All interactions are mediated through LiteLLM using a standard API key (`LITELLM_API_KEY`).
3. **Stock Container Images (Zero Source Patching):** Open WebUI runs strictly from the unpatched upstream image `ghcr.io/open-webui/open-webui:v0.13.4`. All legacy monkey-patches from v0.11.1 have been retired.
4. **Strict Model Segregation:** LiteLLM isolates image models under `/images/v1/models`. The text chat model selector is never polluted with diffusion checkpoints.
5. **Configurable Endpoint Mobility:** Every endpoint, key, path, port, and timeout is configurable via `.env` or `configure.py` without modifying Python source code.

---

## 2. Quick Setup (3 Steps)

### Step 1: Configure Your Target LiteLLM Connection
```bash
python3 configure.py \
    --litellm-url "https://litellm.example.com" \
    --api-key "sk-your-litellm-master-key" \
    --port 3000
```

### Step 2: Run the Automated Installer
```bash
./install.sh
```

### Step 3: Verify All 14 Integration Targets
```bash
python3 validate.py
```

---

## 3. Package File Structure

```
open-webui-portable/
├── README.md                      # Package overview and setup guide (this file)
├── INSTALL.md                     # Step-by-step deployment guide
├── CONFIGURATION.md               # Detailed configuration guide for all parameters
├── UPGRADE.md                     # Version upgrade runbook and rollback procedure
├── TROUBLESHOOTING.md             # Common deployment, connectivity, and auth resolutions
├── .gitignore                     # Git ignore rules (prevents committing secrets or databases)
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

## 4. First-Time Administrator Setup

After running `./install.sh`, perform the following one-time setup steps in your browser:

1. **Bootstrap Admin Account:**
   - Open `http://<your-host-ip>:3000` in your web browser.
   - Click **Sign Up**. The first registered user automatically becomes the system **Administrator** (`role: admin`).
2. **Verify Speech Coach Tool:**
   - In Open WebUI, navigate to **Workspace** -> **Tools**.
   - Verify **Speech Coach & Pronunciation Assessment** is listed and active (`is_active: true`).
   - Click the gear icon to inspect or adjust Valves (`litellm_base_url`, `timeout`).
3. **Use Speech Coach in Chat:**
   - In any chat window, click the **+ (Tools)** button and select **Speech Coach & Pronunciation Assessment**.
   - Ask: *"List available languages and voices for speaking practice"* or *"Give me a pronunciation practice sentence in Spanish"*.
4. **Use Realtime Voice Calls:**
   - Click your profile avatar (bottom-left) -> **Settings** -> **Audio**.
   - Under **Call Settings**, ensure a voice is selected (e.g. `en_US-lessac-medium` or `alloy`).
   - In any chat, click the **Call (Headphones)** button to initiate a full-duplex realtime voice conversation.

---

## 5. Pushing to GitHub

The repository is fully initialized locally on branch `main` with remote origin set to `git@github.com:CyberRoamer/open-webui-portable.git`.

### SSH Key Setup

The SSH key is stored at:
```bash
/home/abc/Documents/ssh/id_ed25519
```

This key is confirmed and authenticated with GitHub:
```
Hi CyberRoamer! You've successfully authenticated, but GitHub does not provide shell access.
```

### Initial Push Instructions

Because GitHub does not allow creating new repositories via a raw `git push` over SSH, follow these steps:

1. **Create the empty repository on GitHub:**
   - Open your browser and go to: [https://github.com/new](https://github.com/new)
   - Set **Repository name** to: `open-webui-portable`
   - Set visibility to **Public** or **Private** (as desired).
   - **Do NOT** initialize with a README, .gitignore, or license (the repository is already initialized and committed locally).
   - Click **Create repository**.

2. **Push the committed code from the terminal:**
   ```bash
   cd /mnt/ai-docker/open-webui-portable
   GIT_SSH_COMMAND="ssh -i /home/abc/Documents/ssh/id_ed25519" git push -u origin main
   ```

3. **Subsequent pushes:**
   Since `core.sshCommand` is configured in `.git/config`, standard Git commands will automatically use the key:
   ```bash
   cd /mnt/ai-docker/open-webui-portable
   git push
   ```

---

## 6. Documentation Map

* [INSTALL.md](file:///mnt/ai-docker/open-webui-portable/INSTALL.md) — Complete installation guide for fresh deployments.
* [CONFIGURATION.md](file:///mnt/ai-docker/open-webui-portable/CONFIGURATION.md) — Comprehensive guide to all configurable variables and remote HTTPS setups.
* [UPGRADE.md](file:///mnt/ai-docker/open-webui-portable/UPGRADE.md) — Runbook for upgrading Open WebUI container versions while preserving user data and custom tools.
* [TROUBLESHOOTING.md](file:///mnt/ai-docker/open-webui-portable/TROUBLESHOOTING.md) — Diagnostic checklists and solutions for network, authentication, and database issues.
* [optional-patches/README.md](file:///mnt/ai-docker/open-webui-portable/optional-patches/README.md) — Evolution analysis and archive of retired v0.11.1 patches.
