"""GiftVoice server: REST API, product images and WebRTC signalling for voice sessions.

Run from backend/:  uvicorn app.main:app --port 7860
"""

import asyncio
import mimetypes
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from app import config
from app.api import router
from app.db.database import init_db

# Windows' registry often lacks .webp, which would serve product photos as octet-stream.
mimetypes.add_type("image/webp", ".webp")

webrtc = SmallWebRTCRequestHandler(ice_servers=[IceServer(urls="stun:stun.l.google.com:19302")])
_bot_tasks: set[asyncio.Task] = set()
warm = asyncio.Event()


def _warm_up() -> None:
    """Load the voice stack and search models up front (~45 s cold) instead of inside the first session."""
    started = time.monotonic()
    from pipecat.utils.prewarm import warm_deferred_imports

    from app.agent import pipeline  # noqa: F401  (torch, onnx, pipecat services)
    from app.services import search

    warm_deferred_imports()
    search.warm_up()
    logger.info(f"Warm-up finished in {time.monotonic() - started:.1f}s")


async def _warm_up_in_background() -> None:
    try:
        await asyncio.to_thread(_warm_up)
    except Exception:
        logger.exception("Warm-up failed; models will load on first use")
    warm.set()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    warm_task = asyncio.create_task(_warm_up_in_background())
    yield
    warm_task.cancel()
    for task in _bot_tasks:
        task.cancel()
    await webrtc.close()


app = FastAPI(title="GiftVoice", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_URL],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=config.IMAGES_DIR), name="images")


async def _run_session(connection: SmallWebRTCConnection, request_data: dict) -> None:
    # A session arriving mid warm-up waits for it: loading models inside the session
    # starved the event loop and overran Pipecat's 20 s pipeline setup timeout.
    await warm.wait()
    from app.agent.pipeline import run_bot

    try:
        await run_bot(connection, request_data.get("session_id"), request_data.get("customer_id"))
    except Exception:
        logger.exception("Voice session crashed")


@app.post("/api/offer")
async def offer(request: Request) -> dict:
    """WebRTC offer from @pipecat-ai/small-webrtc-transport; starts one bot per new peer connection."""
    webrtc_request = SmallWebRTCRequest.from_dict(await request.json())
    request_data = webrtc_request.request_data or {}

    async def on_connection(connection: SmallWebRTCConnection):
        task = asyncio.create_task(_run_session(connection, request_data))
        _bot_tasks.add(task)
        task.add_done_callback(_bot_tasks.discard)

    return await webrtc.handle_web_request(request=webrtc_request, webrtc_connection_callback=on_connection)


@app.get("/api/ready")
def ready() -> dict:
    """False while the voice stack and search models are still loading after startup."""
    return {"ready": warm.is_set()}


@app.patch("/api/offer")
async def ice_candidate(request: SmallWebRTCPatchRequest) -> dict:
    await webrtc.handle_patch_request(request)
    return {"status": "success"}
