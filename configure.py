#!/usr/bin/env python3
"""
configure.py - Open WebUI Portable Configuration Manager

Generates and updates .env, docker-compose.yml, and tool valves without editing Python source code.
Validates parameters and tests remote LiteLLM connectivity.
"""

import os
import sys
import argparse
import urllib.request
import urllib.error
import json
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent.resolve()
ENV_FILE = PACKAGE_DIR / ".env"
ENV_TEMPLATE = PACKAGE_DIR / "env.example"
COMPOSE_TEMPLATE = PACKAGE_DIR / "docker-compose.yml.template"
COMPOSE_FILE = PACKAGE_DIR / "docker-compose.yml"


def parse_env_file(path: Path) -> dict:
    if not path.exists():
        return {}
    config = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            val = val.strip()
            while len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1].strip()
            config[key.strip()] = val
    return config


def write_env_file(path: Path, config: dict):
    lines = [
        "# ==============================================================================",
        "# Open WebUI Portable Deployment — Generated Environment File",
        "# ==============================================================================",
        "",
        "# LiteLLM Proxy Configuration",
        f"LITELLM_BASE_URL={config.get('LITELLM_BASE_URL', 'http://<YOUR_LITELLM_HOST>:4000')}",
        f"LITELLM_API_KEY={config.get('LITELLM_API_KEY', '<YOUR_LITELLM_API_KEY>')}",
        "",
        "# Text & Chat Model Endpoint",
        f"OPENAI_API_BASE_URL={config.get('OPENAI_API_BASE_URL', '${LITELLM_BASE_URL}/v1')}",
        f"OPENAI_API_KEY={config.get('OPENAI_API_KEY', '${LITELLM_API_KEY}')}",
        "",
        "# Image Generation & Model Discovery Endpoint",
        f"ENABLE_IMAGE_GENERATION={config.get('ENABLE_IMAGE_GENERATION', 'true')}",
        f"IMAGE_GENERATION_ENGINE={config.get('IMAGE_GENERATION_ENGINE', 'openai')}",
        f"IMAGES_OPENAI_API_BASE_URL={config.get('IMAGES_OPENAI_API_BASE_URL', '${LITELLM_BASE_URL}/images/v1')}",
        f"IMAGES_OPENAI_API_KEY={config.get('IMAGES_OPENAI_API_KEY', '${LITELLM_API_KEY}')}",
        f"IMAGE_URL_RESPONSE_MODELS_REGEX_PATTERN={config.get('IMAGE_URL_RESPONSE_MODELS_REGEX_PATTERN', '.*')}",
        f"IMAGE_GENERATION_MODEL={config.get('IMAGE_GENERATION_MODEL', 'flux1-schnell')}",
        f"ENABLE_IMAGE_EDIT={config.get('ENABLE_IMAGE_EDIT', 'true')}",
        f"IMAGE_EDIT_ENGINE={config.get('IMAGE_EDIT_ENGINE', 'openai')}",
        f"IMAGES_EDIT_OPENAI_API_BASE_URL={config.get('IMAGES_EDIT_OPENAI_API_BASE_URL', '${LITELLM_BASE_URL}/images/v1')}",
        f"IMAGES_EDIT_OPENAI_API_KEY={config.get('IMAGES_EDIT_OPENAI_API_KEY', '${LITELLM_API_KEY}')}",
        f"IMAGE_EDIT_MODEL={config.get('IMAGE_EDIT_MODEL', 'flux1-schnell')}",
        "",
        "# Turn-Based Audio STT & TTS Endpoints",
        f"AUDIO_STT_ENGINE={config.get('AUDIO_STT_ENGINE', 'openai')}",
        f"AUDIO_STT_OPENAI_API_BASE_URL={config.get('AUDIO_STT_OPENAI_API_BASE_URL', '${LITELLM_BASE_URL}/v1')}",
        f"AUDIO_STT_OPENAI_API_KEY={config.get('AUDIO_STT_OPENAI_API_KEY', '${LITELLM_API_KEY}')}",
        f"AUDIO_STT_MODEL={config.get('AUDIO_STT_MODEL', 'whisper-1')}",
        f"AUDIO_TTS_ENGINE={config.get('AUDIO_TTS_ENGINE', 'openai')}",
        f"AUDIO_TTS_OPENAI_API_BASE_URL={config.get('AUDIO_TTS_OPENAI_API_BASE_URL', '${LITELLM_BASE_URL}/v1')}",
        f"AUDIO_TTS_OPENAI_API_KEY={config.get('AUDIO_TTS_OPENAI_API_KEY', '${LITELLM_API_KEY}')}",
        f"AUDIO_TTS_MODEL={config.get('AUDIO_TTS_MODEL', 'tts-1')}",
        f"AUDIO_TTS_VOICE={config.get('AUDIO_TTS_VOICE', 'alloy')}",
        "",
        "# Realtime Voice Calls Subsystem",
        f"AUDIO_REALTIME_ENABLED={config.get('AUDIO_REALTIME_ENABLED', 'true')}",
        f"AUDIO_REALTIME_PROVIDER={config.get('AUDIO_REALTIME_PROVIDER', 'openai')}",
        f"AUDIO_REALTIME_AUTH_TYPE={config.get('AUDIO_REALTIME_AUTH_TYPE', 'api_key')}",
        f"AUDIO_REALTIME_OPENAI_API_BASE_URL={config.get('AUDIO_REALTIME_OPENAI_API_BASE_URL', '${LITELLM_BASE_URL}/v1')}",
        f"AUDIO_REALTIME_OPENAI_API_KEY={config.get('AUDIO_REALTIME_OPENAI_API_KEY', '${LITELLM_API_KEY}')}",
        f"AUDIO_REALTIME_MODEL={config.get('AUDIO_REALTIME_MODEL', 'realtime-voice')}",
        f"AUDIO_REALTIME_VOICE={config.get('AUDIO_REALTIME_VOICE', 'en_US-lessac-medium')}",
        f"AUDIO_REALTIME_TRANSCRIPTION_MODEL={config.get('AUDIO_REALTIME_TRANSCRIPTION_MODEL', 'whisper-1')}",
        "",
        "# Speech Coach Tool Valves",
        f"SPEECH_COACH_ANALYSIS_PATH={config.get('SPEECH_COACH_ANALYSIS_PATH', '/v1/audio/speech-analysis')}",
        f"SPEECH_COACH_VOICES_PATH={config.get('SPEECH_COACH_VOICES_PATH', '/v1/audio/voices')}",
        f"SPEECH_COACH_TIMEOUT={config.get('SPEECH_COACH_TIMEOUT', '60.0')}",
        "",
        "# WebUI Instance Settings",
        f"PORT={config.get('PORT', '3000')}",
        f"WEBUI_NAME=\"{config.get('WEBUI_NAME', 'Open WebUI')}\"",
        f"OPEN_WEBUI_DATA_DIR={config.get('OPEN_WEBUI_DATA_DIR', './data')}",
        f"CONTAINER_NAME={config.get('CONTAINER_NAME', 'open-webui')}",
        f"DO_NOT_TRACK={config.get('DO_NOT_TRACK', 'true')}",
        f"ANONYMIZED_TELEMETRY={config.get('ANONYMIZED_TELEMETRY', 'false')}",
        f"SCARF_NO_ANALYTICS={config.get('SCARF_NO_ANALYTICS', 'true')}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_compose_file():
    if COMPOSE_TEMPLATE.exists():
        content = COMPOSE_TEMPLATE.read_text(encoding="utf-8")
        COMPOSE_FILE.write_text(content, encoding="utf-8")
        print(f"[SUCCESS] Generated {COMPOSE_FILE.name}")


def validate_litellm_connectivity(litellm_url: str, api_key: str) -> bool:
    litellm_url = litellm_url.rstrip("/")
    probe_url = litellm_url
    if "host.docker.internal" in litellm_url:
        import socket
        try:
            socket.gethostbyname("host.docker.internal")
        except socket.gaierror:
            probe_url = litellm_url.replace("host.docker.internal", "172.17.0.1")
            print(f"[*] Note: Testing host probe via {probe_url} (container will use host.docker.internal)")
    print(f"[*] Validating LiteLLM connectivity to: {litellm_url}")

    # 1. Health Liveliness
    health_url = f"{probe_url}/health/liveliness"
    try:
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                print("    [PASS] Liveliness endpoint reachable")
            else:
                print(f"    [WARN] Liveliness endpoint returned HTTP {resp.status}")
    except Exception as e:
        print(f"    [FAIL] Liveliness check failed: {e}")
        return False

    # 2. Authenticated Model Discovery
    models_url = f"{probe_url}/v1/models"
    try:
        req = urllib.request.Request(models_url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            count = len(data.get("data", []))
            print(f"    [PASS] Authentication successful ({count} text/chat models available)")
    except urllib.error.HTTPError as e:
        if e.code == 401 or e.code == 403:
            print(f"    [FAIL] Authentication failed (HTTP {e.code}). Please verify LITELLM_API_KEY.")
        else:
            print(f"    [FAIL] Model check failed with HTTP {e.code}: {e.reason}")
        return False
    except Exception as e:
        print(f"    [FAIL] Failed to reach /v1/models: {e}")
        return False

    # 3. Image Discovery Endpoint
    img_models_url = f"{probe_url}/images/v1/models"
    try:
        req = urllib.request.Request(img_models_url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            count = len(data.get("data", []))
            print(f"    [PASS] Image discovery endpoint verified ({count} image models available)")
    except Exception as e:
        print(f"    [WARN] Image discovery endpoint check: {e}")

    # 4. Speech Voices Catalog Endpoint
    voices_url = f"{probe_url}/v1/audio/voices"
    try:
        req = urllib.request.Request(voices_url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            print("    [PASS] Speech coach voices catalog endpoint verified")
    except Exception as e:
        print(f"    [WARN] Voices catalog check: {e}")

    return True


def show_config(config: dict):
    print("\n=== Current Open WebUI Configuration ===")
    for k in sorted(config.keys()):
        val = config[k]
        if "KEY" in k and val and val != "<YOUR_LITELLM_API_KEY>":
            masked = val[:6] + "..." + val[-4:] if len(val) > 12 else "********"
            print(f"  {k:35} = {masked}")
        else:
            print(f"  {k:35} = {val}")
    print("========================================\n")


def main():
    parser = argparse.ArgumentParser(description="Configure Open WebUI Portable Deployment.")
    parser.add_argument("--litellm-url", type=str, help="Base URL of LiteLLM proxy (e.g. http://192.168.1.50:4000 or https://ai.example.com)")
    parser.add_argument("--api-key", type=str, help="LiteLLM API key")
    parser.add_argument("--port", type=str, help="Open WebUI HTTP listening port (default: 3000)")
    parser.add_argument("--data-dir", type=str, help="Open WebUI persistent data directory")
    parser.add_argument("--container-name", type=str, help="Docker container name")
    parser.add_argument("--webui-name", type=str, help="Open WebUI header title")
    parser.add_argument("--text-endpoint", type=str, help="Custom text model API endpoint")
    parser.add_argument("--image-endpoint", type=str, help="Custom image generation API endpoint")
    parser.add_argument("--speech-analysis-path", type=str, help="Custom speech analysis path")
    parser.add_argument("--voices-path", type=str, help="Custom speech voices catalog path")
    parser.add_argument("--timeout", type=str, help="Speech Coach timeout in seconds")
    parser.add_argument("--validate", action="store_true", help="Validate LiteLLM connectivity")
    parser.add_argument("--show", action="store_true", help="Display current configuration")
    parser.add_argument("--interactive", action="store_true", help="Interactively prompt for configuration values")

    args = parser.parse_args()

    config = parse_env_file(ENV_FILE)
    if not config and ENV_TEMPLATE.exists():
        config = parse_env_file(ENV_TEMPLATE)

    if args.interactive:
        print("\n--- Open WebUI Portable Setup Wizard ---")
        curr_url = config.get("LITELLM_BASE_URL", "http://localhost:4000")
        new_url = input(f"LiteLLM Base URL [{curr_url}]: ").strip()
        if new_url:
            args.litellm_url = new_url

        curr_key = config.get("LITELLM_API_KEY", "")
        new_key = input(f"LiteLLM API Key [{curr_key[:6]}...]: ").strip()
        if new_key:
            args.api_key = new_key

        curr_port = config.get("PORT", "3000")
        new_port = input(f"Open WebUI Port [{curr_port}]: ").strip()
        if new_port:
            args.port = new_port

    modified = False

    if args.litellm_url:
        url = args.litellm_url.rstrip("/")
        config["LITELLM_BASE_URL"] = url
        # Derive defaults if not explicitly overridden
        if not args.text_endpoint:
            config["OPENAI_API_BASE_URL"] = f"{url}/v1"
        if not args.image_endpoint:
            config["IMAGES_OPENAI_API_BASE_URL"] = f"{url}/images/v1"
        config["IMAGES_EDIT_OPENAI_API_BASE_URL"] = config.get("IMAGES_OPENAI_API_BASE_URL", f"{url}/images/v1")
        if args.image_endpoint or not config.get("IMAGES_EDIT_OPENAI_API_BASE_URL"):
            config["IMAGES_EDIT_OPENAI_API_BASE_URL"] = f"{url}/images/v1"
        config["AUDIO_STT_OPENAI_API_BASE_URL"] = f"{url}/v1"
        config["AUDIO_TTS_OPENAI_API_BASE_URL"] = f"{url}/v1"
        config["AUDIO_REALTIME_OPENAI_API_BASE_URL"] = f"{url}/v1"
        modified = True

    if args.api_key:
        key = args.api_key.strip()
        config["LITELLM_API_KEY"] = key
        config["OPENAI_API_KEY"] = key
        config["IMAGES_OPENAI_API_KEY"] = key
        config["IMAGES_EDIT_OPENAI_API_KEY"] = key
        config["AUDIO_STT_OPENAI_API_KEY"] = key
        config["AUDIO_TTS_OPENAI_API_KEY"] = key
        config["AUDIO_REALTIME_OPENAI_API_KEY"] = key
        modified = True

    if args.port:
        config["PORT"] = args.port.strip()
        modified = True

    if args.data_dir:
        config["OPEN_WEBUI_DATA_DIR"] = args.data_dir.strip()
        modified = True

    if args.container_name:
        config["CONTAINER_NAME"] = args.container_name.strip()
        modified = True

    if args.webui_name:
        config["WEBUI_NAME"] = args.webui_name.strip()
        modified = True

    if args.text_endpoint:
        config["OPENAI_API_BASE_URL"] = args.text_endpoint.strip()
        modified = True

    if args.image_endpoint:
        config["IMAGES_OPENAI_API_BASE_URL"] = args.image_endpoint.strip()
        modified = True

    if args.speech_analysis_path:
        config["SPEECH_COACH_ANALYSIS_PATH"] = args.speech_analysis_path.strip()
        modified = True

    if args.voices_path:
        config["SPEECH_COACH_VOICES_PATH"] = args.voices_path.strip()
        modified = True

    if args.timeout:
        config["SPEECH_COACH_TIMEOUT"] = args.timeout.strip()
        modified = True

    if modified or not ENV_FILE.exists():
        write_env_file(ENV_FILE, config)
        generate_compose_file()
        print(f"[SUCCESS] Updated {ENV_FILE.name} and {COMPOSE_FILE.name}")

    if args.show:
        show_config(config)

    if args.validate:
        litellm_url = config.get("LITELLM_BASE_URL", "").replace("${LITELLM_BASE_URL}", "")
        api_key = config.get("LITELLM_API_KEY", "").replace("${LITELLM_API_KEY}", "")
        if not litellm_url or "<" in litellm_url:
            print("[ERROR] Please configure a valid LITELLM_BASE_URL first.", file=sys.stderr)
            sys.exit(1)
        valid = validate_litellm_connectivity(litellm_url, api_key)
        sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
