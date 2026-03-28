from __future__ import annotations

import asyncio
import logging

from backend.agents.web_search_agent import WebSearchAgent
from backend.agents.academic_agent import AcademicAgent
from backend.agents.deep_research_agent import DeepResearchAgent
from backend.agents.organizer_agent import OrganizerAgent
from backend.audio.audio_pipeline import AudioPipeline
from backend.models import PodcastJob, AgentStatus
from backend.ws_manager import ws_manager

logger = logging.getLogger(__name__)

# Global jobs registry
jobs: dict[str, PodcastJob] = {}


async def generate_podcast(topic: str, job_id: str) -> None:
    """Full podcast generation pipeline: research -> script -> audio."""
    job = jobs[job_id]

    try:
        # ── Phase 1: Run 3 research agents in parallel ──────────────
        job.agent_web = AgentStatus.RUNNING
        job.agent_academic = AgentStatus.RUNNING
        job.agent_deep = AgentStatus.RUNNING
        job.progress_pct = 5

        await ws_manager.broadcast(job_id, {
            "status": "running",
            "phase": "research",
            "progress": 5,
        })

        web_agent = WebSearchAgent(job_id)
        academic_agent = AcademicAgent(job_id)
        deep_agent = DeepResearchAgent(job_id)

        results = await asyncio.gather(
            web_agent.run(topic),
            academic_agent.run(topic),
            deep_agent.run(topic),
            return_exceptions=True,
        )

        web_result = results[0] if not isinstance(results[0], Exception) else {"sources": [], "summary": ""}
        academic_result = results[1] if not isinstance(results[1], Exception) else {"papers": [], "summary": ""}
        deep_result = results[2] if not isinstance(results[2], Exception) else {"sources": [], "summary": ""}

        # Log any agent errors but continue
        for idx, label in enumerate(["web", "academic", "deep"]):
            if isinstance(results[idx], Exception):
                logger.error("Agent %s failed: %s", label, results[idx])

        job.agent_web = AgentStatus.DONE
        job.agent_academic = AgentStatus.DONE
        job.agent_deep = AgentStatus.DONE
        job.progress_pct = 50

        await ws_manager.broadcast(job_id, {
            "status": "running",
            "phase": "research_complete",
            "progress": 50,
        })

        # ── Phase 2: Organizer synthesises and creates script ───────
        job.agent_organizer = AgentStatus.RUNNING
        organizer = OrganizerAgent(job_id)
        script_result = await organizer.run(topic, web_result, academic_result, deep_result)
        job.agent_organizer = AgentStatus.DONE
        job.expert_name = script_result["expert_name"]
        job.expert_country = script_result["expert_country"]
        job.progress_pct = 70

        await ws_manager.broadcast(job_id, {
            "status": "running",
            "phase": "script_complete",
            "progress": 70,
            "expert_name": job.expert_name,
            "expert_country": job.expert_country,
        })

        # ── Phase 3: Generate audio ────────────────────────────────
        job.audio_generation = AgentStatus.RUNNING
        pipeline = AudioPipeline(job_id)
        expert_voice_id = script_result.get("expert_voice_id", "es-MX-JorgeNeural")
        expert_post_process = script_result.get("expert_post_process", None)
        audio_path = await pipeline.generate(
            script_result["script"], expert_voice_id, expert_post_process
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
