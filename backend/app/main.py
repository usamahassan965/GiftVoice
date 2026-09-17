"""GiftVoice server: REST API, product images and WebRTC signalling for voice sessions.

Run from backend/:  uvicorn app.main:app --port 7860
"""

import asyncio
import mimetypes
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from app import config
from app.api import router
from app.db.database import init_db

# Windows' registry often lacks .webp, which would serve product photos as octet-stream.
mimetypes.add_type("image/webp", ".webp")

webrtc = SmallWebRTCRequestHandler(ice_servers=[IceServer(urls="stun:stun.l.google.com:19302")])
_bot_tasks: set[asyncio.Task] = set()
_ws_sessions = 0
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


async def _run_session(transport, request_data: dict) -> None:
    # A session arriving mid warm-up waits for it: loading models inside the session
    # starved the event loop and overran Pipecat's 20 s pipeline setup timeout.
    await warm.wait()
    from app.agent.pipeline import run_bot

    try:
        await run_bot(transport, request_data.get("session_id"), request_data.get("customer_id"))
    except Exception:
        logger.exception("Voice session crashed")


@app.post("/api/offer")
async def offer(request: Request) -> dict:
    """WebRTC offer from @pipecat-ai/small-webrtc-transport; starts one bot per new peer connection."""
    webrtc_request = SmallWebRTCRequest.from_dict(await request.json())
    request_data = webrtc_request.request_data or {}

    async def on_connection(connection: SmallWebRTCConnection):
        transport = SmallWebRTCTransport(
            webrtc_connection=connection,
            params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
        )
        task = asyncio.create_task(_run_session(transport, request_data))
        _bot_tasks.add(task)
        task.add_done_callback(_bot_tasks.discard)

    return await webrtc.handle_web_request(request=webrtc_request, webrtc_connection_callback=on_connection)


@app.websocket("/ws")
async def voice_websocket(websocket: WebSocket, session_id: str = "", customer_id: str = "") -> None:
    """Audio over a websocket for the hosted demo: a Space exposes one HTTPS port, so
    SmallWebRTC's peer-to-peer UDP is not an option there."""
    global _ws_sessions
    if config.MAX_CONCURRENT_SESSIONS and _ws_sessions >= config.MAX_CONCURRENT_SESSIONS:
        # 1013 = try again later; the UI turns this into "the demo is busy right now".
        await websocket.close(code=1013, reason="The demo is busy - please try again in a minute.")
        return

    from pipecat.serializers.protobuf import ProtobufFrameSerializer
    from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

    await websocket.accept()
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
            session_timeout=config.SESSION_TIMEOUT_SECS or None,
        ),
    )

    @transport.event_handler("on_session_timeout")
    async def on_session_timeout(_transport, _websocket) -> None:
        # Closing the socket ends the pipeline through the usual disconnect path.
        logger.info(f"Demo session {session_id} hit the {config.SESSION_TIMEOUT_SECS}s limit")
        await websocket.close(code=1000, reason="Demo time limit reached.")

    _ws_sessions += 1
    try:
        await _run_session(transport, {"session_id": session_id, "customer_id": customer_id})
    finally:
        _ws_sessions -= 1


@app.get("/api/ready")
def ready() -> dict:
    """False while the voice stack and search models are still loading after startup.

    The browser also learns from here which transport to open, so one frontend build works
    both locally (WebRTC) and on the hosted demo (websocket)."""
    return {
        "ready": warm.is_set(),
        "transport": config.TRANSPORT,
        "session_limit_secs": config.SESSION_TIMEOUT_SECS or None,
        "busy": bool(config.MAX_CONCURRENT_SESSIONS and _ws_sessions >= config.MAX_CONCURRENT_SESSIONS),
    }


@app.patch("/api/offer")
async def ice_candidate(request: SmallWebRTCPatchRequest) -> dict:
    await webrtc.handle_patch_request(request)
    return {"status": "success"}


# The single-container deploy (Hugging Face Space) serves the exported Next.js app from here,
# so the browser, the REST API and the audio websocket all share one origin. Mounted last so
# it never shadows /api, /ws or /images.
if config.FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
    logger.info(f"Serving the exported frontend from {config.FRONTEND_DIST}")
