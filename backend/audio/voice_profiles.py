"""Voice profiles for El Rincon de Klaus.

Klaus: older male, raspy but dynamic, characteristic deep voice.
Experts: diverse pool - male/female, different ages, regional accents.
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

# ── EXPERTS ──────────────────────────────────────────────────────
# Diverse pool: male/female, different regions, ages implied by voice
EXPERT_VOICES = [
    # Male voices
    {
        "voice_id": "es-MX-JorgeNeural",
        "name": "Jorge Ramirez",
        "country": "Mexico",
        "gender": "male",
        "description": "Investigador senior, voz grave y pausada",
        "post_process": {"pitch_shift_semitones": -1, "rasp_amount": 0.05, "warmth_boost_db": 2, "compression": True},
    },
    {
        "voice_id": "es-AR-TomasNeural",
        "name": "Martin Pellegrini",
        "country": "Argentina",
        "gender": "male",
        "description": "Profesor universitario, apasionado, acento rioplatense",
        "post_process": {"pitch_shift_semitones": 0, "rasp_amount": 0.08, "warmth_boost_db": 1, "compression": True},
    },
    {
        "voice_id": "es-CO-GonzaloNeural",
        "name": "Gonzalo Herrera",
        "country": "Colombia",
        "gender": "male",
        "description": "Cientifico joven, voz clara y energica",
        "post_process": {"pitch_shift_semitones": 1, "rasp_amount": 0.0, "warmth_boost_db": 1, "compression": True},
    },
    {
        "voice_id": "es-CL-LorenzoNeural",
        "name": "Lorenzo Fuentes",
        "country": "Chile",
        "gender": "male",
        "description": "Academico veterano, voz profunda",
        "post_process": {"pitch_shift_semitones": -2, "rasp_amount": 0.1, "warmth_boost_db": 2, "compression": True},
    },
    # Female voices
    {
        "voice_id": "es-MX-DaliaNeural",
        "name": "Dalia Moreno",
        "country": "Mexico",
        "gender": "female",
        "description": "Doctora en ciencias, voz firme y articulada",
        "post_process": {"pitch_shift_semitones": 0, "rasp_amount": 0.0, "warmth_boost_db": 2, "compression": True},
    },
    {
        "voice_id": "es-CO-SalomeNeural",
        "name": "Salome Rios",
        "country": "Colombia",
        "gender": "female",
        "description": "Investigadora postdoctoral, voz calida y expresiva",
        "post_process": {"pitch_shift_semitones": -1, "rasp_amount": 0.0, "warmth_boost_db": 3, "compression": True},
    },
    {
        "voice_id": "es-ES-ElviraNeural",
        "name": "Elvira Navarro",
        "country": "Espana",
        "gender": "female",
        "description": "Catedratica, autoridad en su campo, voz madura",
        "post_process": {"pitch_shift_semitones": -1, "rasp_amount": 0.03, "warmth_boost_db": 2, "compression": True},
    },
    {
        "voice_id": "es-AR-ElenaNeural",
        "name": "Elena Bustamante",
        "country": "Argentina",
        "gender": "female",
        "description": "Divulgadora cientifica, expresiva, acento porteno",
        "post_process": {"pitch_shift_semitones": 0, "rasp_amount": 0.0, "warmth_boost_db": 1, "compression": True},
    },
    {
        "voice_id": "es-CU-ManuelNeural",
        "name": "Manuel Valdez",
        "country": "Cuba",
        "gender": "male",
        "description": "Profesor emerito, voz ronca y sabia",
        "post_process": {"pitch_shift_semitones": -2, "rasp_amount": 0.12, "warmth_boost_db": 3, "compression": True},
    },
    {
        "voice_id": "es-PE-AlexNeural",
        "name": "Alex Quispe",
        "country": "Peru",
        "gender": "male",
        "description": "Ingeniero de datos, joven, voz clara",
        "post_process": {"pitch_shift_semitones": 1, "rasp_amount": 0.0, "warmth_boost_db": 1, "compression": True},
    },
]


def get_klaus_profile() -> dict:
    return KLAUS_PROFILE


def get_expert_profile(topic: str) -> dict:
    """Select expert deterministically based on topic hash."""
    import hashlib
    h = int(hashlib.md5(topic.encode()).hexdigest(), 16)
    return EXPERT_VOICES[h % len(EXPERT_VOICES)]


def get_prosody(emotion: str) -> dict:
    return EMOTION_PROSODY.get(emotion, EMOTION_PROSODY["neutral"])
