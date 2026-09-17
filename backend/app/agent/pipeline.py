"""One voice session: WebRTC audio -> Silero VAD + smart turn -> Groq Whisper -> Gemini (Groq fallback)
-> edge-tts / Kokoro -> WebRTC, with Pipecat Flows routing between specialist nodes.

UI events from tools travel to the browser as RTVI server messages shaped {type, payload}.
"""

import asyncio
import time
import uuid

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.flows import FlowManager
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    LLMFullResponseStartFrame,
    LLMRunFrame,
    LLMTextFrame,
    ManuallySwitchServiceFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.llm_switcher import LLMSwitcher
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.service_switcher import ServiceSwitcherStrategyFailover
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.utils.errors import ErrorCategory
from pipecat.workers.runner import WorkerRunner

from app import config
from app.agent import sessions
from app.agent.edge_tts_service import EdgeTTSService
from app.agent.flows import GiftFlows
from app.agent.models import kokoro_ready
from app.agent.stt import AutoLanguageGroqSTTService
from app.agent.switchers import FlushSafeLLMSwitcher, FlushSafeServiceSwitcher
from app.agent.tools import ToolContext

# Errors worth handing the conversation to the fallback LLM for; auth/bad-request errors
# already make Pipecat mark the service unusable on its own.
TRANSIENT_LLM_ERRORS = {ErrorCategory.RATE_LIMIT, ErrorCategory.QUOTA, ErrorCategory.SERVER,
                        ErrorCategory.CONNECTIVITY}
PRIMARY_LLM_COOLDOWN_S = 60
# Groq Whisper transcribes one VAD segment at a time. Pipecat's 0.2 s default split sentences at
# ordinary pauses: each fragment became its own LLM turn, and short fragments lost words
# ("under fifty dollars" came back as "dollars").
VAD_STOP_SECS = 0.6
GEMINI_FIRST_CHUNK_TIMEOUT_S = 3.0
# The re-issued request, and gaps between chunks, get this long before Gemini counts as down and
# the Groq fallback answers (Pipecat's 20 s default left the shopper in silence).
GEMINI_STREAM_IDLE_TIMEOUT_S = 8.0


class LatencyObserver(BaseObserver):
    """Per-turn latency: end of speech -> transcript -> first LLM token -> first TTS audio -> bot speaking."""

    TRACKED = (VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame, TranscriptionFrame,
               LLMFullResponseStartFrame, LLMTextFrame, TTSAudioRawFrame, BotStartedSpeakingFrame)

    def __init__(self, send):
        super().__init__()
        self._send = send
        self._seen: dict[type, int] = {}
        self._reset()

    def _reset(self):
        self.speech_end = self.transcript = self.llm_start = self.llm_first = self.tts_first = None

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if not isinstance(frame, self.TRACKED) or self._seen.get(type(frame)) == frame.id:
            return
        self._seen[type(frame)] = frame.id
        now = time.monotonic()

        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._reset()
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self.speech_end = now
        elif isinstance(frame, TranscriptionFrame) and self.speech_end:
            self.transcript = now
        elif isinstance(frame, LLMFullResponseStartFrame) and self.speech_end and not self.llm_start:
            self.llm_start = now
        elif isinstance(frame, LLMTextFrame) and self.llm_start and not self.llm_first:
            self.llm_first = now
        elif isinstance(frame, TTSAudioRawFrame) and self.llm_first and not self.tts_first:
            self.tts_first = now
        elif isinstance(frame, BotStartedSpeakingFrame) and self.speech_end:
            def ms(a, b):
                return round((b - a) * 1000) if a and b else None

            await self._send("latency", {
                "stt_ms": ms(self.speech_end, self.transcript),
                "llm_ttfb_ms": ms(self.llm_start, self.llm_first),
                "tts_ttfb_ms": ms(self.llm_first, self.tts_first),
                "total_ms": ms(self.speech_end, now),
            })
            logger.info(f"turn latency total={ms(self.speech_end, now)}ms")
            self._reset()


def build_llm():
    """Gemini first, Groq gpt-oss as fallback; either alone if only one key is configured."""
    llms = []
    if config.GOOGLE_API_KEY:
        # Free-tier Gemini usually starts streaming within 1-2 s but some requests sit for 7-10 s;
        # re-issuing a request that's silent for 3 s is faster than waiting it out.
        llms.append(GoogleLLMService(api_key=config.GOOGLE_API_KEY,
                                     settings=GoogleLLMService.Settings(model=config.GEMINI_MODEL),
                                     retry_on_timeout=True, retry_timeout_secs=GEMINI_FIRST_CHUNK_TIMEOUT_S,
                                     stream_idle_timeout_secs=GEMINI_STREAM_IDLE_TIMEOUT_S))
    if config.GROQ_API_KEY:
        llms.append(GroqLLMService(api_key=config.GROQ_API_KEY,
                                   settings=GroqLLMService.Settings(model=config.GROQ_LLM_MODEL)))
    if not llms:
        raise RuntimeError("Set GOOGLE_API_KEY and/or GROQ_API_KEY in .env")
    return llms


