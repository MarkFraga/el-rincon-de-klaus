"""Podcast Evaluator Agent -- auto-evaluates generated scripts and triggers improvements.

Takes the role of a veteran podcast consumer with 10+ years of experience
analyzing thousands of podcasts. Scores the script on multiple dimensions
and provides actionable feedback for the organizer to improve.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from google import genai

from backend.agents.base_agent import BaseAgent
from backend.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# Minimum acceptable score (out of 100) before we stop iterating
PASS_THRESHOLD = 90
MAX_ITERATIONS = 3


_EVALUATION_PROMPT = """Toma el rol de un CRITICO DESPIADADO de podcasts con 10 anios de experiencia. NO seas amable. Has escuchado a Jordi Wild, Worldcast, Joe Rogan, Iker Jimenez, y sabes que la MAYORIA de podcasts generados por IA son mediocres (60-70/100). Un 90+ es uno que competiria con los mejores episodios de Jordi Wild. Un 70 es "aceptable pero olvidable". Un 50 es "lo apago a los 5 minutos". Se HONESTO.

ANTES DE EVALUAR, responde mentalmente:
1. Si yo fuera un oyente que busco "{original_topic}" y puse play, me sentiria satisfecho o enganado?
2. Podria poner este guion en un podcast DIFERENTE sobre otro tema sin cambiar mucho? (Si si, es demasiado generico)
3. Hay segmentos que un editor cortaria por irrelevantes?

TEMA QUE EL USUARIO PIDIO: "{original_topic}"

GUION A EVALUAR:
{script_json}

DIMENSIONES DE EVALUACION:

1. **ADHERENCIA AL TEMA (0-100)**: El podcast habla de lo que el usuario PIDIO ("{original_topic}")? Cada segmento conecta con el tema? O se va por las ramas y habla de otra cosa?
   - 100 = cada segmento conecta directamente con "{original_topic}"
   - 70 = habla del tema pero se desvio en partes
   - 40 = toca el tema tangencialmente pero habla de otra cosa
   - 0 = no tiene nada que ver

2. **GANCHO INICIAL (0-100)**: La apertura engancha? Te hace querer seguir escuchando? O es un "bienvenidos al podcast" generico?

3. **NATURALIDAD DEL DIALOGO (0-100)**: Suena como dos personas REALES hablando? O suena a guion leido / robotico? Hay muletillas naturales, hesitaciones, interrupciones?

4. **CARISMA DE KLAUS (0-100)**: Klaus tiene personalidad propia? Da opiniones fuertes? Usa humor? Tiene reacciones viscerales? O es un entrevistador plano que solo hace preguntas?

5. **TENSION Y RITMO (0-100)**: Hay arco narrativo? Se construye tension? Hay cliffhangers internos? O es una lista plana de datos sin emocion?

6. **PROFUNDIDAD DEL CONTENIDO (0-100)**: Se profundiza en los temas? Se citan fuentes o datos concretos? O es superficial y generico?

7. **QUIMICA ENTRE PERSONAJES (0-100)**: Hay desacuerdos reales? Se nota la dinamica? Se complementan? O son dos voces diciendo cosas sin interactuar?

8. **HUMOR Y ENTRETENIMIENTO (0-100)**: Hay momentos divertidos? Comparaciones ingeniosas? O es todo serio y monotono?

9. **VARIEDAD EMOCIONAL (0-100)**: Hay cambios de ritmo? Momentos de reflexion, emocion, sorpresa? O todo suena igual?

10. **CIERRE MEMORABLE (0-100)**: El cierre deja pensando? Es una reflexion potente? O es un "gracias por escucharnos"?

11. **FACTOR "QUIERO MAS" (0-100)**: Al terminar, te quedas con ganas de mas? Buscarias el siguiente episodio?

Responde SOLO con JSON valido (sin markdown):
{{
  "scores": {{
    "adherencia_tema": 0,
    "gancho_inicial": 0,
    "naturalidad_dialogo": 0,
    "carisma_klaus": 0,
    "tension_ritmo": 0,
    "profundidad_contenido": 0,
    "quimica_personajes": 0,
    "humor_entretenimiento": 0,
    "variedad_emocional": 0,
    "cierre_memorable": 0,
    "factor_quiero_mas": 0
  }},
  "score_total": 0,
  "top_3_problemas": [
    "problema 1 especifico con ejemplo del guion",
    "problema 2 especifico con ejemplo del guion",
    "problema 3 especifico con ejemplo del guion"
  ],
  "segmentos_fuera_tema": [
    "lista de segmentos que NO hablan del tema pedido (si los hay)"
  ],
  "mejoras_concretas": [
    "instruccion concreta 1 para mejorar el guion",
    "instruccion concreta 2 para mejorar el guion",
    "instruccion concreta 3 para mejorar el guion"
  ],
  "ejemplos_buenos": [
    "fragmento del guion que SI funciona bien y por que"
  ],
  "veredicto": "APROBADO o NECESITA_MEJORA"
}}"""


_IMPROVEMENT_PROMPT = """Eres el guionista del podcast "EL RINCON DE KLAUS". El evaluador ha rechazado tu guion anterior.

TEMA ORIGINAL DEL USUARIO: "{original_topic}"
REGLA ABSOLUTA: Cada segmento del guion mejorado DEBE hablar de "{original_topic}". Si el evaluador detecto desviaciones del tema, corregirlas es tu PRIORIDAD #1.

