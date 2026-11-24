#!/usr/bin/env python3
"""
register_tool.py - Deterministic, Idempotent Tool & Valves Registration for Open WebUI v0.13.4

Supports:
1. Direct SQLite database registration (--db /path/to/webui.db)
2. Live REST API registration (--api-url http://host:port --token <jwt_token>)
3. Valve parameter configuration (--litellm-url, --api-key, --timeout)
4. Non-destructive, idempotent execution (safe to run repeatedly)
"""

import os
import sys
import json
import time
import argparse
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path

TOOL_ID = "speech_coach"
TOOL_NAME = "Speech Coach & Pronunciation Assessment"

CANONICAL_SPECS = [
    {
        "name": "analyze_speech_attempt",
        "description": "Submit a speech recording to the AI Gateway Speech Coach for comprehensive analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "audio_base64": {
                    "type": "string",
                    "description": "Base64-encoded audio bytes (WAV, MP3, WebM, OGG)."
                },
                "mode": {
                    "type": "string",
                    "default": "pronunciation",
                    "description": "'speaking_practice', 'pronunciation', 'accent_intelligibility', or 'general_conversation'."
                },
                "language": {
                    "type": "string",
                    "description": "Language code override, or None for automatic language detection."
                },
                "reference_text": {
                    "type": "string",
                    "description": "The target sentence if evaluating pronunciation mode."
                }
            },
            "required": ["audio_base64"]
        }
    },
    {
        "name": "get_supported_languages_and_voices",
        "description": "List all verified languages, locales, and local Piper voices available for Speech Coaching and TTS.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "start_pronunciation_practice",
        "description": "Generate a pronunciation practice task with reference sentence and articulatory guidance.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_sentence": {
                    "type": "string",
                    "description": "The sentence for the student to practice repeating."
                },
                "language": {
                    "type": "string",
                    "default": "en",
                    "description": "Language code ('en', 'hi', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'zh', 'ar')."
                }
            },
            "required": ["target_sentence"]
        }
    }
]

CANONICAL_META = {
    "i18n": None,
    "description": "Self-hosted multilingual voice coaching, pronunciation analysis, and speaking practice tool.",
    "manifest": {
        "title": "AI Gateway Speech Coach & Pronunciation Assessment",
        "author": "AI Gateway",
        "author_url": "https://gateway.local",
        "version": "2.0.0",
        "description": "Self-hosted multilingual voice coaching, pronunciation analysis, and speaking practice tool powered by Faster-Whisper and Piper TTS via LiteLLM."
    },
    "has_user_valves": False
}


def load_tool_source(source_path: Path) -> str:
    if not source_path.exists():
        raise FileNotFoundError(f"Speech Coach tool source not found: {source_path}")
    return source_path.read_text(encoding="utf-8")


