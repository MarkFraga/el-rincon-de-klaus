"""Topic Analyzer -- uses Gemini to decompose vague/broad topics into smart search queries.

Instead of searching for the raw user input, this module first understands
the *concepts* behind the topic and generates optimized queries for each
agent type (web, academic, deep/forums).

Example:
    Input:  "alienigenas y el paso del tiempo"
    Output: web_queries  = ["paradoja de Fermi explicacion", "dilatacion temporal vida extraterrestre", ...]
            academic_queries = ["astrobiology time perception", "Fermi paradox Drake equation", ...]
            deep_queries = ["alien civilizations time scales site:reddit.com", ...]
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from google import genai

from backend.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)


@dataclass
class TopicAnalysis:
    """Structured output from the topic analyzer."""

    original_topic: str = ""
    topic_summary: str = ""
    topic_type: str = "mixto"  # cientifico, especulativo, filosofico, mixto
    user_intent: str = ""
    main_concepts: list[str] = field(default_factory=list)
    related_topics: list[str] = field(default_factory=list)
    web_queries: list[str] = field(default_factory=list)
    academic_queries: list[str] = field(default_factory=list)
    deep_queries: list[str] = field(default_factory=list)


_ANALYSIS_PROMPT = """Eres un analista de temas BRILLANTE para un podcast. Tu trabajo es tomar CUALQUIER tema (vago, especifico, especulativo, cientifico, filosofico, conspirativo, etc.) y descomponerlo en queries de busqueda que REALMENTE encuentren informacion.

TEMA DEL USUARIO: "{topic}"

PASO 1 - ENTIENDE LA INTENCION:
El usuario puede expresarse de forma vaga, larga o poetica. Tu trabajo es entender QUE QUIERE ESCUCHAR en el podcast. Ejemplo:
- "personas de otro tiempo viviendo entre nosotros, universo espejo" = quiere hablar de viajeros del tiempo, multiverso, mirror universe theory, anomalias temporales
- "alienigenas y el paso del tiempo" = Fermi paradox, dilatacion temporal, astrobiologia
- "por que soñamos cosas que luego pasan" = premoniciones, deja vu, neurociencia del sueno predictivo

PASO 2 - CLASIFICA EL TIPO DE TEMA:
- CIENTIFICO: tiene base en investigacion real (genera queries academicas fuertes)
- ESPECULATIVO: teorias no probadas, conspiraciones, misterios (genera queries en foros, Reddit, cultura pop, la CIENCIA REAL detras de la especulacion)
- FILOSOFICO: preguntas existenciales (genera queries de thought experiments, filosofia, debates)
- MIXTO: combina varios (genera queries de TODOS los tipos)

PASO 3 - GENERA QUERIES INTELIGENTES:
REGLAS CRITICAS:
- NUNCA repitas las palabras exactas del usuario. DESCOMPONE en conceptos buscables.
- Cada query: 3-6 palabras, un ANGULO DIFERENTE del tema
- Mezcla espanol e ingles
- Para temas especulativos: busca la CIENCIA REAL detras (fisica teorica, neurociencia, etc.) + las TEORIAS POPULARES (Reddit, foros, libros, peliculas)
- Para temas vagos: genera queries MAS AMPLIAS que seguro encuentren algo, no queries ultra-especificas que no den resultados
- Si el tema menciona una teoria especifica (ej: "universo espejo"), busca ESA TEORIA por su nombre cientifico Y popular

EJEMPLO 1 (especulativo):
Tema: "personas de otro tiempo viviendo entre nosotros, universo espejo"
web_queries: ["viajeros del tiempo teoria", "mirror universe physics theory", "universo espejo materia oscura", "time travel paradoxes explained", "anomalias temporales casos reales", "John Titor viajero tiempo", "multiverso teorias fisicas", "personas que afirman venir del futuro", "Mandela effect universos paralelos", "peliculas viajes tiempo mejores", "crononautas historia concepto", "everett many worlds interpretation"]
academic_queries: ["mirror matter dark matter theory", "time travel physics theoretical models", "many worlds interpretation quantum mechanics", "temporal paradoxes philosophical analysis", "parallel universes multiverse evidence"]
deep_queries: ["time travelers site:reddit.com", "mirror universe theory site:reddit.com", "viajeros del tiempo foro experiencias", "parallel universe evidence debate", "John Titor predictions site:reddit.com", "mandela effect explicacion foro", "universo espejo site:researchgate.net", "time travel physics filetype:pdf", "crononautas conspiracion debate", "multiverse evidence surprising findings", "quantum mechanics parallel worlds", "temporal anomalies unexplained cases"]

EJEMPLO 2 (cientifico):
Tema: "CRISPR"
web_queries: ["CRISPR explicacion simple", "gene editing latest breakthroughs 2025", "CRISPR bebes disenados controversia", "Jennifer Doudna Nobel CRISPR", "enfermedades curadas con CRISPR", "CRISPR riesgos peligros etica", "edicion genetica futuro predicciones", "CRISPR vs otros metodos edicion", "CRISPR agricultura alimentos", "terapia genica pacientes reales", "biohacking CRISPR casero", "CRISPR cancer tratamiento resultados"]

