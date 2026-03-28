import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.routes.podcast_routes import router as podcast_router
from backend.routes.ws_routes import router as ws_router
from backend.config import BASE_DIR

app = FastAPI(title="El Rincon de Klaus")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(podcast_router, prefix="/api")
app.include_router(ws_router)

# Mount frontend static files LAST (catch-all)
app.mount("/", StaticFiles(directory=str(BASE_DIR / "frontend"), html=True), name="frontend")
