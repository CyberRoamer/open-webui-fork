"""
title: AI Gateway Speech Coach & Pronunciation Assessment
author: AI Gateway
author_url: https://gateway.local
version: 2.0.0
description: Self-hosted multilingual voice coaching, pronunciation analysis, and speaking practice tool powered by Faster-Whisper and Piper TTS via LiteLLM.
"""

import os
import json
import httpx
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class Tools:
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
            description="API key for LiteLLM proxy authentication. If left blank, falls back to server environment variables (LITELLM_MASTER_KEY or IMAGES_OPENAI_API_KEY).",
        )
        timeout: float = Field(
            default=60.0,
            description="Request timeout in seconds for speech analysis and catalog requests.",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _get_api_key(self) -> str:
        if self.valves.api_key and self.valves.api_key.strip():
            return self.valves.api_key.strip()
        # Fallback to server-side environment variables without leaking credentials to client
        return (
            os.environ.get("LITELLM_MASTER_KEY")
            or os.environ.get("IMAGES_OPENAI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )

    def _build_url(self, path: str) -> str:
        base = (self.valves.litellm_base_url or "").strip().rstrip("/")
        if not (base.startswith("http://") or base.startswith("https://")):
            raise ValueError(f"Invalid LiteLLM base URL scheme. Must start with http:// or https://: {base}")
        path = path if path.startswith("/") else f"/{path}"
        return f"{base}{path}"

    def _get_headers(self, content_type: Optional[str] = None) -> Dict[str, str]:
        headers = {}
        api_key = self._get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    async def get_supported_languages_and_voices(self) -> str:
        """
        List all verified languages, locales, and local Piper voices available for Speech Coaching and TTS.
        :return: JSON formatted catalog of verified languages, voices, and STT capabilities.
        """
        headers = self._get_headers()
        url = self._build_url(self.valves.voices_path)
        timeout = float(self.valves.timeout or 60.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    voices = data.get("voices", [])
                    return json.dumps({
                        "stt_languages": [
                            "English (en)", "Hindi (hi)", "Spanish (es)", "French (fr)",
                            "German (de)", "Italian (it)", "Portuguese (pt)", "Russian (ru)",
                            "Chinese (zh)", "Arabic (ar)", "Japanese (ja)", "Korean (ko)"
                        ],
                        "installed_tts_voices": voices,
                        "coaching_modes": [
                            {"mode": "general_conversation", "description": "Normal conversation voice mode, no scoring."},
                            {"mode": "speaking_practice", "description": "Free speaking practice evaluating fluency, pace (WPM), pauses, and fillers."},
                            {"mode": "pronunciation", "description": "Target sentence repetition with phonetic word alignment, error detection, and articulatory tips."},
                            {"mode": "accent_intelligibility", "description": "Focus on communicative intelligibility, vowel distinctions, and consonant clarity without penalizing non-native accents."}
                        ]
                    }, indent=2)
                return json.dumps({"error": f"Failed to fetch voices ({resp.status_code}): {resp.text}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def start_pronunciation_practice(
        self,
        target_sentence: str,
        language: str = "en",
    ) -> str:
        """
        Generate a pronunciation practice task with reference sentence and articulatory guidance.
        :param target_sentence: The sentence for the student to practice repeating.
        :param language: Language code ('en', 'hi', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'zh', 'ar').
        :return: Practice instructions and prompt for student to record their speech.
        """
        return json.dumps({
            "mode": "pronunciation",
            "language": language,
            "target_sentence": target_sentence,
            "instructions": [
                f"1. Read the target sentence carefully: '{target_sentence}'",
                "2. Click the voice recorder button in Open WebUI to record your attempt.",
                "3. Your recording will be evaluated against the target text on phonetics, pacing, and clarity.",
                "4. You will receive word-by-word accuracy and actionable pronunciation tips."
            ],
            "tips": "Speak at a steady, natural pace. Pay special attention to distinct consonant endings and vowel lengths."
        }, indent=2)

    async def analyze_speech_attempt(
        self,
        audio_base64: str,
        mode: str = "pronunciation",
        language: Optional[str] = None,
        reference_text: Optional[str] = None,
    ) -> str:
        """
        Submit a speech recording to the AI Gateway Speech Coach for comprehensive analysis.
        :param audio_base64: Base64-encoded audio bytes (WAV, MP3, WebM, OGG).
        :param mode: 'speaking_practice', 'pronunciation', 'accent_intelligibility', or 'general_conversation'.
        :param language: Language code override, or None for automatic language detection.
        :param reference_text: The target sentence if evaluating pronunciation mode.
        :return: Structured coaching feedback including speech rate (WPM), pause analysis, fluency, and pronunciation suggestions.
        """
        headers = self._get_headers(content_type="application/json")
        url = self._build_url(self.valves.speech_analysis_path)
        payload = {
            "audio": audio_base64,
            "mode": mode,
            "language": language,
            "reference_text": reference_text,
        }
        timeout = float(self.valves.timeout or 60.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                return resp.text
        except Exception as e:
            return json.dumps({"error": f"Failed to call speech analysis API: {e}"})
