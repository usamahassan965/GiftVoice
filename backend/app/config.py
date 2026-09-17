"""Central configuration loaded from the repo-root .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
DB_PATH = DATA_DIR / "giftvoice.db"
CHROMA_DIR = DATA_DIR / "chroma"

load_dotenv(ROOT_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


GROQ_API_KEY = env("GROQ_API_KEY")
GOOGLE_API_KEY = env("GOOGLE_API_KEY")
PEXELS_API_KEY = env("PEXELS_API_KEY")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")

GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.5-flash-lite")
GROQ_LLM_MODEL = env("GROQ_LLM_MODEL", "openai/gpt-oss-120b")
GROQ_STT_MODEL = env("GROQ_STT_MODEL", "whisper-large-v3-turbo")

TTS_ENGINE = env("TTS_ENGINE", "edge")
KOKORO_VOICE = env("KOKORO_VOICE", "af_heart")
EDGE_VOICE_EN = env("EDGE_VOICE_EN", "en-US-AvaNeural")
EDGE_VOICE_UR = env("EDGE_VOICE_UR", "ur-PK-UzmaNeural")

STORE_NAME = env("STORE_NAME", "GiftVoice")
CURRENCY = env("CURRENCY", "USD")
# On a Hugging Face Space the app is its own origin, and HF exports the host name.
SPACE_HOST = env("SPACE_HOST")
FRONTEND_URL = env("FRONTEND_URL") or (f"https://{SPACE_HOST}" if SPACE_HOST else "http://localhost:3000")

TEXT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
CLIP_MODEL = "clip-ViT-B-32"

# --- Hosted demo (Hugging Face Space) -------------------------------------------------
# Local dev uses SmallWebRTC (peer-to-peer, needs UDP). A Space only exposes one HTTPS
# port, so the hosted demo streams audio over a websocket instead.
TRANSPORT = env("TRANSPORT", "smallwebrtc")
# The shared demo runs on one person's free API quota, so it caps sessions and their length.
MAX_CONCURRENT_SESSIONS = int(env("MAX_CONCURRENT_SESSIONS", "0") or 0)
SESSION_TIMEOUT_SECS = int(env("SESSION_TIMEOUT_SECS", "0") or 0)
# Next.js exports into this folder for the single-container deploy; served at / when present.
FRONTEND_DIST = ROOT_DIR / "frontend" / "out"
