import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

from pydub import AudioSegment
from backend.audio.tts_engine import synthesize
from backend.audio.voice_profiles import get_klaus_profile, get_prosody
from backend.audio.voice_generator import KLAUS_VOICE_RECIPE, VoiceRecipe
from backend.config import OUTPUT_DIR, TTS_BACKEND
from backend.ws_manager import ws_manager

logger = logging.getLogger(__name__)


def _recipe_to_voice_str(recipe: VoiceRecipe) -> str:
    """Convert a VoiceRecipe to a Kokoro mix spec string."""
    r_a = 1 - recipe.blend_ratio
    r_b = recipe.blend_ratio
    return f"{recipe.voice_a}:{r_a:.2f}+{recipe.voice_b}:{r_b:.2f}"


class AudioPipeline:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.temp_dir = Path(tempfile.mkdtemp(prefix="klaus_"))

    async def generate(
        self,
        script: list,
        expert_voice_id: str,
        expert_post_process: dict = None,
        guest_voice_recipe: Optional[VoiceRecipe] = None,
    ) -> Path:
        """Generate full podcast audio from script segments.

        When using Kokoro TTS backend, voice recipes (mixed voices)
        are used instead of edge-tts voice IDs.
        """
        if not script:
            raise ValueError("Cannot generate audio from an empty script")

        segments = []
        total = len(script)
        failed_count = 0
        klaus = get_klaus_profile()
        use_kokoro = TTS_BACKEND.lower() == "kokoro"

        # Prepare voice identifiers
        if use_kokoro:
            klaus_voice = _recipe_to_voice_str(KLAUS_VOICE_RECIPE)
            klaus_pp = KLAUS_VOICE_RECIPE.post_process
            if guest_voice_recipe:
                guest_voice = _recipe_to_voice_str(guest_voice_recipe)
                guest_pp = guest_voice_recipe.post_process
                guest_speed_mult = guest_voice_recipe.speed_multiplier
            else:
                guest_voice = "em_alex"
                guest_pp = expert_post_process
                guest_speed_mult = 1.07
        else:
            klaus_voice = klaus["voice_id"]
            klaus_pp = klaus.get("post_process")
            guest_voice = expert_voice_id
            guest_pp = expert_post_process
            guest_speed_mult = 1.0

        for i, seg in enumerate(script):
            text = (seg.get("text") or "").strip()
            if not text:
                continue

            if seg["speaker"] == "KLAUS":
                voice = klaus_voice
                base_rate = "+10%"
                base_pitch = "-4Hz"
                seg_post_process = klaus_pp
            else:
                voice = guest_voice
                # Apply guest speed multiplier as base rate for Kokoro
                if use_kokoro and guest_speed_mult != 1.0:
                    base_rate = f"+{int((guest_speed_mult - 1) * 100)}%"
                else:
                    base_rate = "+7%"
                base_pitch = "+0Hz"
                seg_post_process = guest_pp

            # Emotion adjustments
            emotion_prosody = get_prosody(seg.get("emotion", "neutral"))
            rate = emotion_prosody["rate"] if emotion_prosody["rate"] != "+0%" else base_rate
            pitch = emotion_prosody["pitch"] if emotion_prosody["pitch"] != "+0Hz" else base_pitch

            # Kokoro outputs .wav, edge-tts outputs .mp3
            ext = ".wav" if use_kokoro else ".mp3"
            seg_path = self.temp_dir / f"seg_{i:03d}{ext}"
            try:
                await synthesize(
                    text, voice, seg_path,
                    rate=rate, pitch=pitch,
                    post_process=seg_post_process,
                )
                if ext == ".wav":
                    audio_seg = AudioSegment.from_wav(str(seg_path))
                else:
                    audio_seg = AudioSegment.from_mp3(str(seg_path))
                segments.append(audio_seg)
            except Exception as e:
                failed_count += 1
                logger.warning("TTS error on segment %d/%d: %s", i, total, e)
                continue

            # Natural pauses -- shorter = more dynamic conversation
            if i < total - 1:
                next_speaker = script[i + 1]["speaker"] if i + 1 < total else seg["speaker"]
                emotion = seg.get("emotion", "neutral")
                if next_speaker != seg["speaker"]:
                    if emotion in ("excited", "surprised", "humorous"):
                        pause_ms = 280 + (i % 3) * 50
                    elif emotion in ("thoughtful", "nostalgic"):
                        pause_ms = 450 + (i % 3) * 60
                    else:
                        pause_ms = 350 + (i % 3) * 50
                else:
                    pause_ms = 100 + (i % 2) * 40
                segments.append(AudioSegment.silent(duration=pause_ms))

            if i % 5 == 0 or i == total - 1:
                pct = 70 + int((i / total) * 30)
                await ws_manager.broadcast(self.job_id, {
                    "agent": "audio",
                    "status": "running",
                    "message": f"Generando audio {i+1}/{total}...",
                    "progress": pct
                })

        if failed_count > 0:
            logger.warning("Audio generation: %d/%d segments failed TTS.", failed_count, total)

        if not segments:
            raise ValueError(f"No audio segments generated. All {total} TTS calls failed.")

        final = segments[0]
        for seg in segments[1:]:
            final = final + seg

        output_path = OUTPUT_DIR / f"{self.job_id}.mp3"
        final.export(str(output_path), format="mp3", bitrate="192k")
        logger.info("Audio exported: %s (%.1f MB, %.0f sec)",
                     output_path.name, output_path.stat().st_size / 1024 / 1024, len(final) / 1000)

        # Cleanup temp files
        for f in self.temp_dir.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass

        return output_path
