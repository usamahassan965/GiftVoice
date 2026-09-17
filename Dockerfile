# GiftVoice in one container: the exported Next.js UI, the FastAPI API and the voice websocket
# all behind a single HTTPS port, which is what a free Hugging Face Space gives you.
#
#   docker build -t giftvoice .
#   docker run -p 7860:7860 --env-file .env giftvoice

FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# A static export needs no Node at runtime: FastAPI serves the files and the browser talks to
# the API and the audio websocket on the same origin.
RUN NEXT_EXPORT=1 npm run build

FROM python:3.12-slim
# Spaces run the container as uid 1000, and the app writes orders to SQLite under /app.
RUN useradd -m -u 1000 user
ENV PYTHONUNBUFFERED=1 \
    HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    TRANSPORT=websocket \
    TTS_ENGINE=edge \
    MAX_CONCURRENT_SESSIONS=2 \
    SESSION_TIMEOUT_SECS=420

WORKDIR /app
# CPU-only torch: the default PyPI wheel carries CUDA and is several gigabytes.
RUN pip install --no-cache-dir --timeout 120 --retries 10 torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --timeout 120 --retries 10 -r backend/requirements.txt

COPY backend/ backend/
COPY --from=ui /ui/out frontend/out
# The seeded catalog (SQLite + Chroma + 214 product photos) is baked in: the image has no
# Pexels/Gemini keys to run the seed script with.
COPY data/catalog.zip data/
RUN python backend/scripts/unpack_catalog.py && chown -R user:user /app

USER user
# Bake the search models (bge-small + CLIP, ~600 MB) into the image so the first visitor doesn't
# wait for a download; a failure here only means they are fetched on first use instead.
RUN cd backend && python -c "from app.services import search; search.warm_up()" || true

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "7860"]
