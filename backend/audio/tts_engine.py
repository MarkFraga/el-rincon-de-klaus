import edge_tts
from pathlib import Path


async def synthesize(text: str, voice: str, output_path: Path, rate: str = "+0%", pitch: str = "+0Hz") -> Path:
    """Generate speech audio for a text segment."""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(output_path))
    return output_path
