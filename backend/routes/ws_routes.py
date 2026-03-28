from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.ws_manager import ws_manager

router = APIRouter()


@router.websocket("/ws/progress/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    await ws_manager.connect(websocket, job_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, job_id)
    except Exception:
        ws_manager.disconnect(websocket, job_id)
