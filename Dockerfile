FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg espeak-ng && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Kokoro ONNX model (int8 quantized = 88MB, fits in 512MB RAM)
RUN mkdir -p models && python -c "\
import urllib.request; \
urllib.request.urlretrieve(\
  'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx', \
  'models/kokoro-v1.0.int8.onnx'); \
urllib.request.urlretrieve(\
  'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin', \
  'models/voices-v1.0.bin'); \
print('Model files downloaded')"

COPY . .
RUN mkdir -p output && python -c "from backend.app import app; print('OK')"

ENV PORT=10000
CMD ["sh", "-c", "exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
