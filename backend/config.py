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

KLAUS_VOICE = "es-ES-AlvaroNeural"
KLAUS_RATE = "+8%"
KLAUS_PITCH = "+3Hz"

EXPERT_VOICES = [
    {"voice_id": "es-MX-JorgeNeural", "name": "Jorge", "country": "México"},
    {"voice_id": "es-AR-TomasNeural", "name": "Tomás", "country": "Argentina"},
    {"voice_id": "es-CO-GonzaloNeural", "name": "Gonzalo", "country": "Colombia"},
    {"voice_id": "es-CL-LorenzoNeural", "name": "Lorenzo", "country": "Chile"},
    {"voice_id": "es-CU-ManuelNeural", "name": "Manuel", "country": "Cuba"},
    {"voice_id": "es-PE-AlexNeural", "name": "Alex", "country": "Perú"},
]

EMOTION_PROSODY = {
    "neutral":     {"rate": "+0%",  "pitch": "+0Hz"},
    "excited":     {"rate": "+10%", "pitch": "+2Hz"},
    "thoughtful":  {"rate": "-5%",  "pitch": "-1Hz"},
    "challenging": {"rate": "+5%",  "pitch": "+1Hz"},
}