Responde SOLO con JSON valido (sin markdown, sin texto extra):
{{
  "topic_summary": "resumen claro de 1-2 frases: DE QUE QUIERE HABLAR el usuario y que angulos cubrir",
  "topic_type": "cientifico | especulativo | filosofico | mixto",
  "main_concepts": ["concepto1", "concepto2", "concepto3", "concepto4"],
  "related_topics": ["tema_relacionado1", "tema_relacionado2", "tema_relacionado3", "tema_relacionado4", "tema_relacionado5"],
  "user_intent": "una frase que capture la INTENCION del usuario: que experiencia quiere tener al escuchar el podcast",
  "web_queries": [
    "12 queries variadas, cortas, en espanol e ingles, que SEGURO encuentren resultados"
  ],
  "academic_queries": [
    "5 queries academicas en ingles (si el tema es especulativo, busca la ciencia detras: fisica teorica, neurociencia, filosofia academica, etc.)"
  ],
  "deep_queries": [
    "12 queries para foros, Reddit, papers oscuros, tesis (para temas especulativos: incluir site:reddit.com, foros de misterio, conspiracion, filosofia)"
  ]
}}"""


async def analyze_topic(topic: str) -> TopicAnalysis:
    """Use Gemini to decompose a topic into smart search queries.

    Falls back to basic decomposition if Gemini is unavailable.
    """
    try:
        return await _analyze_with_gemini(topic)
    except Exception as exc:
        logger.warning("Gemini topic analysis failed, using fallback: %s", exc)
        return _fallback_analysis(topic)


async def _analyze_with_gemini(topic: str) -> TopicAnalysis:
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = _ANALYSIS_PROMPT.format(topic=topic)

    models_to_try = [GEMINI_MODEL, "gemini-2.0-flash", "gemini-2.5-flash-lite"]
    raw = None

    for model_name in models_to_try:
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
            )
            raw = response.text.strip()
            break
        except Exception as exc:
            exc_str = str(exc)
            logger.warning("Topic analysis with %s failed: %s", model_name, exc_str[:150])
            if "RESOURCE_EXHAUSTED" not in exc_str and "429" not in exc_str:
                raise

    if raw is None:
        raise RuntimeError("All Gemini models exhausted for topic analysis")

    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError("Could not parse topic analysis JSON")

    return TopicAnalysis(
        original_topic=topic,
        topic_summary=data.get("topic_summary", topic),
        topic_type=data.get("topic_type", "mixto"),
        user_intent=data.get("user_intent", topic),
        main_concepts=data.get("main_concepts", [topic]),
        related_topics=data.get("related_topics", []),
        web_queries=data.get("web_queries", [topic]),
        academic_queries=data.get("academic_queries", [topic]),
        deep_queries=data.get("deep_queries", [topic]),
    )


def _fallback_analysis(topic: str) -> TopicAnalysis:
    """Basic decomposition when Gemini is unavailable.

    Splits compound topics and generates simple query variations.
    """
    # Split by common conjunctions
    parts = re.split(r'\s+y\s+|\s+and\s+|\s*,\s*', topic, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        parts = [topic]

    web_queries = []
    academic_queries = []
    deep_queries = []

    suffixes_web = [
        "", "explicacion detallada", "datos curiosos", "historia origenes",
        "descubrimientos recientes 2024 2025", "controversia debate",
        "expertos opinion", "estadisticas datos", "futuro predicciones",
        "como funciona", "impacto sociedad", "casos reales ejemplos",
    ]
    suffixes_academic = [
        "", "review", "recent advances", "meta-analysis", "experimental results",
    ]
    suffixes_deep = [
        "site:reddit.com", "foro discusion", "site:researchgate.net",
        "filetype:pdf research", "site:academia.edu", "preprint 2024 2025",
        "controversial findings", "site:ncbi.nlm.nih.gov",
        "tesis doctoral PhD", "meta-analysis systematic review",
        "unexpected results surprising", "lesser known research",
    ]

    for part in parts:
        for suffix in suffixes_web:
            q = f"{part} {suffix}".strip()
            if q not in web_queries:
                web_queries.append(q)
        for suffix in suffixes_academic:
            q = f"{part} {suffix}".strip()
            if q not in academic_queries:
                academic_queries.append(q)
        for suffix in suffixes_deep:
            q = f'"{part}" {suffix}'.strip()
            if q not in deep_queries:
                deep_queries.append(q)

    # Also add the full topic as queries
    if len(parts) > 1:
        web_queries.insert(0, topic)
        academic_queries.insert(0, topic)
        deep_queries.insert(0, f'"{topic}"')

    return TopicAnalysis(
        original_topic=topic,
        topic_summary=topic,
        main_concepts=parts,
        related_topics=[],
        web_queries=web_queries[:12],
        academic_queries=academic_queries[:5],
        deep_queries=deep_queries[:12],
    )