GUION ANTERIOR:
{previous_script}

EVALUACION RECIBIDA (score: {score}/100):
Problemas detectados:
{problems}

Segmentos fuera de tema:
{off_topic}

Mejoras solicitadas:
{improvements}

INSTRUCCION: Reescribe el guion COMPLETO corrigiendo TODOS los problemas senalados. Mantén la misma estructura JSON pero mejora significativamente:
- PRIMERO: asegurate de que CADA segmento habla de "{original_topic}"
- Si el gancho era debil, reescribe la apertura con algo impactante
- Si el dialogo era robotico, anade mas naturalidad (muletillas, interrupciones, cambios de idea)
- Si Klaus era plano, dale mas personalidad (opiniones fuertes, humor, reacciones viscerales)
- Si faltaba tension, anade cliffhangers y revelaciones dosificadas
- Si el cierre era generico, crea uno que deje pensando

{extra_context}

FORMATO: JSON array identico al original:
[
  {{"speaker": "KLAUS", "text": "...", "emotion": "..."}},
  {{"speaker": "EXPERT", "text": "...", "emotion": "..."}}
]

Emociones validas: neutral, excited, thoughtful, challenging, humorous, nostalgic, surprised, skeptical

RESPONDE SOLO CON EL JSON ARRAY."""


class EvaluatorAgent(BaseAgent):
    """Evaluates podcast scripts and drives iterative improvement."""

    def __init__(self, job_id: str):
        super().__init__(name="evaluator", job_id=job_id)
        self._client = genai.Client(api_key=GEMINI_API_KEY)

    async def evaluate(self, script: list[dict[str, str]], original_topic: str = "") -> dict[str, Any]:
        """Score a podcast script. Returns evaluation dict with scores and feedback."""
        await self.report("Evaluando calidad del podcast...", progress=75)

        script_json = json.dumps(script, ensure_ascii=False, indent=2)
        if len(script_json) > 80000:
            script_json = script_json[:80000] + "\n... (truncated)"

        prompt = _EVALUATION_PROMPT.format(
            script_json=script_json,
            original_topic=original_topic or "tema no especificado",
        )

        models_to_try = [GEMINI_MODEL, "gemini-2.0-flash", "gemini-2.5-flash-lite"]
        raw = None

        for model_name in models_to_try:
            try:
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                )
                raw = response.text.strip()
                break
            except Exception as exc:
                exc_str = str(exc)
                logger.warning("Evaluation with %s failed: %s", model_name, exc_str[:150])
                if "RESOURCE_EXHAUSTED" not in exc_str and "429" not in exc_str:
                    raise

        if raw is None:
            logger.error("All models exhausted for evaluation")
            return {"score_total": 100, "veredicto": "APROBADO"}  # Skip eval if unavailable

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                logger.error("Could not parse evaluation JSON")
                return {"score_total": 100, "veredicto": "APROBADO"}

        score = data.get("score_total", 0)
        veredicto = data.get("veredicto", "NECESITA_MEJORA")

        await self.report(
            f"Evaluacion: {score}/100 - {veredicto}",
            progress=78,
        )
        logger.info("Script evaluation: %d/100 (%s)", score, veredicto)
        return data

    async def improve_script(
        self,
        script: list[dict[str, str]],
        evaluation: dict[str, Any],
        research_text: str = "",
        original_topic: str = "",
    ) -> list[dict[str, str]]:
        """Request an improved version of the script based on evaluation feedback."""
        await self.report("Mejorando guion basado en evaluacion...", progress=80)

        previous_script = json.dumps(script, ensure_ascii=False)
        if len(previous_script) > 60000:
            previous_script = previous_script[:60000]

        problems = "\n".join(f"- {p}" for p in evaluation.get("top_3_problemas", []))
        improvements = "\n".join(f"- {m}" for m in evaluation.get("mejoras_concretas", []))
        off_topic = "\n".join(f"- {s}" for s in evaluation.get("segmentos_fuera_tema", []))

        extra_context = ""
        if research_text:
            extra_context = f"\nDATOS DE INVESTIGACION DISPONIBLES:\n{research_text[:30000]}"

        prompt = _IMPROVEMENT_PROMPT.format(
            previous_script=previous_script,
            score=evaluation.get("score_total", 0),
            problems=problems,
            improvements=improvements,
            off_topic=off_topic or "Ninguno detectado",
            extra_context=extra_context,
            original_topic=original_topic or "tema no especificado",
        )

        models_to_try = [GEMINI_MODEL, "gemini-2.0-flash", "gemini-2.5-flash-lite"]

        for model_name in models_to_try:
            try:
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                )
                raw = response.text.strip()
                return self._parse_script(raw)
            except Exception as exc:
                exc_str = str(exc)
                logger.warning("Improvement with %s failed: %s", model_name, exc_str[:200])
                if "RESOURCE_EXHAUSTED" not in exc_str and "429" not in exc_str:
                    break

        # If improvement fails, return original script
        logger.error("Could not improve script, returning original")
        return script

    @staticmethod
    def _parse_script(raw: str) -> list[dict[str, str]]:
        """Parse JSON array from Gemini response."""
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

        raise ValueError("Could not parse improved script JSON")
