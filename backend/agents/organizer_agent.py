from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from google import genai

from backend.agents.base_agent import BaseAgent
from backend.config import GEMINI_API_KEY, GEMINI_MODEL, EXPERT_VOICES

logger = logging.getLogger(__name__)


class OrganizerAgent(BaseAgent):
    """Agent 2 -- synthesises all research and generates the podcast script via Gemini."""

    def __init__(self, job_id: str):
        super().__init__(name="organizer", job_id=job_id)
        self._client = genai.Client(api_key=GEMINI_API_KEY)

    # ------------------------------------------------------------------
    async def run(  # type: ignore[override]
        self,
        topic: str,
        web_result: dict[str, Any],
        academic_result: dict[str, Any],
        deep_result: dict[str, Any],
    ) -> dict:
        await self.report("Seleccionando experto y compilando investigación...", progress=52)

        expert = self._pick_expert(topic)
        expert_name = expert["name"]
        expert_country = expert["country"]
        expert_voice_id = expert["voice_id"]

        research_text = self._compile_research(web_result, academic_result, deep_result)

        await self.report("Generando guión del podcast con Gemini...", progress=58)

        prompt = self._build_prompt(topic, expert_name, expert_country, research_text)

        script = await self._generate_script(prompt, topic, expert_name, expert_country, research_text)

        await self.report(
            f"Guión generado: {len(script)} segmentos con {expert_name} de {expert_country}.",
            progress=68,
        )

        return {
            "script": script,
            "expert_name": expert_name,
            "expert_country": expert_country,
            "expert_voice_id": expert_voice_id,
        }

    # ------------------------------------------------------------------
    def _pick_expert(self, topic: str) -> dict[str, str]:
        """Deterministically pick an expert based on topic hash."""
        h = int(hashlib.md5(topic.encode()).hexdigest(), 16)
        return EXPERT_VOICES[h % len(EXPERT_VOICES)]

    # ------------------------------------------------------------------
    @staticmethod
    def _compile_research(
        web: dict[str, Any],
        academic: dict[str, Any],
        deep: dict[str, Any],
    ) -> str:
        sections: list[str] = []

        # Web sources
        web_sources = web.get("sources", [])
        if web_sources:
            lines = ["=== FUENTES WEB ==="]
            for s in web_sources[:12]:
                lines.append(f"\n### {s.get('title', '')}\nURL: {s.get('url', '')}\n{s.get('content', '')[:1500]}")
            sections.append("\n".join(lines))

        # Academic papers
        papers = academic.get("papers", [])
        if papers:
            lines = ["=== PAPERS ACADÉMICOS ==="]
            for p in papers[:12]:
                lines.append(
                    f"\n### {p.get('title', '')} ({p.get('year', '?')})"
                    f"\nAutores: {p.get('authors', 'N/A')}"
                    f"\nFuente: {p.get('source', 'N/A')}"
                    f"\n{p.get('abstract', '')[:1000]}"
                )
            sections.append("\n".join(lines))

        # Deep/obscure sources
        deep_sources = deep.get("sources", [])
        if deep_sources:
            lines = ["=== INVESTIGACIÓN PROFUNDA ==="]
            for s in deep_sources[:10]:
                lines.append(f"\n### {s.get('title', '')}\nURL: {s.get('url', '')}\n{s.get('content', '')[:1500]}")
            sections.append("\n".join(lines))

        return "\n\n".join(sections) if sections else "No se encontró investigación relevante."

    # ------------------------------------------------------------------
    def _build_prompt(
        self,
        topic: str,
        expert_name: str,
        expert_country: str,
        research_text: str,
    ) -> str:
        return f"""Eres un guionista profesional de podcasts. Escribe el guión completo para un episodio de "EL RINCÓN DE KLAUS".

PERSONAJES:
- KLAUS: Presentador del podcast. Carismático, curioso, a veces escéptico. Hace preguntas difíciles y provoca al invitado. Habla con confianza.
- {expert_name} (de {expert_country}): Experto/a mundial en {topic}. Apasionado/a, usa datos concretos, cita papers específicos. A veces discrepa con Klaus.

REGLAS DEL GUIÓN:
1. Es un DEBATE REAL, no un monólogo. Se interrumpen, se cuestionan, construyen sobre las ideas del otro.
2. KLAUS hace al menos 4 preguntas genuinamente difíciles que el experto debe esforzarse en responder.
3. El experto cita al menos 5 datos específicos o papers de la investigación proporcionada.
4. Incluye momentos de desacuerdo que se resuelven con argumentos.
5. Incluye al menos un momento "espera, eso lo cambia todo" o similar.
6. El diálogo debe sentirse NATURAL: incluye reacciones ("hmm", "exacto", "pero espera...", "a ver a ver", "increíble").
7. Klaus SIEMPRE abre con una intro enganchante sobre el tema y presenta al invitado.
8. Termina con una conclusión sorprendente o una pregunta abierta que deje pensando.
9. Duración: 25-35 intercambios (para ~15 minutos de audio).
10. NO uses marcadores como [PAUSA] o [MÚSICA]. Solo diálogo puro.

DATOS DE INVESTIGACIÓN:
{research_text}

FORMATO DE SALIDA (JSON estricto, sin markdown):
[
  {{"speaker": "KLAUS", "text": "...", "emotion": "excited"}},
  {{"speaker": "EXPERT", "text": "...", "emotion": "thoughtful"}},
  ...
]

Emociones válidas: neutral, excited, thoughtful, challenging

IMPORTANTE: Devuelve SOLO el JSON array, sin texto adicional, sin ```json, sin explicaciones."""

    # ------------------------------------------------------------------
    async def _generate_script(
        self,
        prompt: str,
        topic: str,
        expert_name: str,
        expert_country: str,
        research_text: str,
    ) -> list[dict[str, str]]:
        """Call Gemini and parse the script JSON, with one retry on failure."""
        import asyncio

        for attempt in range(3):
            try:
                if attempt > 0:
                    wait_secs = 30 * attempt
                    await self.report(f"Reintentando en {wait_secs}s (intento {attempt+1}/3)...", progress=63)
                    await asyncio.sleep(wait_secs)
                    prompt = self._build_strict_retry_prompt(topic, expert_name, expert_country, research_text)

                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=GEMINI_MODEL,
                    contents=prompt,
                )
                raw = response.text.strip()
                return self._parse_script(raw)

            except Exception as exc:
                logger.warning("Script generation attempt %d failed: %s", attempt + 1, exc)
                if attempt == 2:
                    raise RuntimeError(f"No se pudo generar el guión tras 3 intentos: {exc}") from exc

        # Unreachable, but satisfies the type checker
        raise RuntimeError("No se pudo generar el guión.")

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_script(raw: str) -> list[dict[str, str]]:
        """Parse JSON array from Gemini response, with regex fallback."""
        # Try direct parse first
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [
                    {
                        "speaker": seg.get("speaker", "KLAUS"),
                        "text": seg.get("text", ""),
                        "emotion": seg.get("emotion", "neutral"),
                    }
                    for seg in data
                ]
        except json.JSONDecodeError:
            pass

        # Regex fallback: find outermost [ ... ]
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return [
                        {
                            "speaker": seg.get("speaker", "KLAUS"),
                            "text": seg.get("text", ""),
                            "emotion": seg.get("emotion", "neutral"),
                        }
                        for seg in data
                    ]
            except json.JSONDecodeError:
                pass

        raise ValueError("No se pudo parsear el JSON del guión generado.")

    # ------------------------------------------------------------------
    def _build_strict_retry_prompt(
        self,
        topic: str,
        expert_name: str,
        expert_country: str,
        research_text: str,
    ) -> str:
        return f"""INSTRUCCIÓN ESTRICTA: Genera ÚNICAMENTE un JSON array válido. Sin texto antes ni después.

Genera un guión de podcast entre KLAUS (presentador) y {expert_name} (de {expert_country}, experto en {topic}).
25-35 intercambios. Debate real con desacuerdos, datos específicos y reacciones naturales.

Investigación disponible:
{research_text[:8000]}

FORMATO OBLIGATORIO (solo esto, nada más):
[
  {{"speaker": "KLAUS", "text": "texto aquí", "emotion": "excited"}},
  {{"speaker": "EXPERT", "text": "texto aquí", "emotion": "thoughtful"}}
]

Emociones válidas: neutral, excited, thoughtful, challenging
RESPONDE SOLO CON EL JSON ARRAY."""
