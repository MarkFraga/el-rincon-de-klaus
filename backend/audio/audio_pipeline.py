import asyncio
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


class AudioPipeline:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.temp_dir = Path(tempfile.mkdtemp(prefix="klaus_"))

    async def generate(self, script: list, expert_voice_id: str, expert_post_process: dict = None) -> Path:
        """Generate full podcast audio from script segments with voice effects."""
        segments = []
        total = len(script)
        klaus = get_klaus_profile()

        for i, seg in enumerate(script):
            if seg["speaker"] == "KLAUS":
                voice = klaus["voice_id"]
                base_rate = klaus["base_rate"]
                base_pitch = klaus["base_pitch"]
                post_process = klaus["post_process"]
            else:
                voice = expert_voice_id
                base_rate = "+0%"
                base_pitch = "+0Hz"
                post_process = expert_post_process

            # Emotion adjustments
            emotion_prosody = get_prosody(seg.get("emotion", "neutral"))
            rate = emotion_prosody["rate"] if emotion_prosody["rate"] != "+0%" else base_rate
            pitch = emotion_prosody["pitch"] if emotion_prosody["pitch"] != "+0Hz" else base_pitch

            seg_path = self.temp_dir / f"seg_{i:03d}.mp3"
            try:
                await synthesize(
                    seg["text"], voice, seg_path,
                    rate=rate, pitch=pitch,
                    post_process=post_process,
                )
                audio_seg = AudioSegment.from_mp3(str(seg_path))
                segments.append(audio_seg)
            except Exception as e:
                print(f"TTS error on segment {i}: {e}")
                continue

            # Natural pauses between speakers
            if i < total - 1:
                next_speaker = script[i + 1]["speaker"] if i + 1 < total else seg["speaker"]
                if next_speaker != seg["speaker"]:
                    # Speaker change: longer, variable pause
                    pause_ms = 600 + (i % 3) * 100  # 600-800ms variation
                else:
                    pause_ms = 200 + (i % 2) * 50  # 200-250ms variation
                segments.append(AudioSegment.silent(duration=pause_ms))

            pct = 70 + int((i / total) * 30)
            await ws_manager.broadcast(self.job_id, {
                "agent": "audio",
                "status": "running",
                "message": f"Generando audio {i+1}/{total}...",
                "progress": pct
            })

        if not segments:
            raise ValueError("No audio segments generated")

        final = segments[0]
        for seg in segments[1:]:
            final = final + seg

        output_path = OUTPUT_DIR / f"{self.job_id}.mp3"
        final.export(str(output_path), format="mp3", bitrate="192k")

        for f in self.temp_dir.glob("*.mp3"):
            try:
                f.unlink()
            except Exception:
                pass

        return output_path
