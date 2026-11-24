# Open WebUI Portable Installation Guide

This document describes the complete procedure for deploying our custom Open WebUI implementation onto a new physical or virtual Linux, macOS, or Windows (WSL2) system.

---

## 1. Prerequisites

Ensure the target system meets the following requirements:

1. **Operating System:** Linux (Ubuntu 22.04+, Debian 12+, RHEL 9+), macOS 13+, or Windows 11 with WSL2.
2. **Container Engine:**
   - Docker Engine `v24.0+` (or Docker Desktop)
   - Docker Compose `v2.20+` (`docker compose`)
3. **Runtime Utility:** Python `3.10+` with standard library (`sqlite3`, `urllib`, `json`).
4. **Network Connectivity:**
   - Outbound network reachability to the central LiteLLM proxy server (default port `4000` or HTTPS `443`).
   - Inbound access to the target host port (default port `3000`).
   - Outbound access to Hugging Face Hub (or cached volume) on initial container launch for Open WebUI's embedding model (`sentence-transformers/all-MiniLM-L6-v2`).

> [!NOTE]
> No local GPUs, AMD ROCm/Vulkan drivers, AI Gateway source code, or internal database credentials are required on this target machine.

---

## 2. Directory Preparation

Unpack or transfer the `open-webui-portable` package to your desired deployment location:

```bash
# Example deployment directory
mkdir -p /opt/open-webui-portable
cp -r /path/to/open-webui-portable/* /opt/open-webui-portable/
cd /opt/open-webui-portable

# Ensure helper scripts have execution permissions
chmod +x install.sh configure.py validate.py tools/register_tool.py
```

---

## 3. Configuration

You can configure the target deployment using either the automated CLI tool or by copying and editing `.env`.

### Method A: Automated CLI (Recommended)

Run `configure.py` to establish the connection to your existing LiteLLM proxy:

```bash
# Example 1: Connecting to a remote LiteLLM server over HTTPS
python3 configure.py \
    --litellm-url "https://litellm.example.com" \
    --api-key "sk-litellm-master-key-here" \
    --port 3000

# Example 2: Connecting to an internal network LiteLLM server
python3 configure.py \
    --litellm-url "http://192.168.1.50:4000" \
    --api-key "044cc23b73cc9e58e63e4aadf872d28ecf0d52b9182798a576c951ca8c95af40" \
    --port 3000
```

To run interactively with prompted values:
```bash
python3 configure.py --interactive
```

To display the current parsed configuration:
```bash
python3 configure.py --show
```

To run a pre-deployment network and authentication verification:
```bash
python3 configure.py --validate
```

### Method B: Manual File Configuration

Copy `env.example` to `.env`:

```bash
cp env.example .env
```

Edit `.env` using your preferred editor (`nano .env` or `vim .env`):

```bash
LITELLM_BASE_URL=https://litellm.example.com
LITELLM_API_KEY=your-litellm-key-here
PORT=3000
WEBUI_NAME="My Organization Open WebUI"
```

Then regenerate `docker-compose.yml`:
```bash
python3 configure.py
```

---

## 4. Execution

Execute the portable installer:

```bash
./install.sh
```

### What `install.sh` Does Automatically

1. **Preflight Checks:** Validates Docker, Docker Compose, and Python 3 availability.
2. **LiteLLM Connectivity Test:** Tests `/health/liveliness`, authenticated model discovery (`/v1/models`), image discovery (`/images/v1/models`), and speech voices catalog (`/v1/audio/voices`).
3. **Deployment Manifest Generation:** Synchronizes `docker-compose.yml` with `.env` settings.
4. **Container Boot:** Starts `open-webui` (`ghcr.io/open-webui/open-webui:v0.13.4`).
5. **Health Wait:** Waits for Open WebUI's HTTP health check to succeed (up to 120s for initial model pull).
6. **Stock Verification:** Confirms stock unpatched image execution.
7. **Speech Coach Registration:** Automatically injects `speech_coach_tool.py` (v2.0.0) into the SQLite database and configures Valves (`litellm_base_url`, paths, key, timeout).
8. **Image Connection Initialization:** Seeds `images.connections` in the database to link directly to LiteLLM's `/images/v1` routes.
9. **Idempotency Guarantee:** Can be run repeatedly without duplicating tools or corrupting configuration.

---

## 5. Post-Installation Verification

Run the automated validation suite to verify all 14 integration targets:

```bash
python3 validate.py
```

Expected output:
```
================================================================
  Open WebUI Portable Deployment — Integration Validation Suite 
================================================================
Target LiteLLM URL:  https://litellm.example.com
Target Open WebUI:   http://localhost:3000

 [PASS] LiteLLM Authentication & Key Isolation
 [PASS] Text Model Discovery & Model Separation (/v1/models)
 [PASS] Image Model Discovery & Separation (/images/v1/models)
 [PASS] Text Completion (/v1/chat/completions)
 [PASS] Audio TTS Speech Synthesis (/v1/audio/speech)
 [PASS] Audio STT Transcription (/v1/audio/transcriptions)
 [PASS] Speech Coach Voice Catalog (/v1/audio/voices)
 [PASS] Speech Coach Speaking Practice Analysis
 [PASS] Speech Coach Pronunciation Assessment
 [PASS] Realtime Voice WebSocket Handshake
 [PASS] Image Generation Reachability & Routing
 [PASS] Gateway Credential Isolation Check
 [PASS] End-to-End 3-Tier Routing Integrity
 [PASS] Open WebUI Container Healthcheck

----------------------------------------------------------------
ALL 14/14 VALIDATION TARGETS PASSED SUCCESSFULLY!
----------------------------------------------------------------
```

---

## 6. First-Time Administrator Setup (Manual Actions)

While the installer completely provisions the database, models, image connections, audio routes, and custom tools, Open WebUI's security model requires the following initial user actions in the browser:

### 1. Create First Administrator Account
1. Open your browser and navigate to `http://localhost:3000` (or `http://<your-ip>:3000`).
2. Click **Sign Up** to create your account.
3. The **first registered user** automatically becomes the instance **Administrator** (`role: admin`).

### 2. Verify Speech Coach Tool in Workspace
1. Navigate to **Workspace** (top-left menu) -> **Tools**.
2. Verify **Speech Coach & Pronunciation Assessment** is listed and active (`is_active: true`).
3. Click the gear icon to open **Valves**:
   - `litellm_base_url`: Reflects your configured LiteLLM URL.
   - `api_key`: Leave blank to inherit container environment variable, or enter a specific user key.
   - Click **Save**.

### 3. Use Speech Coach in Chat
1. Open a new chat.
2. In the chat input box, click the **+ (Tools)** button and select **Speech Coach & Pronunciation Assessment**.
3. You can now prompt the model:
   - *"List available languages and voices for speaking practice"*
   - *"Give me a pronunciation practice sentence in Spanish"*
   - Record an audio clip and ask: *"Please analyze my pronunciation against the reference sentence"*

### 4. Enable Realtime Voice Calls
1. Click your profile icon (bottom-left) -> **Settings** -> **Audio**.
2. Under **Call Settings**, ensure **Voice** is selected (e.g., `en_US-lessac-medium` or `alloy`).
3. In any chat, click the **Call (Headphones)** button next to the input field to start a low-latency, full-duplex realtime voice conversation.