def register_via_db(
    db_path: Path,
    source_path: Path,
    litellm_base_url: str,
    api_key: str = "",
    timeout: float = 60.0,
    speech_path: str = "/v1/audio/speech-analysis",
    voices_path: str = "/v1/audio/voices",
    check_only: bool = False,
) -> bool:
    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}", file=sys.stderr)
        return False

    content = load_tool_source(source_path)
    now = int(time.time())

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    try:
        # Check if table exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tool'")
        if not c.fetchone():
            print("[ERROR] Table 'tool' does not exist in target database.", file=sys.stderr)
            return False

        # Find existing admin user id for assignment if needed
        c.execute("SELECT id FROM user WHERE role='admin' ORDER BY created_at ASC LIMIT 1")
        row = c.fetchone()
        user_id = row[0] if row else "system"

        # Check existing tool
        c.execute("SELECT id, name, valves, updated_at FROM tool WHERE id = ?", (TOOL_ID,))
        existing = c.fetchone()

        target_valves = {
            "litellm_base_url": litellm_base_url.rstrip("/"),
            "speech_analysis_path": speech_path if speech_path.startswith("/") else f"/{speech_path}",
            "voices_path": voices_path if voices_path.startswith("/") else f"/{voices_path}",
            "api_key": api_key,
            "timeout": float(timeout),
        }

        if check_only:
            if not existing:
                print(f"[CHECK] Tool '{TOOL_ID}' is NOT installed.")
                return False
            print(f"[CHECK] Tool '{TOOL_ID}' is installed: {existing[1]}")
            print(f"        Valves: {existing[2]}")
            return True

        valves_json = json.dumps(target_valves)
        specs_json = json.dumps(CANONICAL_SPECS)
        meta_json = json.dumps(CANONICAL_META)

        if existing:
            print(f"[*] Updating existing tool '{TOOL_ID}' in database...")
            c.execute(
                """
                UPDATE tool
                SET name = ?,
                    content = ?,
                    specs = ?,
                    meta = ?,
                    valves = ?,
                    is_active = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (TOOL_NAME, content, specs_json, meta_json, valves_json, now, TOOL_ID),
            )
            print(f"[SUCCESS] Tool '{TOOL_ID}' successfully updated.")
        else:
            print(f"[*] Inserting new tool '{TOOL_ID}' into database...")
            c.execute(
                """
                INSERT INTO tool (id, version_id, user_id, name, content, specs, meta, valves, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (TOOL_ID, "2.0.0", user_id, TOOL_NAME, content, specs_json, meta_json, valves_json, now, now),
            )
            print(f"[SUCCESS] Tool '{TOOL_ID}' successfully registered.")

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Database registration failed: {e}", file=sys.stderr)
        return False
    finally:
        conn.close()


def register_via_api(
    api_url: str,
    token: str,
    source_path: Path,
    litellm_base_url: str,
    api_key: str = "",
    timeout: float = 60.0,
    speech_path: str = "/v1/audio/speech-analysis",
    voices_path: str = "/v1/audio/voices",
    check_only: bool = False,
) -> bool:
    api_url = api_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    content = load_tool_source(source_path)

    # 1. Check if tool exists
    req = urllib.request.Request(f"{api_url}/api/v1/tools/", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            tools = json.loads(resp.read().decode("utf-8"))
            existing = next((t for t in tools if t.get("id") == TOOL_ID), None)
    except Exception as e:
        print(f"[ERROR] Failed to query Open WebUI tools API: {e}", file=sys.stderr)
        return False

    if check_only:
        if existing:
            print(f"[CHECK] Tool '{TOOL_ID}' found via API.")
            return True
        print(f"[CHECK] Tool '{TOOL_ID}' not found via API.")
        return False

    target_valves = {
        "litellm_base_url": litellm_base_url.rstrip("/"),
        "speech_analysis_path": speech_path,
        "voices_path": voices_path,
        "api_key": api_key,
        "timeout": float(timeout),
    }

    if not existing:
        print(f"[*] Creating tool '{TOOL_ID}' via Open WebUI API...")
        payload = {
            "id": TOOL_ID,
            "name": TOOL_NAME,
            "content": content,
            "meta": CANONICAL_META,
        }
        create_req = urllib.request.Request(
            f"{api_url}/api/v1/tools/create",
            headers=headers,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        try:
            with urllib.request.urlopen(create_req, timeout=15) as resp:
                print(f"[SUCCESS] Tool created: HTTP {resp.status}")
        except Exception as e:
            print(f"[ERROR] Tool creation failed: {e}", file=sys.stderr)
            return False
    else:
        print(f"[*] Updating tool '{TOOL_ID}' via Open WebUI API...")
        payload = {
            "name": TOOL_NAME,
            "content": content,
            "meta": CANONICAL_META,
        }
        update_req = urllib.request.Request(
            f"{api_url}/api/v1/tools/id/{TOOL_ID}/update",
            headers=headers,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        try:
            with urllib.request.urlopen(update_req, timeout=15) as resp:
                print(f"[SUCCESS] Tool source updated: HTTP {resp.status}")
        except Exception as e:
            print(f"[ERROR] Tool update failed: {e}", file=sys.stderr)
            return False

    # 2. Update Valves
    print(f"[*] Configuring Valves for '{TOOL_ID}'...")
    valves_req = urllib.request.Request(
        f"{api_url}/api/v1/tools/id/{TOOL_ID}/valves/update",
        headers=headers,
        data=json.dumps(target_valves).encode("utf-8"),
        method="POST",
    )
    try:
        with urllib.request.urlopen(valves_req, timeout=10) as resp:
            print(f"[SUCCESS] Valves configured successfully: HTTP {resp.status}")
            return True
    except Exception as e:
        print(f"[ERROR] Valve update failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Register and configure Open WebUI Speech Coach custom tool.")
    parser.add_argument("--db", type=str, help="Path to Open WebUI SQLite webui.db file")
    parser.add_argument("--api-url", type=str, help="Open WebUI base URL (e.g. http://localhost:8080)")
    parser.add_argument("--token", type=str, help="Open WebUI JWT auth token for API calls")
    parser.add_argument("--source", type=str, default=str(Path(__file__).parent / "speech_coach_tool.py"), help="Path to speech_coach_tool.py")
    parser.add_argument("--litellm-url", type=str, default="http://litellm:4000", help="Base URL of LiteLLM proxy")
    parser.add_argument("--api-key", type=str, default="", help="LiteLLM API key for Valves (optional)")
    parser.add_argument("--timeout", type=float, default=60.0, help="Valves request timeout (seconds)")
    parser.add_argument("--speech-path", type=str, default="/v1/audio/speech-analysis", help="Speech analysis path")
    parser.add_argument("--voices-path", type=str, default="/v1/audio/voices", help="Voices catalog path")
    parser.add_argument("--check", action="store_true", help="Only check tool status without modifying")

    args = parser.parse_args()
    source_path = Path(args.source)

    if args.db:
        success = register_via_db(
            db_path=Path(args.db),
            source_path=source_path,
            litellm_base_url=args.litellm_url,
            api_key=args.api_key,
            timeout=args.timeout,
            speech_path=args.speech_path,
            voices_path=args.voices_path,
            check_only=args.check,
        )
    elif args.api_url and args.token:
        success = register_via_api(
            api_url=args.api_url,
            token=args.token,
            source_path=source_path,
            litellm_base_url=args.litellm_url,
            api_key=args.api_key,
            timeout=args.timeout,
            speech_path=args.speech_path,
            voices_path=args.voices_path,
            check_only=args.check,
        )
    else:
        print("[ERROR] Specify either --db /path/to/webui.db or --api-url and --token", file=sys.stderr)
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