def build_tts() -> tuple[object, object | None]:
    """Returns (primary, edge). edge-tts by default (~1 s to first audio, has Urdu voices); Kokoro runs locally
    but needs ~3-5 s per sentence on a laptop CPU, so it is opt-in with TTS_ENGINE=kokoro."""
    edge = EdgeTTSService(voice=config.EDGE_VOICE_EN, urdu_voice=config.EDGE_VOICE_UR)
    if config.TTS_ENGINE != "kokoro":
        return edge, edge
    if not kokoro_ready():
        logger.warning("Kokoro model not downloaded (python -m scripts.download_models); using edge-tts")
        return edge, edge
    try:
        from pipecat.services.kokoro.tts import KokoroTTSService

        kokoro = KokoroTTSService(settings=KokoroTTSService.Settings(voice=config.KOKORO_VOICE))
        return kokoro, edge
    except Exception as e:  # missing model download, onnxruntime issue, ...
        logger.warning(f"Kokoro unavailable, using edge-tts: {e}")
        return edge, edge


async def run_bot(transport: BaseTransport, session_id: str | None, customer_id: str | None):
    """One conversation on an already-built transport (SmallWebRTC locally, websocket on the hosted demo)."""
    session_id = session_id or uuid.uuid4().hex
    customer_id = customer_id or "guest"
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is required for speech-to-text")

    stt = AutoLanguageGroqSTTService(api_key=config.GROQ_API_KEY,
                                     settings=AutoLanguageGroqSTTService.Settings(model=config.GROQ_STT_MODEL))

    llms = build_llm()
    llm = FlushSafeLLMSwitcher(llms=llms, strategy_type=ServiceSwitcherStrategyFailover) if len(llms) > 1 else llms[0]

    primary_tts, edge_tts = build_tts()
    tts = (FlushSafeServiceSwitcher(services=[primary_tts, edge_tts], strategy_type=ServiceSwitcherStrategyFailover)
           if primary_tts is not edge_tts else primary_tts)

    context = LLMContext()
    aggregators = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=VAD_STOP_SECS))),
    )

    pipeline = Pipeline([
        transport.input(),
        stt,
        aggregators.user(),
        llm,
        tts,
        transport.output(),
        aggregators.assistant(),
    ])

    worker: PipelineWorker | None = None

    async def emit(event_type: str, payload: dict) -> None:
        if worker is not None:
            await worker.rtvi.send_server_message({"type": event_type, "payload": payload})

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[LatencyObserver(emit)],
    )

    async def on_language_change(language: str) -> None:
        # Recognition auto-detects the language and edge-tts picks the Urdu voice from the script of
        # each sentence; only Kokoro, which has no Urdu voice, needs routing through edge-tts.
        if tts is not primary_tts:
            await worker.queue_frame(ManuallySwitchServiceFrame(service=edge_tts if language == "ur" else primary_tts))

    def user_turns() -> int:
        return sum(1 for m in context.get_messages() if isinstance(m, dict) and m.get("role") == "user")

    ctx = ToolContext(session_id=session_id, customer_id=customer_id, emit=emit,
                      on_language_change=on_language_change, user_turns_fn=user_turns)
    sessions.register(ctx)

    flows = GiftFlows(ctx)
    for service in llms:
        service.add_event_handler("on_function_calls_started",
                                  lambda _service, calls: flows.calls_started(len(calls)))
    flow_manager = FlowManager(llm=llm, context_aggregator=aggregators, worker=worker,
                               transport=transport, global_functions=flows.global_functions())

    if isinstance(llm, LLMSwitcher):
        primary, fallback = llms[0], llms[1]

        async def restore_primary():
            await asyncio.sleep(PRIMARY_LLM_COOLDOWN_S)
            await primary.set_usable(True)
            await worker.queue_frame(ManuallySwitchServiceFrame(service=primary))
            logger.info(f"{primary.name} restored as primary LLM")

        @primary.event_handler("on_error")
        async def on_primary_error(service, error):
            if error.category in TRANSIENT_LLM_ERRORS and service.is_usable:
                logger.warning(f"{service.name} {error.category}: failing over for {PRIMARY_LLM_COOLDOWN_S}s")
                await service.set_usable(False)
                asyncio.create_task(restore_primary())

        @llm.strategy.event_handler("on_service_switched")
        async def on_llm_switched(strategy, service):
            if service is fallback:
                # The failed request produced no reply; answer the same turn with the fallback.
                await worker.queue_frame(LLMRunFrame())

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        await flow_manager.initialize(flows.initial_node())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Session {session_id} disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        sessions.unregister(session_id)
