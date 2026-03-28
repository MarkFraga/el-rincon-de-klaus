"""Voice profiles for El Rincon de Klaus.

Klaus: older male, raspy but dynamic, characteristic deep voice.
Guest voices are now determined dynamically by the guest generator.
"""

from backend.config import EMOTION_PROSODY

# ── KLAUS ────────────────────────────────────────────────────────
# Base: Alvaro (Spain) - deep, confident male voice
# Post-processing: pitch down, add rasp/gravel, warm EQ
KLAUS_PROFILE = {
    "voice_id": "es-ES-AlvaroNeural",
    "base_rate": "+5%",       # slightly dynamic pace
    "base_pitch": "-2Hz",     # slightly lower base
    "post_process": {
        "pitch_shift_semitones": -3,    # lower voice = older sound
        "rasp_amount": 0.15,            # subtle harmonic distortion
        "warmth_boost_db": 3,           # boost low-mids for warmth
        "compression": True,            # broadcast compression
    },
}


def get_klaus_profile() -> dict:
    return KLAUS_PROFILE


def get_prosody(emotion: str) -> dict:
    return EMOTION_PROSODY.get(emotion, EMOTION_PROSODY["neutral"])
