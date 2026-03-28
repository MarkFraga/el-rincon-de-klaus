from pydantic import BaseModel
from enum import Enum
from typing import Optional


class PodcastRequest(BaseModel):
    topic: str


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class PodcastJob(BaseModel):
    id: str
    topic: str
    agent_web: AgentStatus = AgentStatus.PENDING
    agent_academic: AgentStatus = AgentStatus.PENDING
    agent_deep: AgentStatus = AgentStatus.PENDING
    agent_organizer: AgentStatus = AgentStatus.PENDING
    audio_generation: AgentStatus = AgentStatus.PENDING
    progress_pct: int = 0
    audio_url: Optional[str] = None
    error: Optional[str] = None
    guest_name: Optional[str] = None
    guest_country: Optional[str] = None
    guest_role: Optional[str] = None


class ScriptSegment(BaseModel):
    speaker: str  # "KLAUS" or "EXPERT"
    text: str
    emotion: str = "neutral"
