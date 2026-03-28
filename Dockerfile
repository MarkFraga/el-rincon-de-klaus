FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p output

# Render sets PORT env var; default to 10000 (Render's default)
ENV PORT=10000
EXPOSE ${PORT}

# Use shell form so $PORT is expanded at runtime
CMD sh -c "uvicorn backend.app:app --host 0.0.0.0 --port $PORT"
