"""Dynamic voice generation via Kokoro voice mixing + ffmpeg post-processing.

Creates unique voices by:
1. Blending 2 Kokoro base voice embeddings at variable ratios
2. Applying age/gender-appropriate post-processing (pitch, rasp, warmth)
3. Using guest name as seed for reproducibility
4. Tracking recent voices to avoid repetition

This gives effectively unlimited unique voices from ~50 base embeddings.
"""

from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

# All usable Kokoro voices (any voice works with any language pipeline)
# Grouped by perceived gender/character for intelligent mixing
MALE_VOICES = [
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
    "am_michael", "am_onyx", "am_puck",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    "em_alex",
]

FEMALE_VOICES = [
    "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
    "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "ef_dora",
]

# Deep/authoritative male voices (good base for Klaus)
DEEP_MALE_VOICES = ["am_onyx", "am_michael", "am_fenrir", "bm_george", "bm_daniel"]

# Warm/bright voices for contrast
BRIGHT_VOICES = ["af_heart", "af_bella", "am_puck", "af_nova", "bf_emma"]


@dataclass
class VoiceRecipe:
    """A unique voice created by mixing base voices + post-processing."""
    voice_a: str = "em_alex"
    voice_b: str = "am_adam"
    blend_ratio: float = 0.5  # 0.0 = all voice_a, 1.0 = all voice_b
    post_process: dict = field(default_factory=dict)
    speed_multiplier: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


# Klaus's fixed, unique voice recipe
KLAUS_VOICE_RECIPE = VoiceRecipe(
    voice_a="am_onyx",      # Deep, authoritative American male
    voice_b="em_alex",      # Spanish male (for accent blending)
    blend_ratio=0.35,       # 65% onyx + 35% alex
    post_process={
        "pitch_shift_semitones": -3,
        "rasp_amount": 0.18,
        "warmth_boost_db": 4,
        "compression": True,
    },
    speed_multiplier=1.10,  # Klaus speaks 10% faster (energetic)
)


def _name_to_seed(name: str) -> int:
    """Convert a name to a deterministic random seed."""
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16)


def generate_guest_voice(
    guest_name: str,
    gender: str = "male",
    age_range: str = "mid",
    recently_used: list[VoiceRecipe] | None = None,
) -> VoiceRecipe:
    """Generate a unique voice recipe for a podcast guest.

    Uses the guest name as seed for reproducibility -- same guest always
    gets the same voice. Ensures the voice is distinct from Klaus and
    recently used guest voices.
    """
    seed = _name_to_seed(guest_name)
    rng = random.Random(seed)

    voice_pool = MALE_VOICES if gender == "male" else FEMALE_VOICES

    # Pick 2 base voices to blend
    voice_a = rng.choice(voice_pool)
    remaining = [v for v in voice_pool if v != voice_a]
    voice_b = rng.choice(remaining)

    # Ensure we don't pick Klaus's exact voices
    if voice_a == KLAUS_VOICE_RECIPE.voice_a and voice_b == KLAUS_VOICE_RECIPE.voice_b:
        voice_b = rng.choice([v for v in remaining if v != KLAUS_VOICE_RECIPE.voice_b])

    # Random blend ratio (avoid extremes -- 0.25 to 0.75)
    blend_ratio = rng.uniform(0.25, 0.75)

    # Age-appropriate post-processing
    if age_range == "young":
        post_process = {
            "pitch_shift_semitones": rng.choice([0, 1]),
            "rasp_amount": rng.uniform(0.0, 0.02),
            "warmth_boost_db": rng.uniform(0, 2),
            "compression": True,
        }
        speed = rng.uniform(1.05, 1.12)
    elif age_range == "senior":
        post_process = {
            "pitch_shift_semitones": rng.choice([-2, -1]),
            "rasp_amount": rng.uniform(0.05, 0.12),
            "warmth_boost_db": rng.uniform(2, 4),
            "compression": True,
        }
        speed = rng.uniform(0.97, 1.05)
    else:  # mid
        post_process = {
            "pitch_shift_semitones": rng.choice([-1, 0, 1]),
            "rasp_amount": rng.uniform(0.01, 0.06),
            "warmth_boost_db": rng.uniform(1, 3),
            "compression": True,
        }
        speed = rng.uniform(1.02, 1.08)

    recipe = VoiceRecipe(
        voice_a=voice_a,
        voice_b=voice_b,
        blend_ratio=blend_ratio,
        post_process=post_process,
        speed_multiplier=speed,
    )

    # Check distance from recently used voices
    if recently_used:
        for attempt in range(5):
            if _is_too_similar(recipe, recently_used):
                # Reshuffle with different seed
                rng2 = random.Random(seed + attempt + 1)
                recipe.voice_a = rng2.choice(voice_pool)
                remaining2 = [v for v in voice_pool if v != recipe.voice_a]
                recipe.voice_b = rng2.choice(remaining2)
                recipe.blend_ratio = rng2.uniform(0.25, 0.75)
            else:
                break

    return recipe


def _is_too_similar(recipe: VoiceRecipe, others: list[VoiceRecipe]) -> bool:
    """Check if a voice recipe is too similar to recently used ones."""
    for other in others:
        # Same primary voice AND similar blend
        if recipe.voice_a == other.voice_a and abs(recipe.blend_ratio - other.blend_ratio) < 0.15:
            return True
        # Same voice pair (in any order)
        if {recipe.voice_a, recipe.voice_b} == {other.voice_a, other.voice_b}:
            return True
    return False
