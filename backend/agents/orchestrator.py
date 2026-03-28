from __future__ import annotations

import asyncio
import logging

from backend.agents.web_search_agent import WebSearchAgent
from backend.agents.academic_agent import AcademicAgent
from backend.agents.deep_research_agent import DeepResearchAgent
from backend.agents.organizer_agent import OrganizerAgent
from backend.audio.audio_pipeline import AudioPipeline
from backend.guests.guest_generator import generate_guest
from backend.models import PodcastJob, AgentStatus
from backend.ws_manager import ws_manager

logger = logging.getLogger(__name__)

# Global jobs registry
jobs: dict[str, PodcastJob] = {}


async def generate_podcast(topic: str, job_id: str) -> None:
    """Full podcast generation pipeline: research -> script -> audio."""
    job = jobs[job_id]

    try:
        # ── Phase 1: Run 3 research agents + guest generation in parallel ──
        job.agent_web = AgentStatus.RUNNING
        job.agent_academic = AgentStatus.RUNNING
        job.agent_deep = AgentStatus.RUNNING
        job.progress_pct = 5

        # Broadcast EACH agent status individually so frontend sees them all running
        await ws_manager.broadcast(job_id, {
            "agent": "web_search", "status": "running",
            "message": "Iniciando busqueda web...", "progress": 5,
        })
        await ws_manager.broadcast(job_id, {
            "agent": "academic", "status": "running",
            "message": "Iniciando busqueda academica...", "progress": 5,
        })
        await ws_manager.broadcast(job_id, {
            "agent": "deep_research", "status": "running",
            "message": "Iniciando busqueda profunda...", "progress": 5,
        })

        web_agent = WebSearchAgent(job_id)
        academic_agent = AcademicAgent(job_id)
        deep_agent = DeepResearchAgent(job_id)

        results = await asyncio.gather(
            web_agent.run(topic),
            academic_agent.run(topic),
            deep_agent.run(topic),
            generate_guest(topic),
            return_exceptions=True,
        )

        # Process results with detailed logging
        agent_labels = ["web", "academic", "deep", "guest"]
        for idx, label in enumerate(agent_labels):
            if isinstance(results[idx], Exception):
                logger.error("Agent %s FAILED: %s", label, results[idx], exc_info=results[idx])
                # Broadcast failure to frontend
                if label != "guest":
                    await ws_manager.broadcast(job_id, {
                        "agent": {"web": "web_search", "academic": "academic", "deep": "deep_research"}[label],
                        "status": "error",
                        "message": f"Error: {str(results[idx])[:100]}",
                        "progress": 0,
                    })
            else:
                logger.info("Agent %s completed successfully", label)

        web_result = results[0] if not isinstance(results[0], Exception) else {"sources": [], "summary": ""}
        academic_result = results[1] if not isinstance(results[1], Exception) else {"papers": [], "summary": ""}
        deep_result = results[2] if not isinstance(results[2], Exception) else {"sources": [], "summary": ""}

        # Log what each agent found
        web_count = len(web_result.get("sources", []))
        acad_count = len(academic_result.get("papers", []))
        deep_count = len(deep_result.get("sources", []))
        logger.info("Research results: web=%d, academic=%d, deep=%d", web_count, acad_count, deep_count)

        guest_profile = results[3] if not isinstance(results[3], Exception) else {
            "full_name": "Invitado Anonimo",
            "country": "mexico",
            "gender": "male",
            "age_range": "mid",
            "archetype": "academic_expert",
            "personality_traits": ["analitico", "curioso"],
            "connection_to_topic": f"Experto en {topic}",
            "dynamic": "guest_expert",
            "speaking_style": "Habla con precision y datos concretos",
            "voice_id": "es-MX-JorgeNeural",
            "post_process": {"pitch_shift_semitones": 0, "rasp_amount": 0.03, "warmth_boost_db": 2, "compression": True},
        }

        job.agent_web = AgentStatus.DONE
        job.agent_academic = AgentStatus.DONE
        job.agent_deep = AgentStatus.DONE
        job.progress_pct = 50

        # Broadcast done for each agent individually
        await ws_manager.broadcast(job_id, {
            "agent": "web_search", "status": "done",
            "message": f"Completado: {web_count} fuentes", "progress": 50,
        })
        await ws_manager.broadcast(job_id, {
            "agent": "academic", "status": "done",
            "message": f"Completado: {acad_count} papers", "progress": 50,
        })
        await ws_manager.broadcast(job_id, {
            "agent": "deep_research", "status": "done",
            "message": f"Completado: {deep_count} fuentes", "progress": 50,
        })

        # ── Phase 2: Organizer synthesises and creates script ───────
        job.agent_organizer = AgentStatus.RUNNING
        await ws_manager.broadcast(job_id, {
            "agent": "organizer", "status": "running",
            "message": "Organizando informacion y generando guion...", "progress": 55,
        })

        organizer = OrganizerAgent(job_id)
        script_result = await organizer.run(topic, web_result, academic_result, deep_result, guest_profile)
        job.agent_organizer = AgentStatus.DONE
        job.guest_name = script_result["guest_name"]
        job.guest_country = script_result["guest_country"]
        job.guest_role = script_result.get("guest_role", "experto")
        job.progress_pct = 70

        await ws_manager.broadcast(job_id, {
            "agent": "organizer", "status": "done",
            "message": f"Guion listo con {job.guest_name}",
            "progress": 70,
            "guest_name": job.guest_name,
            "guest_country": job.guest_country,
            "guest_role": job.guest_role,
        })

        # ── Phase 3: Generate audio ────────────────────────────────
        job.audio_generation = AgentStatus.RUNNING
        pipeline = AudioPipeline(job_id)
        guest_voice_id = script_result.get("guest_voice_id", "es-MX-JorgeNeural")
        guest_post_process = script_result.get("guest_post_process", None)
        audio_path = await pipeline.generate(
            script_result["script"], guest_voice_id, guest_post_process
        )
        job.audio_generation = AgentStatus.DONE
        job.audio_url = f"/api/audio/{job_id}"
        job.progress_pct = 100

        await ws_manager.broadcast(job_id, {
            "status": "complete",
            "audio_url": job.audio_url,
            "progress": 100,
        })

    except Exception as exc:
        logger.exception("Podcast generation failed for job %s", job_id)
        job.error = str(exc)
        job.progress_pct = -1
        await ws_manager.broadcast(job_id, {
            "status": "error",
            "error": str(exc),
        })
