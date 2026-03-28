from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai

from backend.agents.base_agent import BaseAgent
from backend.config import GEMINI_API_KEY, GEMINI_MODEL

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
        guest_profile: dict[str, Any] | None = None,
    ) -> dict:
        await self.report("Compilando investigacion y preparando guion...", progress=52)

        # Convert GuestProfile dataclass to dict if needed
        if hasattr(guest_profile, "to_dict"):
            guest_profile = guest_profile.to_dict()
        elif hasattr(guest_profile, "__dataclass_fields__"):
            from dataclasses import asdict
            guest_profile = asdict(guest_profile)
        elif guest_profile is None:
            guest_profile = {
                "full_name": "Invitado Anonimo",
                "country": "Desconocido",
                "gender": "male",
                "age_range": "40-50",
                "archetype": "academic_researcher",
                "personality_traits": ["analitico", "curioso"],
                "connection_to_topic": f"Experto en {topic}",
                "dynamic": "guest_expert",
                "speaking_style": "Habla con precision y datos concretos",
            }

        guest_name = guest_profile.get("full_name", "Invitado")
        guest_country = guest_profile.get("country", "Desconocido")
        guest_voice_id = guest_profile.get("voice_id", "es-MX-JorgeNeural")
        guest_post_process = guest_profile.get("post_process", None)
        guest_role = guest_profile.get("archetype", "experto")
        dynamic = guest_profile.get("dynamic", "guest_expert")

        research_text = self._compile_research(web_result, academic_result, deep_result)

        await self.report("Generando guion del podcast con Gemini...", progress=58)

        prompt = self._build_prompt(topic, guest_profile, research_text)

        script = await self._generate_script(prompt, topic, guest_profile, research_text)

        await self.report(
            f"Guion generado: {len(script)} segmentos con {guest_name} de {guest_country}.",
            progress=68,
        )

        return {
            "script": script,
            "guest_name": guest_name,
            "guest_country": guest_country,
            "guest_voice_id": guest_voice_id,
            "guest_post_process": guest_post_process,
            "guest_role": guest_role,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _compile_research(
        web: dict[str, Any],
        academic: dict[str, Any],
        deep: dict[str, Any],
    ) -> str:
        sections: list[str] = []

        # Web sources - use ALL available
        web_sources = web.get("sources", [])
        if web_sources:
            lines = ["=== FUENTES WEB ==="]
            for s in web_sources[:30]:
                lines.append(f"\n### {s.get('title', '')}\nURL: {s.get('url', '')}\n{s.get('content', '')[:2500]}")
            sections.append("\n".join(lines))

        # Academic papers - use ALL available
        papers = academic.get("papers", [])
        if papers:
            lines = ["=== PAPERS ACADEMICOS ==="]
            for p in papers[:40]:
                lines.append(
                    f"\n### {p.get('title', '')} ({p.get('year', '?')})"
                    f"\nAutores: {p.get('authors', 'N/A')}"
                    f"\nFuente: {p.get('source', 'N/A')}"
                    f"\n{p.get('abstract', '')[:1200]}"
                )
            sections.append("\n".join(lines))

        # Deep/obscure sources - use ALL available
        deep_sources = deep.get("sources", [])
        if deep_sources:
            lines = ["=== INVESTIGACION PROFUNDA ==="]
            for s in deep_sources[:25]:
                lines.append(f"\n### {s.get('title', '')}\nURL: {s.get('url', '')}\n{s.get('content', '')[:2500]}")
            sections.append("\n".join(lines))

        return "\n\n".join(sections) if sections else "No se encontro investigacion relevante."

    # ------------------------------------------------------------------
    def _build_prompt(
        self,
        topic: str,
        guest_profile: dict[str, Any],
        research_text: str,
    ) -> str:
        full_name = guest_profile.get("full_name", "Invitado")
        country = guest_profile.get("country", "Desconocido")
        gender = guest_profile.get("gender", "male")
        connection = guest_profile.get("connection_to_topic", f"Experto en {topic}")
        speaking_style = guest_profile.get("speaking_style", "Habla con claridad")
        traits = ", ".join(guest_profile.get("personality_traits", ["analitico"]))
        dynamic = guest_profile.get("dynamic", "guest_expert")

        # Build characters block based on dynamic
        if dynamic == "guest_expert":
            characters_block = f"""PERSONAJES:
- KLAUS: Presentador veterano, voz ronca y caracter audaz. Curioso, esceptico, provoca con inteligencia.
- {full_name} (de {country}): {connection}. {speaking_style}. Personalidad: {traits}.
  Es LA autoridad en este tema. Klaus le hace preguntas dificiles y el/ella responde con datos y experiencia."""
            # Expert cites papers
            citation_rule = f"3. {full_name} cita al menos 10 datos especificos, estudios o papers de la investigacion proporcionada con nombres de autores y fechas."
            question_rule = "2. KLAUS hace al menos 8 preguntas genuinamente dificiles que el invitado debe esforzarse en responder."
            debate_style = "Es un DEBATE REAL y EXTENSO, no un monologo. Se interrumpen, se cuestionan, construyen sobre las ideas del otro."

        elif dynamic == "guest_learner":
            characters_block = f"""PERSONAJES:
- KLAUS: El EXPERTO en este tema. Tiene toda la investigacion y sabe de lo que habla. Explica con pasion y detalle.
- {full_name} (de {country}): {connection}. {speaking_style}.
  NO es experto. Hace preguntas genuinas, se sorprende, pide que le expliquen mas. Aporta perspectiva de la calle."""
            citation_rule = "3. KLAUS cita al menos 10 datos especificos, estudios o papers de la investigacion proporcionada con nombres de autores y fechas."
            question_rule = f"2. {full_name} hace al menos 8 preguntas genuinas y curiosas que KLAUS responde con profundidad."
            debate_style = "Es una CONVERSACION EDUCATIVA y EXTENSA. Klaus explica, el invitado pregunta, reacciona y aporta su perspectiva."

        elif dynamic == "debate":
            characters_block = f"""PERSONAJES:
- KLAUS: Defiende una posicion sobre el tema basada en la investigacion. Argumenta con datos.
- {full_name} (de {country}): {connection}. {speaking_style}.
  Tiene una perspectiva DIFERENTE o contraria. Debaten con respeto pero con firmeza. Ninguno cede facilmente."""
            citation_rule = "3. Ambos citan datos especificos, estudios o papers de la investigacion proporcionada (al menos 10 en total) con nombres de autores y fechas."
            question_rule = "2. Ambos se hacen preguntas dificiles mutuamente. Al menos 8 intercambios de cuestionamiento directo."
            debate_style = "Es un DEBATE REAL y EXTENSO con posiciones contrarias. Se desafian, argumentan y contraargumentan con firmeza pero respeto."

        elif dynamic == "interview":
            characters_block = f"""PERSONAJES:
- KLAUS: Entrevistador experimentado. Saca las mejores historias del invitado con preguntas certeras.
- {full_name} (de {country}): {connection}. {speaking_style}.
  Tiene una HISTORIA PERSONAL fascinante. Cuenta desde su experiencia vivida, no desde teoria."""
            citation_rule = f"3. {full_name} menciona al menos 10 datos, momentos o detalles concretos de su experiencia, conectados con la investigacion proporcionada."
            question_rule = "2. KLAUS hace al menos 8 preguntas certeras que sacan las mejores historias y reflexiones del invitado."
            debate_style = "Es una ENTREVISTA EN PROFUNDIDAD. Klaus guia la conversacion y el invitado comparte su experiencia vivida con detalle."

        elif dynamic == "storytelling":
            characters_block = f"""PERSONAJES:
- KLAUS: Escucha fascinado, hace preguntas para profundizar, anade contexto cientifico cuando es relevante.
- {full_name} (de {country}): {connection}. {speaking_style}.
  Narra su experiencia de decadas. Tiene anecdotas increibles. Es sabio/a y reflexivo/a."""
            citation_rule = "3. Se mencionan al menos 10 datos concretos, anecdotas o referencias de la investigacion proporcionada con contexto y detalles."
            question_rule = "2. KLAUS hace al menos 8 preguntas que invitan a profundizar en las historias y anecdotas del invitado."
            debate_style = "Es una NARRACION FASCINANTE. El invitado cuenta historias increibles y Klaus profundiza con preguntas y contexto."

        else:
            # Default to guest_expert
            characters_block = f"""PERSONAJES:
- KLAUS: Presentador veterano, voz ronca y caracter audaz. Curioso, esceptico, provoca con inteligencia.
- {full_name} (de {country}): {connection}. {speaking_style}. Personalidad: {traits}.
  Es LA autoridad en este tema. Klaus le hace preguntas dificiles y el/ella responde con datos y experiencia."""
            citation_rule = f"3. {full_name} cita al menos 10 datos especificos, estudios o papers de la investigacion proporcionada con nombres de autores y fechas."
            question_rule = "2. KLAUS hace al menos 8 preguntas genuinamente dificiles que el invitado debe esforzarse en responder."
            debate_style = "Es un DEBATE REAL y EXTENSO, no un monologo. Se interrumpen, se cuestionan, construyen sobre las ideas del otro."

        return f"""Eres un guionista profesional de podcasts. Escribe el guion completo para un episodio de "EL RINCON DE KLAUS".

{characters_block}

REGLAS DEL GUION (MUY IMPORTANTE - SEGUIR TODAS):
1. {debate_style}
{question_rule}
{citation_rule}
4. Incluye MULTIPLES momentos de desacuerdo o sorpresa que se resuelven con argumentos detallados.
5. Incluye al menos 2 momentos "espera, eso lo cambia todo" o revelaciones sorprendentes.
6. El dialogo debe sentirse MUY NATURAL: incluye reacciones largas ("hmm, dejame pensar...", "exacto, pero mira...", "pero espera un momento...", "a ver a ver, esto es importante", "increible, no tenia idea").
7. Klaus SIEMPRE abre con una intro larga y enganchante sobre el tema (minimo 4-5 frases) y presenta al invitado con entusiasmo.
8. Desarrolla CADA subtema en profundidad antes de pasar al siguiente. No resumas, EXPLICA con detalle.
9. Cada respuesta del invitado debe ser LARGA y detallada (minimo 3-4 frases por intervencion). No respuestas cortas.
10. Cada intervencion de Klaus tambien debe ser sustancial: reacciona, comenta, anade contexto, y luego pregunta.
11. Termina con una conclusion extensa y una pregunta abierta que deje pensando.
12. DURACION OBLIGATORIA: entre 55 y 75 intercambios. Esto es CRITICO para alcanzar 20+ minutos de audio.
13. NO uses marcadores como [PAUSA] o [MUSICA]. Solo dialogo puro.
14. Cubre TODOS los angulos del tema: historia, ciencia actual, controversias, futuro, impacto social, datos sorprendentes.

DATOS DE INVESTIGACION:
{research_text}

FORMATO DE SALIDA (JSON estricto, sin markdown):
[
  {{"speaker": "KLAUS", "text": "...", "emotion": "excited"}},
  {{"speaker": "EXPERT", "text": "...", "emotion": "thoughtful"}},
  ...
]

Emociones validas: neutral, excited, thoughtful, challenging, humorous, nostalgic, surprised, skeptical

IMPORTANTE: Devuelve SOLO el JSON array, sin texto adicional, sin ```json, sin explicaciones."""

    # ------------------------------------------------------------------
    async def _generate_script(
        self,
        prompt: str,
        topic: str,
        guest_profile: dict[str, Any],
        research_text: str,
    ) -> list[dict[str, str]]:
        """Call Gemini and parse the script JSON, with retries and model fallback."""
        import asyncio

        # Try primary model first, then fall back to alternatives on quota errors
        models_to_try = [
            GEMINI_MODEL,
            "gemini-2.0-flash",
            "gemini-2.5-flash-lite",
        ]

        last_exc = None
        for model_idx, model_name in enumerate(models_to_try):
            for attempt in range(2):
                try:
                    current_prompt = prompt
                    if attempt > 0 or model_idx > 0:
                        wait_secs = 5 if model_idx > 0 else 30
                        await self.report(
                            f"Intentando modelo {model_name} (intento {attempt+1})...",
                            progress=60 + model_idx * 2,
                        )
                        if attempt > 0:
                            await asyncio.sleep(wait_secs)
                        current_prompt = self._build_strict_retry_prompt(
                            topic, guest_profile, research_text
                        )

                    response = await asyncio.to_thread(
                        self._client.models.generate_content,
                        model=model_name,
                        contents=current_prompt,
                    )
                    raw = response.text.strip()
                    return self._parse_script(raw)

                except Exception as exc:
                    last_exc = exc
                    exc_str = str(exc)
                    logger.warning(
                        "Script generation with %s attempt %d failed: %s",
                        model_name, attempt + 1, exc_str[:200],
                    )
                    # If quota exceeded, skip remaining attempts for this model
                    if "RESOURCE_EXHAUSTED" in exc_str or "429" in exc_str:
                        logger.info(
                            "Quota exhausted for %s, trying next model...", model_name
                        )
                        break

        raise RuntimeError(
            f"No se pudo generar el guion tras probar {len(models_to_try)} modelos: {last_exc}"
        ) from last_exc

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

        raise ValueError("No se pudo parsear el JSON del guion generado.")

    # ------------------------------------------------------------------
    def _build_strict_retry_prompt(
        self,
        topic: str,
        guest_profile: dict[str, Any],
        research_text: str,
    ) -> str:
        guest_name = guest_profile.get("full_name", "Invitado")
        guest_country = guest_profile.get("country", "Desconocido")
        dynamic = guest_profile.get("dynamic", "guest_expert")

        dynamic_desc = {
            "guest_expert": f"{guest_name} es el experto, Klaus pregunta",
            "guest_learner": f"KLAUS es el experto, {guest_name} pregunta y aprende",
            "debate": f"Klaus y {guest_name} debaten con posiciones contrarias",
            "interview": f"Klaus entrevista a {guest_name} sobre su experiencia",
            "storytelling": f"{guest_name} narra historias fascinantes, Klaus profundiza",
        }.get(dynamic, f"{guest_name} es el experto, Klaus pregunta")

        return f"""INSTRUCCION ESTRICTA: Genera UNICAMENTE un JSON array valido. Sin texto antes ni despues.

Genera un guion de podcast LARGO entre KLAUS (presentador) y {guest_name} (de {guest_country}).
Dinamica: {dynamic_desc}.
MINIMO 55-75 intercambios. Cada intervencion debe ser LARGA (3-5 frases minimo). Debate real con desacuerdos, datos especificos y reacciones naturales. Cubre el tema en profundidad.

Investigacion disponible:
{research_text[:60000]}

FORMATO OBLIGATORIO (solo esto, nada mas):
[
  {{"speaker": "KLAUS", "text": "texto aqui", "emotion": "excited"}},
  {{"speaker": "EXPERT", "text": "texto aqui", "emotion": "thoughtful"}}
]

Emociones validas: neutral, excited, thoughtful, challenging, humorous, nostalgic, surprised, skeptical
RESPONDE SOLO CON EL JSON ARRAY."""
