"""Kokoro TTS backend using ONNX runtime (no PyTorch required).

Uses kokoro-onnx for lightweight TTS with voice blending.
Memory footprint ~200MB vs ~1GB+ with PyTorch.
Model files are pre-downloaded in the Docker image.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import numpy as np

from backend.audio.tts_backends.base import TTSBackend

logger = logging.getLogger(__name__)

# Model files location (downloaded during Docker build)
_MODEL_DIR = Path(__file__).parent.parent.parent.parent / "models"
_MODEL_PATH = _MODEL_DIR / "kokoro-v1.0.int8.onnx"
_VOICES_PATH = _MODEL_DIR / "voices-v1.0.bin"

# Lazy-loaded instances
_kokoro = None
_g2p = None
_load_lock = asyncio.Lock()
_voice_cache: dict[str, np.ndarray] = {}


async def _get_kokoro():
    """Lazy-load the Kokoro ONNX model and Spanish G2P."""
    global _kokoro, _g2p
    async with _load_lock:
        if _kokoro is not None:
            return _kokoro, _g2p

        from kokoro_onnx import Kokoro

        logger.info("Loading Kokoro ONNX model from %s ...", _MODEL_PATH)
        _kokoro = Kokoro(str(_MODEL_PATH), str(_VOICES_PATH))
        logger.info("Kokoro ONNX model loaded.")

        try:
            from misaki.espeak import EspeakG2P

            _g2p = EspeakG2P(language="es")
            logger.info("Spanish G2P (espeak-ng) loaded.")
        except Exception as exc:
            logger.warning("Spanish G2P unavailable (%s), will try direct mode", exc)
            _g2p = None

        return _kokoro, _g2p


def _get_voice_style(kokoro_inst, voice_name: str) -> np.ndarray:
    """Load a voice style array, with caching."""
    if voice_name in _voice_cache:
        return _voice_cache[voice_name]
    style = kokoro_inst.get_voice_style(voice_name)
    _voice_cache[voice_name] = style
    logger.debug("Loaded voice style: %s", voice_name)
    return style


def create_mixed_voice(
    kokoro_inst, voice_a: str, voice_b: str, blend_ratio: float
) -> np.ndarray:
    """Blend two voice embeddings using numpy."""
    s_a = _get_voice_style(kokoro_inst, voice_a)
    s_b = _get_voice_style(kokoro_inst, voice_b)
    return np.add(s_a * (1 - blend_ratio), s_b * blend_ratio)


def _parse_rate(rate_str: str) -> float:
    """Convert rate string like '+10%' to speed float like 1.10."""
    rate_str = rate_str.strip().replace("%", "")
    try:
        return 1.0 + float(rate_str) / 100.0
    except ValueError:
        return 1.0


class KokoroTTSBackend(TTSBackend):
    """Kokoro TTS via ONNX runtime with voice mixing. CPU-friendly, ~200MB RAM."""

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
        """
        kokoro, g2p = await _get_kokoro()
        speed = _parse_rate(rate)

        # Parse voice specification
        if isinstance(voice, np.ndarray):
            voice_style = voice
        elif "+" in voice and ":" in voice:
            voice_style = self._parse_mix_spec(kokoro, voice)
        else:
            try:
                voice_style = _get_voice_style(kokoro, voice)
            except Exception:
                voice_style = _get_voice_style(kokoro, "em_alex")

        def _generate():
            import soundfile as sf

            if g2p:
                phonemes, _ = g2p(text)
                samples, sample_rate = kokoro.create(
                    phonemes, voice=voice_style, speed=speed, is_phonemes=True
                )
            else:
                samples, sample_rate = kokoro.create(
                    text, voice=voice_style, speed=speed, lang="es"
                )

            sf.write(str(output_path), samples, sample_rate)

        await asyncio.to_thread(_generate)
        return output_path

    @staticmethod
    def _parse_mix_spec(kokoro_inst, spec: str) -> np.ndarray:
        """Parse 'am_onyx:0.65+em_alex:0.35' into a blended style."""
        parts = spec.split("+")
        if len(parts) != 2:
            return _get_voice_style(kokoro_inst, "em_alex")

        name_a, ratio_a = parts[0].rsplit(":", 1)
        name_b, ratio_b = parts[1].rsplit(":", 1)

        try:
            r_a = float(ratio_a)
            r_b = float(ratio_b)
        except ValueError:
            r_a, r_b = 0.5, 0.5

        total = r_a + r_b
        return create_mixed_voice(
            kokoro_inst, name_a.strip(), name_b.strip(), r_b / total
        )
