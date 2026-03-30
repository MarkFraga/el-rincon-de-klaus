"""Kokoro TTS microservice for HuggingFace Spaces.

Provides a simple HTTP API for text-to-speech synthesis using Kokoro's
82M parameter model with voice blending support. Designed to be called
from the main Klaus podcast app running on Render.
"""

import asyncio
import io
import logging
from typing import Optional

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from huggingface_hub import hf_hub_download
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Klaus TTS Service")

_REPO_ID = "hexgrad/Kokoro-82M"

# Lazy-loaded pipeline and voice cache
_pipeline = None
_load_lock = asyncio.Lock()
_voice_cache: dict[str, torch.Tensor] = {}


async def _get_pipeline():
    """Lazy-load the Kokoro pipeline on first request."""
    global _pipeline
    async with _load_lock:
        if _pipeline is not None:
            return _pipeline
        from kokoro import KPipeline
        logger.info("Loading Kokoro TTS model...")
        _pipeline = KPipeline(lang_code="es", repo_id=_REPO_ID)
        logger.info("Kokoro TTS model loaded.")
        return _pipeline


def _load_voice(voice_name: str) -> torch.Tensor:
    """Load a voice embedding tensor, with caching."""
    if voice_name in _voice_cache:
        return _voice_cache[voice_name]
    path = hf_hub_download(_REPO_ID, f"voices/{voice_name}.pt")
    tensor = torch.load(path, weights_only=True)
    _voice_cache[voice_name] = tensor
    logger.debug("Loaded voice: %s (%s)", voice_name, tensor.shape)
    return tensor


def _create_mixed_voice(voice_a: str, voice_b: str, blend_ratio: float) -> torch.Tensor:
    """Blend two voice embeddings."""
    t_a = _load_voice(voice_a)
    t_b = _load_voice(voice_b)
    return t_a * (1 - blend_ratio) + t_b * blend_ratio


def _parse_voice_spec(spec: str) -> torch.Tensor:
    """Parse voice specification into a tensor.

    Supports:
      - Single voice: "am_onyx"
      - Mix spec: "am_onyx:0.65+em_alex:0.35"
    """
    if "+" in spec and ":" in spec:
        parts = spec.split("+")
        if len(parts) == 2:
            name_a, ratio_a = parts[0].rsplit(":", 1)
            name_b, ratio_b = parts[1].rsplit(":", 1)
            try:
                r_a = float(ratio_a)
                r_b = float(ratio_b)
            except ValueError:
                r_a, r_b = 0.5, 0.5
            total = r_a + r_b
            return _create_mixed_voice(name_a.strip(), name_b.strip(), r_b / total)
    return _load_voice(spec.strip())


class SynthesizeRequest(BaseModel):
    text: str
    voice_spec: str = "em_alex"
    speed: float = 1.0


@app.post("/synthesize")
async def synthesize(req: SynthesizeRequest):
    """Synthesize speech and return WAV audio bytes."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    pipeline = await _get_pipeline()
    voice_tensor = _parse_voice_spec(req.voice_spec)

    def _generate() -> bytes:
        audio_chunks = []
        for _, _, chunk in pipeline(req.text, voice=voice_tensor, speed=req.speed):
            if chunk is not None:
                audio_chunks.append(chunk)

        if not audio_chunks:
            raise ValueError(f"Kokoro produced no audio for: {req.text[:50]}...")

        full_audio = np.concatenate(audio_chunks)
        buf = io.BytesIO()
        sf.write(buf, full_audio, 24000, format="WAV")
        buf.seek(0)
        return buf.read()

    wav_bytes = await asyncio.to_thread(_generate)
    return Response(content=wav_bytes, media_type="audio/wav")


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": _pipeline is not None}
