"""ElevenLabs TTS backend -- premium cloud API, human-like quality.

Requires ELEVENLABS_API_KEY env var. Free tier: 10k chars/month.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.audio.tts_backends.base import TTSBackend
from backend.config import ELEVENLABS_API_KEY

logger = logging.getLogger(__name__)

# Map edge-tts voice IDs to ElevenLabs voice IDs
# Users should set their own voice IDs via env vars or config
_VOICE_MAP = {
    "es-ES-AlvaroNeural": "pNInz6obpgDQGcFmaJgB",  # Default: "Adam"
    "es-MX-JorgeNeural": "ErXwobaYiN019PkySvjV",     # Default: "Antoni"
}

_DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"


class ElevenLabsTTSBackend(TTSBackend):
    """Uses ElevenLabs API (premium quality, cloud-based)."""

    def __init__(self):
        if not ELEVENLABS_API_KEY:
            raise ValueError(
                "ELEVENLABS_API_KEY not set. Set it in .env to use ElevenLabs TTS."
            )

    async def synthesize(
        self,
        text: str,
        voice: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> Path:
        voice_id = _VOICE_MAP.get(voice, _DEFAULT_VOICE_ID)

        def _generate():
            import httpx

            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": ELEVENLABS_API_KEY,
            }
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.5,
                    "use_speaker_boost": True,
                },
            }

            with httpx.Client(timeout=60) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                output_path.write_bytes(resp.content)

        await asyncio.to_thread(_generate)
        return output_path
