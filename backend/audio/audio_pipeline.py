import asyncio
import logging
import tempfile
from pathlib import Path

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

from pydub import AudioSegment
from backend.audio.tts_engine import synthesize
from backend.audio.voice_profiles import get_klaus_profile, get_prosody
from backend.config import OUTPUT_DIR
from backend.ws_manager import ws_manager

logger = logging.getLogger(__name__)


class AudioPipeline:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.temp_dir = Path(tempfile.mkdtemp(prefix="klaus_"))

    async def generate(self, script: list, expert_voice_id: str, expert_post_process: dict = None) -> Path:
        """Generate full podcast audio from script segments.

        Strategy: Generate TTS WITHOUT per-segment ffmpeg post-processing
        (which is too slow on limited CPUs). Use edge-tts pitch/rate params
        directly for voice character. This is much faster.
        """
        if not script:
            raise ValueError("Cannot generate audio from an empty script")

        segments = []
        total = len(script)
        failed_count = 0
        klaus = get_klaus_profile()

        for i, seg in enumerate(script):
            text = (seg.get("text") or "").strip()
            if not text:
                continue

            if seg["speaker"] == "KLAUS":
                voice = klaus["voice_id"]
                # Apply Klaus character via edge-tts params directly (no ffmpeg)
                base_rate = "+3%"
                base_pitch = "-4Hz"  # lower pitch for older voice
            else:
                voice = expert_voice_id
                base_rate = "+0%"
                base_pitch = "+0Hz"

            # Emotion adjustments
            emotion_prosody = get_prosody(seg.get("emotion", "neutral"))
            rate = emotion_prosody["rate"] if emotion_prosody["rate"] != "+0%" else base_rate
            pitch = emotion_prosody["pitch"] if emotion_prosody["pitch"] != "+0Hz" else base_pitch

            seg_path = self.temp_dir / f"seg_{i:03d}.mp3"
            try:
                # Generate TTS directly without post-processing (FAST)
                await synthesize(
                    text, voice, seg_path,
                    rate=rate, pitch=pitch,
                    post_process=None,  # Skip per-segment ffmpeg = 10x faster
                )
                audio_seg = AudioSegment.from_mp3(str(seg_path))
                segments.append(audio_seg)
            except Exception as e:
                failed_count += 1
                logger.warning("TTS error on segment %d/%d: %s", i, total, e)
                continue

            # Natural pauses between speakers
            if i < total - 1:
                next_speaker = script[i + 1]["speaker"] if i + 1 < total else seg["speaker"]
                if next_speaker != seg["speaker"]:
                    pause_ms = 600 + (i % 3) * 100
                else:
                    pause_ms = 200 + (i % 2) * 50
                segments.append(AudioSegment.silent(duration=pause_ms))

            # Report progress every 5 segments to reduce WS spam
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
        for f in self.temp_dir.glob("*.mp3"):
            try:
                f.unlink()
            except Exception:
                pass

        return output_path
