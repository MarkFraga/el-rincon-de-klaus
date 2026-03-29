"""Kokoro TTS backend with voice mixing for unique voices.

Uses Kokoro's voice embedding system to blend 2 base voices into
unique combinations. Each character gets a distinct voice that
doesn't repeat across guests.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import torch
from huggingface_hub import hf_hub_download

from backend.audio.tts_backends.base import TTSBackend

logger = logging.getLogger(__name__)

_REPO_ID = "hexgrad/Kokoro-82M"

# Lazy-loaded pipeline and voice cache
_pipeline = None
_load_lock = asyncio.Lock()
_voice_cache: dict[str, torch.Tensor] = {}


async def _get_pipeline():
    """Lazy-load the Kokoro pipeline."""
    global _pipeline
    async with _load_lock:
        if _pipeline is not None:
            return _pipeline
        try:
            from kokoro import KPipeline
            logger.info("Loading Kokoro TTS model...")
            _pipeline = KPipeline(lang_code="es", repo_id=_REPO_ID)
            logger.info("Kokoro TTS model loaded.")
            return _pipeline
        except ImportError:
            raise ImportError("kokoro not installed. pip install kokoro>=0.9 soundfile")


def _load_voice(voice_name: str) -> torch.Tensor:
    """Load a voice embedding tensor, with caching."""
    if voice_name in _voice_cache:
        return _voice_cache[voice_name]

    path = hf_hub_download(_REPO_ID, f"voices/{voice_name}.pt")
    tensor = torch.load(path, weights_only=True)
    _voice_cache[voice_name] = tensor
    logger.debug("Loaded voice: %s (%s)", voice_name, tensor.shape)
    return tensor


def create_mixed_voice(voice_a: str, voice_b: str, blend_ratio: float = 0.5) -> torch.Tensor:
    """Create a new voice by blending two base voice embeddings.

    Args:
        voice_a: First voice name (e.g., "am_onyx")
        voice_b: Second voice name (e.g., "em_alex")
        blend_ratio: 0.0 = all voice_a, 1.0 = all voice_b

    Returns:
        Blended voice tensor ready for Kokoro pipeline.
    """
    t_a = _load_voice(voice_a)
    t_b = _load_voice(voice_b)
    return t_a * (1 - blend_ratio) + t_b * blend_ratio


def _parse_rate(rate_str: str) -> float:
    """Convert rate string like '+10%' to speed float like 1.10."""
    rate_str = rate_str.strip().replace("%", "")
    try:
        return 1.0 + float(rate_str) / 100.0
    except ValueError:
        return 1.0


class KokoroTTSBackend(TTSBackend):
    """Kokoro TTS with voice mixing. 82M params, CPU-friendly."""

    async def synthesize(
        self,
        text: str,
        voice: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> Path:
        """Synthesize speech. `voice` can be:

        - A single voice name: "am_onyx"
        - A mix spec: "am_onyx:0.65+em_alex:0.35"
        - A pre-built torch.Tensor (via synthesize_with_recipe)
        """
        pipeline = await _get_pipeline()
        speed = _parse_rate(rate)

        # Parse voice specification
        if isinstance(voice, torch.Tensor):
            voice_tensor = voice
        elif "+" in voice and ":" in voice:
            # Mix spec: "am_onyx:0.65+em_alex:0.35"
            voice_tensor = self._parse_mix_spec(voice)
        else:
            # Single voice name -- try loading it
            try:
                voice_tensor = _load_voice(voice)
            except Exception:
                # If voice name is an edge-tts ID, use default Spanish male
                voice_tensor = _load_voice("em_alex")

        def _generate():
            import soundfile as sf
            import numpy as np

            audio_chunks = []
            for _, _, chunk in pipeline(text, voice=voice_tensor, speed=speed):
                if chunk is not None:
                    audio_chunks.append(chunk)

            if not audio_chunks:
                raise ValueError(f"Kokoro produced no audio for: {text[:50]}...")

            full_audio = np.concatenate(audio_chunks)
            sf.write(str(output_path), full_audio, 24000)

        await asyncio.to_thread(_generate)
        return output_path

    async def synthesize_with_recipe(
        self,
        text: str,
        voice_a: str,
        voice_b: str,
        blend_ratio: float,
        output_path: Path,
        speed: float = 1.0,
    ) -> Path:
        """Synthesize with a voice recipe (mixed voice)."""
        pipeline = await _get_pipeline()
        voice_tensor = create_mixed_voice(voice_a, voice_b, blend_ratio)

        def _generate():
            import soundfile as sf
            import numpy as np

            audio_chunks = []
            for _, _, chunk in pipeline(text, voice=voice_tensor, speed=speed):
                if chunk is not None:
                    audio_chunks.append(chunk)

            if not audio_chunks:
                raise ValueError(f"Kokoro produced no audio for: {text[:50]}...")

            full_audio = np.concatenate(audio_chunks)
            sf.write(str(output_path), full_audio, 24000)

        await asyncio.to_thread(_generate)
        return output_path

    @staticmethod
    def _parse_mix_spec(spec: str) -> torch.Tensor:
        """Parse 'am_onyx:0.65+em_alex:0.35' into a mixed tensor."""
        parts = spec.split("+")
        if len(parts) != 2:
            return _load_voice("em_alex")  # fallback

        name_a, ratio_a = parts[0].rsplit(":", 1)
        name_b, ratio_b = parts[1].rsplit(":", 1)

        try:
            r_a = float(ratio_a)
            r_b = float(ratio_b)
        except ValueError:
            r_a, r_b = 0.5, 0.5

        total = r_a + r_b
        return create_mixed_voice(name_a.strip(), name_b.strip(), r_b / total)
