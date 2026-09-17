"""Pipecat TTS service backed by edge-tts (free Microsoft Edge neural voices, incl. Urdu).

edge-tts streams MP3; PyAV (already a dependency of aiortc) decodes it incrementally so
audio reaches the shopper chunk by chunk instead of after the whole sentence.
"""

import asyncio
import re
from collections.abc import AsyncGenerator

import av
import edge_tts
import numpy as np
from loguru import logger
from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService

# The service usually answers in about a second but occasionally stalls for half a minute
# without sending anything; a fresh connection is faster than waiting.
FIRST_AUDIO_TIMEOUT_S = 4.0
NEXT_CHUNK_TIMEOUT_S = 10.0
ATTEMPTS = 2
# Arabic-script letters: a sentence written in Urdu needs an Urdu voice (an English voice returns no audio).
URDU_SCRIPT = re.compile("[\u0600-\u06FF]")


class EdgeTTSService(TTSService):
    Settings = TTSSettings
    _settings: TTSSettings

    def __init__(self, *, voice: str, urdu_voice: str | None = None, **kwargs):
        super().__init__(
            push_start_frame=True,
            push_stop_frames=True,
            settings=TTSSettings(model=None, voice=voice, language=None),
            # Pipecat gives up on a sentence after this much silence (3 s by default), which
            # dropped sentences whose first attempt stalled before the retry could answer.
            stop_frame_timeout_s=kwargs.pop("stop_frame_timeout_s", FIRST_AUDIO_TIMEOUT_S * ATTEMPTS + 1),
            **kwargs,
        )
        self._urdu_voice = urdu_voice
        self._resampler = create_stream_resampler()

    def voice_for(self, text: str) -> str:
        # Chosen per sentence rather than by a settings update: an update frame queued when the
        # shopper switches language reaches TTS after the reply it was meant for.
        return self._urdu_voice if self._urdu_voice and URDU_SCRIPT.search(text) else self._settings.voice

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        try:
            await self.start_tts_usage_metrics(text)
            for attempt in range(1, ATTEMPTS + 1):
                sent_audio = False
                stream = edge_tts.Communicate(text, self.voice_for(text)).stream()
                try:
                    decoder = av.CodecContext.create("mp3", "r")
                    while True:
                        timeout = NEXT_CHUNK_TIMEOUT_S if sent_audio else FIRST_AUDIO_TIMEOUT_S
                        try:
                            chunk = await asyncio.wait_for(anext(stream), timeout)
                        except StopAsyncIteration:
                            break
                        if chunk["type"] != "audio":
                            continue
                        for packet in decoder.parse(chunk["data"]):
                            for frame in await self._decode(decoder, packet, context_id):
                                sent_audio = True
                                yield frame
                    for frame in await self._decode(decoder, None, context_id):
                        yield frame
                    return
                except Exception as e:
                    # Retrying after audio went out would repeat the start of the sentence.
                    if sent_audio or attempt == ATTEMPTS:
                        raise
                    logger.warning(f"edge-tts attempt {attempt} failed before any audio ({e!r}); retrying")
                finally:
                    await stream.aclose()
        except Exception as e:
            yield ErrorFrame(error=f"edge-tts error: {e!r}", exception=e)
        finally:
            await self.stop_ttfb_metrics()

    async def _decode(self, decoder, packet, context_id: str) -> list[Frame]:
        frames = []
        for decoded in decoder.decode(packet):
            await self.stop_ttfb_metrics()
            samples = decoded.to_ndarray()
            # A bare mp3 CodecContext decodes to s16p, while the same mp3 opened as a container
            # gives fltp; and averaging the channels promotes either one to float64. So record
            # which scale the samples are on *before* the mean — clipping int16 samples to
            # -1.0..1.0 leaves only their sign, which is heard as a full-scale square wave.
            was_float = np.issubdtype(samples.dtype, np.floating)
            if samples.ndim > 1:
                samples = samples.mean(axis=0)
            if was_float:
                samples = samples * 32767.0
            samples = np.clip(samples, -32768, 32767).astype(np.int16)
            audio = await self._resampler.resample(samples.tobytes(), decoded.sample_rate, self.sample_rate)
            frames.append(TTSAudioRawFrame(audio=audio, sample_rate=self.sample_rate, num_channels=1,
                                           context_id=context_id))
        return frames
