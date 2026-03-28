import os
from uuid import uuid4
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse
from backend.models import PodcastRequest, PodcastJob, AgentStatus
from backend.config import OUTPUT_DIR

router = APIRouter()

# Import jobs dict from orchestrator (will be created by the other agent)
# We need a shared reference, so use a module-level dict
from backend.agents.orchestrator import jobs, generate_podcast


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/generate")
async def start_generation(req: PodcastRequest, background_tasks: BackgroundTasks):
    job_id = uuid4().hex[:8]
    jobs[job_id] = PodcastJob(id=job_id, topic=req.topic)
    background_tasks.add_task(generate_podcast, req.topic, job_id)
    return {"job_id": job_id}


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        return {"error": "Job not found"}
    return jobs[job_id].model_dump()


@router.get("/audio/{job_id}")
async def get_audio(job_id: str):
    audio_path = OUTPUT_DIR / f"{job_id}.mp3"
    if not audio_path.exists():
        return {"error": "Audio not found"}
    return FileResponse(
        path=str(audio_path),
        media_type="audio/mpeg",
        filename=f"el-rincon-de-klaus-{job_id}.mp3"
    )


@router.get("/podcasts")
async def list_podcasts():
    """List all generated podcasts with their metadata."""
    podcasts = []
    for job_id, job in jobs.items():
        if job.audio_url:
            podcasts.append({
                "id": job.id,
                "topic": job.topic,
                "audio_url": job.audio_url,
                "guest_name": job.guest_name,
                "guest_country": job.guest_country,
                "guest_role": job.guest_role,
            })
    return podcasts
