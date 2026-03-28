FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg gcc g++ && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p output

# Debug: test imports one by one
RUN python -c "print('Testing imports...'); \
from fastapi import FastAPI; print('fastapi OK'); \
from pydub import AudioSegment; print('pydub OK'); \
import edge_tts; print('edge_tts OK'); \
import trafilatura; print('trafilatura OK'); \
from google import genai; print('genai OK'); \
from duckduckgo_search import DDGS; print('ddgs OK'); \
import httpx; print('httpx OK'); \
from backend.config import GEMINI_API_KEY; print('config OK'); \
from backend.app import app; print('ALL IMPORTS OK')"

ENV PORT=10000

CMD ["sh", "-c", "exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
