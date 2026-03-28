from backend.config import KLAUS_VOICE, KLAUS_RATE, KLAUS_PITCH, EXPERT_VOICES, EMOTION_PROSODY


def get_klaus_config():
    return {
        "voice_id": KLAUS_VOICE,
        "base_rate": KLAUS_RATE,
        "base_pitch": KLAUS_PITCH,
    }


def get_expert_config(topic: str) -> dict:
    """Select expert voice deterministically based on topic hash."""
    idx = hash(topic) % len(EXPERT_VOICES)
    return EXPERT_VOICES[idx]


def get_prosody(emotion: str) -> dict:
    """Get rate and pitch adjustments for a given emotion."""
    return EMOTION_PROSODY.get(emotion, EMOTION_PROSODY["neutral"])
