"""Dynamic guest profile generation using Gemini + names database."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from google import genai

from backend.config import GEMINI_API_KEY, GEMINI_MODEL
from backend.guests.voice_mapper import resolve_voice, ALL_COUNTRIES

logger = logging.getLogger(__name__)

# Load names database
_DB_PATH = Path(__file__).parent / "names_db.json"
_NAMES_DB = {}
if _DB_PATH.exists():
    with open(_DB_PATH, "r", encoding="utf-8") as f:
        _NAMES_DB = json.load(f)

# Archetypes with weights
ARCHETYPES = [
    ("academic_expert", 20),
    ("everyday_person", 20),
    ("journalist", 15),
    ("young_prodigy", 10),
    ("retired_veteran", 15),
    ("klaus_is_expert", 10),
    ("unexpected", 10),
]

ARCHETYPE_DESCRIPTIONS = {
    "academic_expert": "Profesor/a, investigador/a, PhD. Conocimiento tecnico profundo.",
    "everyday_person": "Persona comun (agricultor, taxista, cocinero, etc.) con experiencia personal fascinante sobre el tema.",
    "journalist": "Periodista de investigacion o documentalista. Perspectiva narrativa y storytelling.",
    "young_prodigy": "Estudiante brillante, joven inventor/a, perspectiva fresca de nueva generacion.",
    "retired_veteran": "Profesional jubilado/a con 30+ anios de experiencia. Historias de guerra, sabiduria.",
    "klaus_is_expert": "Persona curiosa que quiere aprender. Klaus es quien sabe del tema y ensenia.",
    "unexpected": "Alguien inesperado: comediante, artista, deportista, chef... con conexion sorprendente al tema.",
}

DYNAMIC_MAP = {
    "academic_expert": "guest_expert",
    "everyday_person": "interview",
    "journalist": "debate",
    "young_prodigy": "guest_expert",
    "retired_veteran": "storytelling",
    "klaus_is_expert": "guest_learner",
    "unexpected": "interview",
}


@dataclass
class GuestProfile:
    full_name: str = ""
    country: str = "mexico"
    gender: str = "male"
    age_range: str = "mid"
    archetype: str = "academic_expert"
    personality_traits: list = field(default_factory=lambda: ["apasionado"])
    connection_to_topic: str = ""
    dynamic: str = "guest_expert"
    speaking_style: str = ""
    voice_id: str = ""
    post_process: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _weighted_choice(items_with_weights):
    items, weights = zip(*items_with_weights)
    return random.choices(items, weights=weights, k=1)[0]


def _random_name(gender: str, country: str) -> str:
    """Generate a random name from the database."""
    first_names = _NAMES_DB.get("first_names", {}).get(gender, {})
    surnames = _NAMES_DB.get("surnames", {})

    country_key = country.lower().replace(" ", "_")

    # Get first name
    names_list = first_names.get(country_key, first_names.get("mexico", ["Carlos"]))
    first = random.choice(names_list) if names_list else "Carlos"

    # Get surname
    surname_list = surnames.get(country_key, surnames.get("mexico", ["Garcia"]))
    last = random.choice(surname_list) if surname_list else "Garcia"

    return f"{first} {last}"


async def generate_guest(topic: str) -> GuestProfile:
    """Generate a unique guest profile for the given topic.

    Uses Gemini for intelligent guest creation with fallback to random generation.
    """
    archetype = _weighted_choice(ARCHETYPES)

    try:
        return await _generate_with_gemini(topic, archetype)
    except Exception as exc:
        logger.warning("Gemini guest generation failed, using fallback: %s", exc)
        return _generate_fallback(topic, archetype)


async def _generate_with_gemini(topic: str, archetype: str) -> GuestProfile:
    """Use Gemini to create an intelligent guest profile."""
    client = genai.Client(api_key=GEMINI_API_KEY)

    countries_str = ", ".join(sorted(set(ALL_COUNTRIES)))

    prompt = f"""Genera un perfil de invitado para un podcast en espanol sobre: "{topic}"

El arquetipo del invitado es: {archetype} ({ARCHETYPE_DESCRIPTIONS[archetype]})

Responde SOLO con un JSON valido (sin markdown, sin texto extra):
{{
  "full_name": "nombre completo culturalmente apropiado",
  "country": "uno de: {countries_str}",
  "gender": "male o female",
  "age_range": "young (18-30), mid (31-55), o senior (56+)",
  "personality_traits": ["rasgo1", "rasgo2"],
  "connection_to_topic": "por que esta persona esta en el podcast, 1 frase",
  "speaking_style": "como habla esta persona, 1 frase breve"
}}"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=prompt,
    )

    raw = response.text.strip()

    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError("Could not parse guest profile JSON")

    # Build profile
    country = data.get("country", "mexico").lower().replace(" ", "_")
    gender = data.get("gender", "male").lower()
    age_range = data.get("age_range", "mid").lower()
    dynamic = DYNAMIC_MAP.get(archetype, "guest_expert")

    voice_id, post_process = resolve_voice(country, gender, age_range)

    return GuestProfile(
        full_name=data.get("full_name", _random_name(gender, country)),
        country=country,
        gender=gender,
        age_range=age_range,
        archetype=archetype,
        personality_traits=data.get("personality_traits", ["apasionado"]),
        connection_to_topic=data.get("connection_to_topic", f"Invitado para hablar sobre {topic}"),
        dynamic=dynamic,
        speaking_style=data.get("speaking_style", "habla con claridad y pasion"),
        voice_id=voice_id,
        post_process=post_process,
    )


def _generate_fallback(topic: str, archetype: str) -> GuestProfile:
    """Fallback: random generation from names database."""
    gender = random.choice(["male", "female"])
    country = random.choice(ALL_COUNTRIES)
    age_map = {
        "young_prodigy": "young",
        "retired_veteran": "senior",
        "academic_expert": "mid",
    }
    age_range = age_map.get(archetype, random.choice(["young", "mid", "senior"]))
    dynamic = DYNAMIC_MAP.get(archetype, "guest_expert")

    full_name = _random_name(gender, country)
    voice_id, post_process = resolve_voice(country, gender, age_range)

    return GuestProfile(
        full_name=full_name,
        country=country,
        gender=gender,
        age_range=age_range,
        archetype=archetype,
        personality_traits=["curioso", "apasionado"],
        connection_to_topic=f"Invitado para hablar sobre {topic}",
        dynamic=dynamic,
        speaking_style="habla con naturalidad",
        voice_id=voice_id,
        post_process=post_process,
    )
