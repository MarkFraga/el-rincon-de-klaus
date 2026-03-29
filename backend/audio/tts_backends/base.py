"""Base interface for TTS backends."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class TTSBackend:
    """Abstract base class for TTS backends."""

    async def synthesize(
        self,
        text: str,
        voice: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> Path:
        """Generate speech audio from text.

        Args:
            text: Text to synthesize.
            voice: Voice identifier (backend-specific).
            output_path: Where to save the audio file.
            rate: Speech rate adjustment (e.g., "+10%", "-5%").
            pitch: Pitch adjustment (e.g., "-4Hz", "+2Hz").

        Returns:
            Path to the generated audio file.
        """
        raise NotImplementedError
