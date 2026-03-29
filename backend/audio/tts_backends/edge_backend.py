"""Edge-TTS backend -- Microsoft's free neural TTS."""

from __future__ import annotations

from pathlib import Path

import edge_tts

from backend.audio.tts_backends.base import TTSBackend


class EdgeTTSBackend(TTSBackend):
    """Uses Microsoft Edge TTS (free, cloud-based, decent quality)."""

    async def synthesize(
        self,
        text: str,
        voice: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> Path:
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(str(output_path))
        return output_path
