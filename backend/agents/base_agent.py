from backend.ws_manager import ws_manager


class BaseAgent:
    """Abstract base class for all podcast pipeline agents."""

    def __init__(self, name: str, job_id: str):
        self.name = name
        self.job_id = job_id

    async def report(self, message: str, progress: int = 0):
        """Broadcast a progress update over the WebSocket."""
        await ws_manager.broadcast(self.job_id, {
            "agent": self.name,
            "status": "running",
            "message": message,
            "progress": progress,
        })

    async def run(self, topic: str) -> dict:
        raise NotImplementedError
