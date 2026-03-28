"""TTS engine with voice character post-processing.

Uses edge-tts for neural speech synthesis, then applies audio effects
via ffmpeg and numpy/scipy to create unique, natural-sounding voices.
"""

import asyncio
import subprocess
import shutil
import struct
from pathlib import Path
from typing import Optional

import edge_tts

# Check if scipy is available for advanced processing
try:
    import numpy as np
    from scipy.signal import butter, lfilter
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


async def synthesize(
    text: str,
    voice: str,
    output_path: Path,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    post_process: Optional[dict] = None,
) -> Path:
    """Generate speech and optionally apply voice character effects."""
    # Step 1: Generate raw TTS audio
    raw_path = output_path.with_suffix(".raw.mp3") if post_process else output_path
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(raw_path))

    # Step 2: Apply post-processing if specified
    if post_process and raw_path.exists():
        await _apply_voice_character(raw_path, output_path, post_process)
        # Clean up raw file
        try:
            raw_path.unlink()
        except Exception:
            pass
    elif post_process and not raw_path.exists():
        # TTS failed silently
        raise FileNotFoundError(f"TTS output not created: {raw_path}")

    return output_path


async def _apply_voice_character(input_path: Path, output_path: Path, config: dict) -> None:
    """Apply voice character effects using ffmpeg filters."""
    pitch_semitones = config.get("pitch_shift_semitones", 0)
    rasp = config.get("rasp_amount", 0.0)
    warmth_db = config.get("warmth_boost_db", 0)
    compression = config.get("compression", False)

    # Build ffmpeg filter chain
    filters = []

    # 1. Pitch shift without changing speed
    if pitch_semitones != 0:
        # Pitch shift: change sample rate then resample back
        # semitone ratio = 2^(n/12)
        ratio = 2 ** (pitch_semitones / 12.0)
        # asetrate changes pitch, atempo corrects speed
        filters.append(f"asetrate=44100*{ratio:.4f}")
        filters.append(f"aresample=44100")
        # Correct duration with atempo
        tempo_correction = 1.0 / ratio
        # atempo only accepts 0.5-2.0, so chain if needed
        while tempo_correction > 2.0:
            filters.append("atempo=2.0")
            tempo_correction /= 2.0
        while tempo_correction < 0.5:
            filters.append("atempo=0.5")
            tempo_correction *= 2.0
        if 0.5 <= tempo_correction <= 2.0:
            filters.append(f"atempo={tempo_correction:.4f}")

    # 2. Add subtle rasp via soft clipping (overdrive effect)
    if rasp > 0:
        # asinh soft-clips the signal creating harmonic distortion
        drive = 1.0 + rasp * 8  # scale rasp to drive amount
        filters.append(f"aeval='val(0)*{drive:.2f}'")
        filters.append("alimiter=limit=0.9:attack=0.1:release=50")

    # 3. Warmth: boost low-mids (200-500Hz)
    if warmth_db > 0:
        filters.append(f"equalizer=f=300:t=q:w=1.5:g={warmth_db}")
        # Also slight high-shelf cut for less sibilance
        filters.append(f"equalizer=f=6000:t=h:w=1:g=-2")

    # 4. Broadcast compression
    if compression:
        filters.append("acompressor=threshold=-18dB:ratio=3:attack=5:release=50:makeup=2dB")

    # 5. Final limiter to prevent clipping
    filters.append("alimiter=limit=0.95:attack=0.5:release=50")

    if not filters:
        # No processing needed, just copy
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
        # Fallback: copy without processing
        shutil.copy2(str(input_path), str(output_path))


def _find_ffmpeg() -> str:
    """Find ffmpeg executable."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    # Try static_ffmpeg
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
    except ImportError:
        pass

    # Try imageio_ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass

    return "ffmpeg"  # hope it's on PATH
