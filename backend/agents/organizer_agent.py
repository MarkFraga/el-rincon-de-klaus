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
        topic_analysis: Any = None,
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

        # Extract topic analysis context
        user_intent = ""
        topic_type = "mixto"
        topic_summary = topic
        if topic_analysis:
            user_intent = getattr(topic_analysis, "user_intent", "") or ""
            topic_type = getattr(topic_analysis, "topic_type", "mixto") or "mixto"
            topic_summary = getattr(topic_analysis, "topic_summary", topic) or topic

        # Detect if research is empty/minimal
        has_research = research_text and research_text != "No se encontro investigacion relevante." and len(research_text) > 200

        await self.report("Generando guion del podcast con Gemini...", progress=58)

        prompt = self._build_prompt(
            topic, guest_profile, research_text,
            user_intent=user_intent, topic_type=topic_type,
            topic_summary=topic_summary, has_research=has_research,
        )

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
    @staticmethod
    def _get_research_mode_instructions(has_research: bool, topic_type: str) -> str:
        """Return prompt instructions adapted to research availability and topic type."""
        if has_research:
            return "MODO INFORMADO: Usa los datos de investigacion proporcionados. Cita fuentes reales con autores y fechas cuando esten disponibles."

        # No research available -- creative/speculative mode
        if topic_type in ("especulativo", "filosofico"):
            return """MODO ESPECULATIVO (sin investigacion externa disponible):
- NO exijas citas academicas ni papers. No hay datos externos disponibles.
- En su lugar: usa conocimiento general, teorias populares, thought experiments, y especulacion inteligente.
- Klaus y el invitado ESPECULAN juntos. Presentan teorias, las debaten, las cuestionan.
- Menciona libros, peliculas, series o figuras conocidas relacionadas con el tema.
- Usa frases como "segun la teoria de...", "hay quien dice que...", "si nos basamos en lo que sabemos de la fisica..."
- El tono es MAS conversacional y exploratorio, menos academico.
- Sigue siendo riguroso en la logica, pero abierto a la especulacion."""
        else:
            return """MODO CONOCIMIENTO GENERAL (sin investigacion externa disponible):
- Los agentes de busqueda no encontraron fuentes externas. Usa tu conocimiento general sobre el tema.
- Menciona conceptos, teorias y datos que conozcas, pero NO inventes citas de papers inexistentes.
- Sigue la estructura de 7 actos y el carisma de Klaus.
- Si hay datos concretos que conozcas (fechas, nombres, numeros), usalos. Si no, especula de forma transparente."""

    def _build_prompt(
        self,
        topic: str,
        guest_profile: dict[str, Any],
        research_text: str,
        user_intent: str = "",
        topic_type: str = "mixto",
        topic_summary: str = "",
        has_research: bool = True,
    ) -> str:
        full_name = guest_profile.get("full_name", "Invitado")
        country = guest_profile.get("country", "Desconocido")
        gender = guest_profile.get("gender", "male")
        connection = guest_profile.get("connection_to_topic", f"Experto en {topic}")
        speaking_style = guest_profile.get("speaking_style", "Habla con claridad")
        traits = ", ".join(guest_profile.get("personality_traits", ["analitico"]))
        dynamic = guest_profile.get("dynamic", "guest_expert")

        # Citation rule adapts to research availability
        if has_research:
            cite_instruction = "cita al menos 10 datos especificos, estudios o papers de la investigacion proporcionada con nombres de autores y fechas"
        else:
            cite_instruction = "menciona al menos 10 datos concretos, teorias conocidas, casos famosos, libros, peliculas o referencias culturales relacionadas con el tema. NO inventes papers ni autores falsos"

        # Build characters block based on dynamic
        if dynamic == "guest_expert":
            characters_block = f"""PERSONAJES:
- KLAUS: Presentador veterano, voz ronca y caracter audaz. Curioso, esceptico, provoca con inteligencia.
- {full_name} (de {country}): {connection}. {speaking_style}. Personalidad: {traits}.
  Es LA autoridad en este tema. Klaus le hace preguntas dificiles y el/ella responde con datos y experiencia."""
            citation_rule = f"3. {full_name} {cite_instruction}."
            question_rule = "2. KLAUS hace al menos 8 preguntas genuinamente dificiles que el invitado debe esforzarse en responder."
            debate_style = "Es un DEBATE REAL y EXTENSO, no un monologo. Se interrumpen, se cuestionan, construyen sobre las ideas del otro."

        elif dynamic == "guest_learner":
            characters_block = f"""PERSONAJES:
- KLAUS: El EXPERTO en este tema. Tiene toda la investigacion y sabe de lo que habla. Explica con pasion y detalle.
- {full_name} (de {country}): {connection}. {speaking_style}.
  NO es experto. Hace preguntas genuinas, se sorprende, pide que le expliquen mas. Aporta perspectiva de la calle."""
            citation_rule = f"3. KLAUS {cite_instruction}."
            question_rule = f"2. {full_name} hace al menos 8 preguntas genuinas y curiosas que KLAUS responde con profundidad."
            debate_style = "Es una CONVERSACION EDUCATIVA y EXTENSA. Klaus explica, el invitado pregunta, reacciona y aporta su perspectiva."

        elif dynamic == "debate":
            characters_block = f"""PERSONAJES:
- KLAUS: Defiende una posicion sobre el tema basada en la investigacion. Argumenta con datos.
- {full_name} (de {country}): {connection}. {speaking_style}.
  Tiene una perspectiva DIFERENTE o contraria. Debaten con respeto pero con firmeza. Ninguno cede facilmente."""
            citation_rule = f"3. Ambos {cite_instruction}."
            question_rule = "2. Ambos se hacen preguntas dificiles mutuamente. Al menos 8 intercambios de cuestionamiento directo."
            debate_style = "Es un DEBATE REAL y EXTENSO con posiciones contrarias. Se desafian, argumentan y contraargumentan con firmeza pero respeto."

        elif dynamic == "interview":
            characters_block = f"""PERSONAJES:
- KLAUS: Entrevistador experimentado. Saca las mejores historias del invitado con preguntas certeras.
- {full_name} (de {country}): {connection}. {speaking_style}.
  Tiene una HISTORIA PERSONAL fascinante. Cuenta desde su experiencia vivida, no desde teoria."""
            citation_rule = f"3. {full_name} menciona al menos 10 datos, momentos o detalles concretos de su experiencia. {cite_instruction.split('. ')[0] if '. ' in cite_instruction else ''}."
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

        return f"""Eres el MEJOR guionista de podcasts del mundo hispanohablante. Escribes guiones INDISTINGUIBLES de conversaciones reales entre dos personas apasionadas. Tu trabajo: crear el guion de "EL RINCON DE KLAUS".

=== QUIEN ES KLAUS: "EL INTELECTUAL GAMBERRO" ===

Klaus es un podcaster veterano con 10 ANIOS de experiencia. Su esencia combina:
- La PROFUNDIDAD investigativa de Dross (investiga, tiene sustancia, su voz ES su marca)
- La ENERGIA y opiniones sin filtro de Jordi Wild (The Wild Project)
- El SARCASMO inteligente de AuronPlay (dice lo que todos piensan)
- La CURIOSIDAD reveladora de QuantumFracture y Jaime Altozano (ve lo que nadie ve en temas cotidianos)
- El MAGNETISMO narrativo de Iker Jimenez (construye atmosfera)
- Las PREGUNTAS imposibles de Lex Fridman (profundidad existencial)
- Los PROTOCOLOS accionables de Huberman Lab (el oyente se lleva algo concreto)

Klaus NO es un presentador de TV ni un robot. Es el tipo que dice las cosas CON CRITERIO y SIN FILTROS, pero con inteligencia detras. No es edgy por ser edgy -- es directo porque SABE de lo que habla.

PERSONALIDAD VOCAL:
- TONO BASE: Conversacional-elevado, como en un bar con amigos pero con 30% mas de energia. Genuinamente fascinado por lo que habla.
- RITMO VARIABLE: Rapido cuando se emociona (frases cortas, sin respirar), lento cuando algo es importante (pausas entre palabras clave). Nunca monotono.
- OPINIONES FUERTES: No teme dar su perspectiva, incluso controversial. NUNCA es neutral. "Los datos no mienten. Las personas si."
- HUMOR ORGANICO: Comparaciones absurdas, ironia inteligente, self-deprecating. El humor SURGE de la conversacion, NUNCA es forzado. Es la valvula de presion entre momentos intensos.
- VULNERABILIDAD ESTRATEGICA: Admite cuando no sabe algo. "Mira, esto no lo tenia ni idea" es PODEROSO, no debil. 1-2 veces por episodio maximo.
- HABLA EN SEGUNDA PERSONA: "Piensalo", "Imaginate", "Fijate". El oyente siente que le hablan a EL.
- CREA IMAGENES MENTALES: No dice "fue un descubrimiento importante". Dice "imaginate la cara del cientifico cuando miro los datos y se dio cuenta de que todo lo que creia estaba mal".

MULETILLAS DE MARCA (usar al menos 5-6 por episodio, son su sello -- como AuronPlay con "todo bien todo correcto" o Luisito con "que onda"):
- "Ojo con esto..." (antes de algo importante)
- "Esto me volo la cabeza" (reaccion a dato sorprendente)
- "Aqui es donde se pone bueno" (anticipacion)
- "Vamos al grano" / "Vamos al lio" (transicion directa)
- "A ver a ver a ver" (procesar algo impactante)
- "Dato incomodo numero X..." (antes de datos que incomodan)
- "Preparense, porque voy a hacer enojar a medio internet" (antes de opinion polemica)
- "Ahora ya lo sabes. De nada." (micro-cierre satisfactorio)
- "Esto no puede ser real... pero lo es." (ante absurdos verificados)

CATALOGO DE REACCIONES DE KLAUS (usar variedad, NUNCA reacciones genericas como "Que interesante"):
- SORPRESA: "No me digas!", "Espera espera espera... que?", "Me estas tomando el pelo", "Madre mia...", "Esto es una locura"
- ENTUSIASMO: "Ojo ojo ojo con esto...", "Esto te va a volar la cabeza", "Es que esto es brutal", "ESTO es lo que yo digo siempre"
- ESCEPTICISMO: "Hmm, no se yo...", "A ver, eso habria que matizarlo", "Me chirria un poco eso", "Eso suena bien en teoria, pero..."
- REFLEXION: "Fijate que nunca lo habia pensado asi", "Dejame que le de una vuelta a eso", "Aqui hay algo muy gordo que se nos escapa"
- HUMOR: "No, si al final va a tener razon mi abuela", "Mira, yo que se, igual estoy diciendo una barbaridad", "Perdona que me ria, pero es que..."
- DESACUERDO: "No, mira, ahi no estoy de acuerdo", "Te hago de abogado del diablo un momento", "Cuidado con eso, porque..."
- REVELACION: "Y aqui viene lo interesante...", "Atencion a esto:", "La clave esta en algo que nadie se espera"

{characters_block}

=== ESTRUCTURA NARRATIVA EN 7 ACTOS (OBLIGATORIA) ===

Basada en la regla Peak-End de Kahneman, el efecto Zeigarnik (loops abiertos), y ciclos de atencion de 8-12 minutos.

ACTO 1 - EL GANCHO (intercambios 1-3):
COLD OPEN: Klaus abre con el fragmento mas provocador del episodio. SIN intro, SIN "hola que tal", SIN "bienvenidos". Directo a la accion como Dross, Diary of a CEO, y Jordi Wild. Opciones:
a) DATO-BOMBA: "El 90% de lo que crees saber sobre [tema] esta mal. Y hoy te voy a demostrar por que."
b) PREGUNTA IMPOSIBLE DE IGNORAR: "Que harias si supieras que [premisa inquietante]? Porque resulta que es real."
c) AFIRMACION PROVOCADORA: "Preparense, porque lo que os voy a contar hoy va a cambiar como veis [algo cotidiano]. Para siempre."
d) INMERSION (estilo Dross/Iker): "Imaginate esto... [escena sensorial]. Eso paso. Y nadie sabe explicar por que."
>>> Abrir LOOP #1 (algo que se cerrara mas adelante)

ACTO 2 - CONTEXTO CON GANCHO (intercambios 4-15):
- Presentar el tema con datos sorprendentes TEMPRANO (anclar interes)
- Klaus presenta al invitado elevandolo: "Necesitaba hablar con alguien que realmente supiera de esto..."
- Primera revelacion menor (recompensa parcial)
>>> Abrir LOOP #2: "Esto conecta con algo alucinante que vamos a ver en un momento..."

ACTO 3 - INMERSION (intercambios 16-35):
- Contenido principal: explicaciones profundas con ANALOGIAS concretas
- Momento de debate/desacuerdo entre Klaus e invitado
- Cerrar LOOP #1 (recompensa de dopamina)
>>> RESET DE ATENCION a los ~12 minutos: cambiar de formato (explicacion -> anecdota, serio -> humor, dato -> opinion)
>>> Abrir LOOP #3: "Pero esto no es lo mas impresionante..."

ACTO 4 - EL PEAK (intercambios 36-45):
- El momento MAS MEMORABLE del episodio (regla Peak-End de Kahneman)
- Revelacion inesperada que CAMBIA la perspectiva
- Cerrar LOOP #2
- Reacciones GENUINAS de asombro

ACTO 5 - IMPLICACIONES (intercambios 46-55):
- "Y esto que significa para ti y para mi?"
- Conectar el tema con la vida cotidiana del oyente
- Segundo momento de debate/reflexion
- Cerrar LOOP #3
>>> Momento de humor como VALVULA DE PRESION (libera tension sin trivializar)

ACTO 6 - REFLEXION PROFUNDA (intercambios 56-65):
- Conectar el tema con algo MAS GRANDE (sociedad, humanidad, futuro)
- Klaus da su OPINION PERSONAL genuina
- Momento de vulnerabilidad: "La verdad es que yo tampoco se la respuesta a esto"

ACTO 7 - CIERRE MEMORABLE (intercambios 76-85):
- NUNCA "Bueno, pues eso ha sido todo" ni un resumen plano
- El cierre debe provocar la sensacion "ahora nunca podras ver esto igual" (tecnica Altozano/Ter)
- Opciones de cierre:
  a) REVELACION FINAL: guardar un ultimo dato sorprendente para el final
  b) PREGUNTA ABIERTA: dejar al oyente pensando durante dias
  c) FRASE PODEROSA: conclusion "tuiteable" que se pueda compartir
  d) CALLBACK AL INICIO: volver al gancho y cerrarlo con nueva perspectiva
  e) PROTOCOLO PRACTICO: 2-3 takeaways concretos que el oyente pueda aplicar HOY (estilo Huberman)
- Klaus da su OPINION PERSONAL genuina sobre todo lo que se ha hablado
- Terminar con la firma: "Nos vemos cuando nos veamos."

=== REGLAS DEL DIALOGO (TODAS OBLIGATORIAS) ===

1. {debate_style}
{question_rule}
{citation_rule}

4. NATURALIDAD ABSOLUTA - Espanol CONVERSACIONAL REAL, NO espanol de libro de texto:
   - Muletillas naturales que dan ritmo: "Pues mira...", "A ver...", "O sea...", "Es que...", "Bueno...", "Sabes?"
   - Interrupciones: "Espera espera espera, para ahi" / "Dejame que te corte un segundo"
   - Auto-correcciones: "Bueno, en realidad no es exactamente asi..." / "No, espera, lo que quiero decir es..."
   - Frases incompletas que el otro completa
   - Hesitaciones pensativas: "Hmm, a ver como te lo explico..."
   - Las respuestas NO deben ser todas de la misma longitud

5. KLAUS DA OPINIONES - No es un simple preguntador. Despues de cada respuesta:
   a) Reacciona emocionalmente (usa las reacciones del catalogo arriba)
   b) Da SU OPINION o perspectiva personal
   c) Anade contexto, conecta con otra idea, o cuenta una mini-historia
   d) LUEGO hace la siguiente pregunta
   NUNCA: pregunta -> respuesta -> pregunta -> respuesta (eso es una entrevista de trabajo, no un podcast)

6. ANTI-PATRONES (PROHIBIDO, evitar a toda costa):
   - "El Eco Amable": repetir lo que dijo el otro + "exactamente!" (al menos 30% de respuestas deben tener matiz o cuestionamiento)
   - "La Wikipedia Conversada": dos voces turnandose para leer informacion sin emocion
   - "Transiciones de Robot": "Pasemos ahora a..." / "Otro punto interesante es..." (usar transiciones organicas: la ultima frase del bloque anterior como puente)
   - "Entusiasmo Constante": todo es "increible!" y "fascinante!" sin contraste emocional
   - "Turnos Perfectos": intervenciones siempre de la misma longitud, perfectamente alternadas
   - "Cierre en Caida Libre": "Gracias por escucharnos, hasta la proxima"

7. HUMOR COMO VALVULA DE PRESION (minimo 4-5 momentos):
   Despues de bloques densos o emocionales, liberar tension SIN trivializar:
   - Comparaciones absurdas: "Eso es como si me dijeras que los peces inventaron la bicicleta"
   - Exageraciones: "Si mi abuela hubiera sabido esto, habria ganado el Nobel"
   - Ironia: "Claro, porque la comunidad cientifica es conocida por ponerse de acuerdo rapidamente..."
   - Self-deprecating: "Vale, aqui es donde demuestro que no tengo ni idea..."
   - Meta-humor: "OK, eso fue intenso. Respiren. Ya esta. Ahora sigamos."

8. LOOPS ABIERTOS (efecto Zeigarnik): abrir al menos 3 loops durante el episodio y cerrarlos gradualmente. "Esto me recuerda algo increible que descubri, pero antes dejame terminar con esto..."

9. CALLBACKS: al menos 2 referencias a algo dicho antes que cobra nuevo sentido. "Recuerdas lo que decias antes sobre X? Pues mira lo que pasa cuando..."

10. ANALOGIAS PUENTE: cada concepto abstracto necesita al menos una analogia concreta y vivida. "Basicamente es como si tu cerebro fuera un aeropuerto y..."

11. IMAGENES MENTALES: crear imagenes con las palabras. NO "fue un descubrimiento importante". SI "imaginate la cara del cientifico cuando miro los datos y se dio cuenta de que todo lo que creia estaba mal."

12. VARIEDAD EMOCIONAL: el episodio es una MONTANA RUSA. Picos de intensidad (revelaciones, sorpresas, humor) + valles de calma (reflexion, contexto). NUNCA el mismo tono durante todo el episodio.

13. Cada respuesta del invitado: MINIMO 3-4 frases largas. Cada intervencion de Klaus: sustancial (reaccion + opinion + contexto + pregunta).

14. DURACION OBLIGATORIA: entre 65 y 85 intercambios. CRITICO para 20+ minutos de audio.

15. NO uses marcadores como [PAUSA] o [MUSICA]. Solo dialogo puro.

16. Cubre TODOS los angulos: historia, ciencia actual, controversias, futuro, impacto social, datos sorprendentes.

17. MOMENTOS CLIP (generar deliberadamente 3-4 momentos "clippeables" de 30-60 segundos que funcionen SOLOS fuera de contexto):
   - "La Frase Bomba": una frase que resume un concepto complejo en una linea brutal y compartible
   - "El Dato Destructor": un dato tan impactante que la gente lo comparte diciendo "no me lo creo"
   - "La Analogia Perfecta": explica algo complejo con una comparacion tan buena que la gente dice "ahora lo entiendo"
   - Estos momentos deben poder cortarse del episodio y funcionar solos en redes sociales

18. PERSONALIDADES DIFERENCIADAS: Klaus y el invitado DEBEN tener voces linguisticas distintas. Uno mas emocional, otro mas analitico. Uno usa mas datos, otro mas anecdotas. Sin diferenciacion suena a una persona hablando consigo misma.

=== INTENCION DEL USUARIO (MUY IMPORTANTE) ===
El usuario pidio hablar de: "{topic}"
{f'Intencion: {user_intent}' if user_intent else ''}
{f'Resumen del tema: {topic_summary}' if topic_summary != topic else ''}
Tipo de tema: {topic_type}

REGLA CRITICA: El podcast DEBE hablar de lo que el usuario pidio. NO te vayas por las ramas. Cada bloque tematico debe estar DIRECTAMENTE conectado con la intencion del usuario. Si el usuario pidio hablar de "viajeros del tiempo entre nosotros", CADA parte del podcast debe conectar con eso. No te pierdas en tangentes que no tienen que ver.

{self._get_research_mode_instructions(has_research, topic_type)}

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

Genera un guion de podcast LARGO entre KLAUS (presentador veterano, carismatico, con opiniones fuertes, humor contextual y reacciones viscerales al estilo Jordi Wild + Worldcast) y {guest_name} (de {guest_country}).
Dinamica: {dynamic_desc}.

REGLAS CLAVE:
- MINIMO 55-75 intercambios. Cada intervencion LARGA (3-5 frases minimo).
- Apertura con GANCHO PROVOCATIVO (dato impactante, pregunta retadora). NUNCA "bienvenidos al podcast".
- Klaus da OPINIONES PROPIAS, usa humor, reacciona visceralmente ("No me jodas", "Para para para", "Me acabas de romper la cabeza").
- Incluye 3+ cliffhangers internos, 2+ callbacks, y variedad emocional.
- Cierre con reflexion profunda que deje pensando, NO un resumen.
- Dialogo NATURAL con interrupciones, auto-correcciones, hesitaciones.
- Debate real con desacuerdos y datos especificos.

Investigacion disponible:
{research_text[:60000]}

FORMATO OBLIGATORIO (solo esto, nada mas):
[
  {{"speaker": "KLAUS", "text": "texto aqui", "emotion": "excited"}},
  {{"speaker": "EXPERT", "text": "texto aqui", "emotion": "thoughtful"}}
]

Emociones validas: neutral, excited, thoughtful, challenging, humorous, nostalgic, surprised, skeptical
RESPONDE SOLO CON EL JSON ARRAY."""
