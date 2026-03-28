import asyncio
import tempfile
from pathlib import Path

# Add static-ffmpeg to PATH so pydub finds ffmpeg + ffprobe
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

from pydub import AudioSegment
from backend.audio.tts_engine import synthesize
from backend.audio.voice_profiles import get_klaus_config, get_prosody
from backend.config import OUTPUT_DIR
from backend.ws_manager import ws_manager


class AudioPipeline:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.temp_dir = Path(tempfile.mkdtemp(prefix="klaus_"))

    async def generate(self, script: list, expert_voice_id: str) -> Path:
        """Generate full podcast audio from script segments."""
        segments = []
        total = len(script)

        for i, seg in enumerate(script):
            # Determine voice and prosody
            if seg["speaker"] == "KLAUS":
                klaus = get_klaus_config()
                voice = klaus["voice_id"]
                base_rate = klaus["base_rate"]
                base_pitch = klaus["base_pitch"]
            else:
                voice = expert_voice_id
                base_rate = "+0%"
                base_pitch = "+0Hz"

            # Adjust for emotion
            emotion_prosody = get_prosody(seg.get("emotion", "neutral"))
            rate = emotion_prosody["rate"] if emotion_prosody["rate"] != "+0%" else base_rate
            pitch = emotion_prosody["pitch"] if emotion_prosody["pitch"] != "+0Hz" else base_pitch

            # Generate segment audio
            seg_path = self.temp_dir / f"seg_{i:03d}.mp3"
            try:
                await synthesize(seg["text"], voice, seg_path, rate=rate, pitch=pitch)
                audio_seg = AudioSegment.from_mp3(str(seg_path))
                segments.append(audio_seg)
            except Exception as e:
                print(f"TTS error on segment {i}: {e}")
                continue

            # Add pause between speakers
            if i < total - 1:
                next_speaker = script[i + 1]["speaker"] if i + 1 < total else seg["speaker"]
                pause_ms = 700 if next_speaker != seg["speaker"] else 250
                segments.append(AudioSegment.silent(duration=pause_ms))

            # Report progress
            pct = 70 + int((i / total) * 30)
            await ws_manager.broadcast(self.job_id, {
                "agent": "audio",
                "status": "running",
                "message": f"Generando audio {i+1}/{total}...",
                "progress": pct
            })

        # Merge all segments
        if not segments:
            raise ValueError("No audio segments generated")

        final = segments[0]
        for seg in segments[1:]:
            final = final + seg

        # Export
        output_path = OUTPUT_DIR / f"{self.job_id}.mp3"
        final.export(str(output_path), format="mp3", bitrate="192k")

        # Cleanup temp files
        for f in self.temp_dir.glob("*.mp3"):
            try:
                f.unlink()
            except Exception:
                pass

        return output_path
