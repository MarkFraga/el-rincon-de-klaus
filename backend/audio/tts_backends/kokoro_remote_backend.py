"""Remote Kokoro TTS backend via HuggingFace Spaces API.

Calls an external Kokoro TTS microservice instead of loading
the model locally. This allows running on memory-constrained
environments (like Render free tier) while keeping full Kokoro
voice quality and mixing capabilities.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from backend.audio.tts_backends.base import TTSBackend

logger = logging.getLogger(__name__)


def _parse_rate(rate_str: str) -> float:
    """Convert rate string like '+10%' to speed float like 1.10."""
    rate_str = rate_str.strip().replace("%", "")
    try:
        return 1.0 + float(rate_str) / 100.0
    except ValueError:
        return 1.0


class KokoroRemoteTTSBackend(TTSBackend):
    """Kokoro TTS via remote HuggingFace Spaces API."""

    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=120.0)

    async def synthesize(
        self,
        text: str,
        voice: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> Path:
        """Synthesize speech via remote Kokoro API.

        Args:
            text: Text to synthesize.
            voice: Voice spec - single name ("am_onyx") or mix ("am_onyx:0.65+em_alex:0.35").
            output_path: Where to save the WAV file.
            rate: Speech rate adjustment (e.g., "+3%").
            pitch: Pitch adjustment (ignored - Kokoro uses speed only, pitch via ffmpeg).
        """
        speed = _parse_rate(rate)
        payload = {"text": text, "voice_spec": str(voice), "speed": speed}

        last_exc = None
        for attempt in range(3):
            try:
                resp = await self._client.post(
                    f"{self.api_url}/synthesize",
                    json=payload,
                )
                resp.raise_for_status()
                output_path.write_bytes(resp.content)
                return output_path
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                last_exc = exc
                if attempt < 2:
                    wait = 10 * (2 ** attempt)
                    logger.warning(
                        "Kokoro remote attempt %d failed (%s), retrying in %ds...",
                        attempt + 1, exc, wait,
                    )
                    await asyncio.sleep(wait)
            except httpx.HTTPStatusError as exc:
                logger.error("Kokoro remote HTTP error: %s", exc)
                raise

        raise ConnectionError(
            f"Kokoro remote API unreachable after 3 attempts: {last_exc}"
        )
