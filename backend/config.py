import os
from pathlib import Path

# Load .env for local dev; on Render env vars are set directly
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PORT = int(os.getenv("PORT", "8000"))
GEMINI_MODEL = "gemini-2.5-flash"

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# TTS backend: "edge" (default), "kokoro", or "elevenlabs"
TTS_BACKEND = os.getenv("TTS_BACKEND", "edge")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# Emotion-to-prosody mapping for TTS
EMOTION_PROSODY = {
    "neutral":     {"rate": "+0%",  "pitch": "+0Hz"},
    "excited":     {"rate": "+8%",  "pitch": "+2Hz"},
    "thoughtful":  {"rate": "-5%",  "pitch": "-1Hz"},
    "challenging": {"rate": "+4%",  "pitch": "+1Hz"},
    "humorous":    {"rate": "+6%",  "pitch": "+1Hz"},
    "nostalgic":   {"rate": "-3%",  "pitch": "-1Hz"},
    "surprised":   {"rate": "+10%", "pitch": "+3Hz"},
    "skeptical":   {"rate": "+0%",  "pitch": "+1Hz"},
}
