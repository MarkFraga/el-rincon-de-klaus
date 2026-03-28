import json
from typing import Dict, List
from fastapi import WebSocket


class WSManager:
    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, ws: WebSocket, job_id: str):
        await ws.accept()
        if job_id not in self.connections:
            self.connections[job_id] = []
        self.connections[job_id].append(ws)

    def disconnect(self, ws: WebSocket, job_id: str):
        if job_id in self.connections:
            self.connections[job_id] = [c for c in self.connections[job_id] if c != ws]

    async def broadcast(self, job_id: str, data: dict):
        if job_id not in self.connections:
            return
        dead = []
        for ws in self.connections[job_id]:
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, job_id)


ws_manager = WSManager()
