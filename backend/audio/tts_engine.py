"""TTS engine with pluggable backends and voice character post-processing.

Supports multiple backends:
- "edge": Microsoft Edge TTS (free, cloud, decent quality) [DEFAULT]
- "kokoro": Kokoro TTS (82M params, CPU, better quality, Apache 2.0)
- "elevenlabs": ElevenLabs API (premium quality, requires API key)

Set TTS_BACKEND env var to choose. Falls back to edge on errors.
"""

import asyncio
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from backend.config import TTS_BACKEND, KOKORO_API_URL

logger = logging.getLogger(__name__)

# Lazy-loaded backend instance
_backend = None


def _get_backend():
    """Get or create the TTS backend based on config."""
    global _backend
    if _backend is not None:
        return _backend

    backend_name = TTS_BACKEND.lower().strip()

    if backend_name == "kokoro":
        if KOKORO_API_URL:
            try:
                from backend.audio.tts_backends.kokoro_remote_backend import KokoroRemoteTTSBackend
                _backend = KokoroRemoteTTSBackend(KOKORO_API_URL)
                logger.info("Using Kokoro REMOTE TTS backend at %s", KOKORO_API_URL)
                return _backend
            except Exception as exc:
                logger.warning("Kokoro remote unavailable (%s), trying local", exc)
        try:
            from backend.audio.tts_backends.kokoro_backend import KokoroTTSBackend
            _backend = KokoroTTSBackend()
            logger.info("Using Kokoro LOCAL TTS backend")
            return _backend
        except Exception as exc:
            logger.warning("Kokoro TTS unavailable (%s), falling back to edge-tts", exc)

    elif backend_name == "elevenlabs":
        try:
            from backend.audio.tts_backends.elevenlabs_backend import ElevenLabsTTSBackend
            _backend = ElevenLabsTTSBackend()
            logger.info("Using ElevenLabs TTS backend")
            return _backend
        except Exception as exc:
            logger.warning("ElevenLabs TTS unavailable (%s), falling back to edge-tts", exc)

    # Default: edge-tts
    from backend.audio.tts_backends.edge_backend import EdgeTTSBackend
    _backend = EdgeTTSBackend()
    logger.info("Using Edge TTS backend")
    return _backend


async def synthesize(
    text: str,
    voice: str,
    output_path: Path,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    post_process: Optional[dict] = None,
) -> Path:
    """Generate speech and optionally apply voice character effects."""
    backend = _get_backend()

    # Step 1: Generate raw TTS audio
    raw_path = output_path.with_suffix(".raw.mp3") if post_process else output_path

    try:
        await backend.synthesize(text, voice, raw_path, rate=rate, pitch=pitch)
    except Exception as exc:
        # If non-default backend fails, try edge-tts as fallback
        if TTS_BACKEND.lower() != "edge":
            logger.warning("Backend %s failed, falling back to edge-tts: %s", TTS_BACKEND, exc)
            from backend.audio.tts_backends.edge_backend import EdgeTTSBackend
            fallback = EdgeTTSBackend()
            await fallback.synthesize(text, voice, raw_path, rate=rate, pitch=pitch)
        else:
            raise

    # Step 2: Apply post-processing if specified
    if post_process and raw_path.exists():
        await _apply_voice_character(raw_path, output_path, post_process)
        try:
            raw_path.unlink()
        except Exception:
            pass
    elif post_process and not raw_path.exists():
        raise FileNotFoundError(f"TTS output not created: {raw_path}")

    return output_path


async def _apply_voice_character(input_path: Path, output_path: Path, config: dict) -> None:
    """Apply voice character effects using ffmpeg filters."""
    pitch_semitones = config.get("pitch_shift_semitones", 0)
    rasp = config.get("rasp_amount", 0.0)
    warmth_db = config.get("warmth_boost_db", 0)
    compression = config.get("compression", False)

    filters = []

    if pitch_semitones != 0:
        ratio = 2 ** (pitch_semitones / 12.0)
        filters.append(f"asetrate=44100*{ratio:.4f}")
        filters.append("aresample=44100")
        tempo_correction = 1.0 / ratio
        while tempo_correction > 2.0:
            filters.append("atempo=2.0")
            tempo_correction /= 2.0
        while tempo_correction < 0.5:
            filters.append("atempo=0.5")
            tempo_correction *= 2.0
        if 0.5 <= tempo_correction <= 2.0:
            filters.append(f"atempo={tempo_correction:.4f}")

    if rasp > 0:
        drive = 1.0 + rasp * 8
        filters.append(f"aeval='val(0)*{drive:.2f}'")
        filters.append("alimiter=limit=0.9:attack=0.1:release=50")

    if warmth_db > 0:
        filters.append(f"equalizer=f=300:t=q:w=1.5:g={warmth_db}")
        filters.append("equalizer=f=6000:t=h:w=1:g=-2")

    if compression:
        filters.append("acompressor=threshold=-18dB:ratio=3:attack=5:release=50:makeup=2dB")

    filters.append("alimiter=limit=0.95:attack=0.5:release=50")

    if not filters:
        shutil.copy2(str(input_path), str(output_path))
        return

    filter_chain = ",".join(filters)
    ffmpeg = _find_ffmpeg()
    cmd = [
        ffmpeg, "-y", "-i", str(input_path),
        "-af", filter_chain,
        "-ar", "44100",
        "-b:a", "192k",
        str(output_path),
    ]

    proc = await asyncio.to_thread(
        subprocess.run, cmd,
        capture_output=True, timeout=30,
    )

    if proc.returncode != 0:
        shutil.copy2(str(input_path), str(output_path))


def _find_ffmpeg() -> str:
    """Find ffmpeg executable."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
    except ImportError:
        pass
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    return "ffmpeg"
