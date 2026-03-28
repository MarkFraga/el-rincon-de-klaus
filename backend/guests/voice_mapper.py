"""Maps guest profiles to edge-tts voices and audio post-processing."""

# Complete registry of all 44 Spanish edge-tts voices
VOICE_REGISTRY = {
    ("argentina", "male"): "es-AR-TomasNeural",
    ("argentina", "female"): "es-AR-ElenaNeural",
    ("bolivia", "male"): "es-BO-MarceloNeural",
    ("bolivia", "female"): "es-BO-SofiaNeural",
    ("chile", "male"): "es-CL-LorenzoNeural",
    ("chile", "female"): "es-CL-CatalinaNeural",
    ("colombia", "male"): "es-CO-GonzaloNeural",
    ("colombia", "female"): "es-CO-SalomeNeural",
    ("costa_rica", "male"): "es-CR-JuanNeural",
    ("costa_rica", "female"): "es-CR-MariaNeural",
    ("cuba", "male"): "es-CU-ManuelNeural",
    ("cuba", "female"): "es-CU-BelkysNeural",
    ("dominican_republic", "male"): "es-DO-EmilioNeural",
    ("dominican_republic", "female"): "es-DO-RamonaNeural",
    ("ecuador", "male"): "es-EC-LuisNeural",
    ("ecuador", "female"): "es-EC-AndreaNeural",
    ("spain", "male"): "es-ES-AlvaroNeural",
    ("spain", "female"): "es-ES-ElviraNeural",
    ("equatorial_guinea", "male"): "es-GQ-JavierNeural",
    ("equatorial_guinea", "female"): "es-GQ-TeresaNeural",
    ("guatemala", "male"): "es-GT-AndresNeural",
    ("guatemala", "female"): "es-GT-MartaNeural",
    ("honduras", "male"): "es-HN-CarlosNeural",
    ("honduras", "female"): "es-HN-KarlaNeural",
    ("mexico", "male"): "es-MX-JorgeNeural",
    ("mexico", "female"): "es-MX-DaliaNeural",
    ("nicaragua", "male"): "es-NI-FedericoNeural",
    ("nicaragua", "female"): "es-NI-YolandaNeural",
    ("panama", "male"): "es-PA-RobertoNeural",
    ("panama", "female"): "es-PA-MargaritaNeural",
    ("peru", "male"): "es-PE-AlexNeural",
    ("peru", "female"): "es-PE-CamilaNeural",
    ("puerto_rico", "male"): "es-PR-VictorNeural",
    ("puerto_rico", "female"): "es-PR-KarinaNeural",
    ("paraguay", "male"): "es-PY-MarioNeural",
    ("paraguay", "female"): "es-PY-TaniaNeural",
    ("el_salvador", "male"): "es-SV-RodrigoNeural",
    ("el_salvador", "female"): "es-SV-LorenaNeural",
    ("us", "male"): "es-US-AlonsoNeural",
    ("us", "female"): "es-US-PalomaNeural",
    ("uruguay", "male"): "es-UY-MateoNeural",
    ("uruguay", "female"): "es-UY-ValentinaNeural",
    ("venezuela", "male"): "es-VE-SebastianNeural",
    ("venezuela", "female"): "es-VE-PaolaNeural",
}

# All country keys for random selection
ALL_COUNTRIES = list(set(k[0] for k in VOICE_REGISTRY.keys()))

# Age-based voice post-processing
AGE_PROFILES = {
    "young": {
        "pitch_shift_semitones": 1,
        "rasp_amount": 0.0,
        "warmth_boost_db": 1,
        "compression": True,
    },
    "mid": {
        "pitch_shift_semitones": 0,
        "rasp_amount": 0.03,
        "warmth_boost_db": 2,
        "compression": True,
    },
    "senior": {
        "pitch_shift_semitones": -2,
        "rasp_amount": 0.08,
        "warmth_boost_db": 3,
        "compression": True,
    },
}

KLAUS_VOICE_ID = "es-ES-AlvaroNeural"


def resolve_voice(country: str, gender: str, age_range: str = "mid") -> tuple:
    """Map guest profile to (voice_id, post_process_dict).

    Ensures the guest voice is different from Klaus (es-ES-AlvaroNeural).
    """
    key = (country.lower().replace(" ", "_"), gender.lower())
    voice_id = VOICE_REGISTRY.get(key)

    if not voice_id:
        # Fallback to Mexico if country not found
        voice_id = VOICE_REGISTRY.get(("mexico", gender.lower()), "es-MX-JorgeNeural")

    # Avoid collision with Klaus voice
    if voice_id == KLAUS_VOICE_ID:
        if gender == "male":
            voice_id = "es-MX-JorgeNeural"  # Different male voice
        else:
            voice_id = "es-ES-ElviraNeural"  # Spanish female instead

    post_process = dict(AGE_PROFILES.get(age_range, AGE_PROFILES["mid"]))

    return voice_id, post_process
