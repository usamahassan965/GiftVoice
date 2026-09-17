"""Speech services that wrap free providers: Urdu-aware Groq Whisper and edge-tts retries."""

import asyncio
from types import SimpleNamespace

from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame

from app.agent import edge_tts_service
from app.agent.edge_tts_service import EdgeTTSService
from app.agent.stt import AutoLanguageGroqSTTService


def test_stt_auto_detects_and_retries_hindi_as_urdu():
    stt = AutoLanguageGroqSTTService(api_key="test")
    requests = []

    async def create(**kwargs):
        requests.append(kwargs.get("language"))
        if kwargs.get("language") == "ur":
            return SimpleNamespace(text="میری امی کے لیے", language="urdu")
        return SimpleNamespace(text="मेरी उम्मी के लिए", language="Hindi")

    stt._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    result = asyncio.run(stt._transcribe(b"wav"))
    assert requests == [None, "ur"]  # no forced language first, Urdu only for the Hindi lookalike
    assert result.text == "میری امی کے لیے"


def test_stt_keeps_english_in_one_request():
    stt = AutoLanguageGroqSTTService(api_key="test")
    requests = []

    async def create(**kwargs):
        requests.append(kwargs.get("language"))
        return SimpleNamespace(text="Under $50.", language="English")

    stt._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    assert asyncio.run(stt._transcribe(b"wav")).text == "Under $50."
    assert requests == [None]


def _tts_frames(monkeypatch, streams):
    """Run EdgeTTSService.run_tts where each connection attempt replays the next fake stream."""
    attempts = iter(streams)

    class FakeCommunicate:
        def __init__(self, text, voice):
            self._stream = next(attempts)

        def stream(self):
            return self._stream()

    monkeypatch.setattr(edge_tts_service.edge_tts, "Communicate", FakeCommunicate)
    monkeypatch.setattr(edge_tts_service, "FIRST_AUDIO_TIMEOUT_S", 0.2)
    tts = EdgeTTSService(voice="en-US-AvaNeural")
    tts._sample_rate = 24000

    # Decoding is PyAV's job; here each MP3 chunk simply becomes one audio frame.
    monkeypatch.setattr(edge_tts_service.av.CodecContext, "create", lambda *a: SimpleNamespace(parse=lambda d: [d] if d else []))

    async def decode(decoder, packet, context_id):
        return [TTSAudioRawFrame(audio=b"\0\0", sample_rate=24000, num_channels=1, context_id=context_id)] if packet else []

    tts._decode = decode

    async def collect():
        return [f async for f in tts.run_tts("Hello there.", "ctx")]

    return asyncio.run(collect())


def test_edge_tts_retries_a_stalled_connection(monkeypatch):
    mp3 = b"mp3"

    async def stalled():
        await asyncio.sleep(5)
        yield {"type": "audio", "data": mp3}

    async def healthy():
        yield {"type": "WordBoundary"}
        yield {"type": "audio", "data": mp3}

    frames = _tts_frames(monkeypatch, [stalled, healthy])
    assert any(isinstance(f, TTSAudioRawFrame) for f in frames)
    assert not any(isinstance(f, ErrorFrame) for f in frames)


def test_edge_tts_reports_error_after_last_attempt(monkeypatch):
    async def broken():
        raise ConnectionError("no route")
        yield  # pragma: no cover

    frames = _tts_frames(monkeypatch, [broken, broken])
    assert [type(f) for f in frames] == [ErrorFrame]


def test_edge_tts_picks_urdu_voice_from_script():
    tts = EdgeTTSService(voice="en-US-AvaNeural", urdu_voice="ur-PK-UzmaNeural")
    assert tts.voice_for("Here are two gardening gifts.") == "en-US-AvaNeural"
    assert tts.voice_for("جی ہاں، میں اردو میں بات کر سکتی ہوں۔") == "ur-PK-UzmaNeural"
    assert EdgeTTSService(voice="en-US-AvaNeural").voice_for("جی ہاں") == "en-US-AvaNeural"


def test_edge_tts_waits_long_enough_for_its_retry():
    tts = EdgeTTSService(voice="en-US-AvaNeural")
    assert tts._stop_frame_timeout_s > edge_tts_service.FIRST_AUDIO_TIMEOUT_S * edge_tts_service.ATTEMPTS


def test_gemini_reissues_a_stalled_request(monkeypatch):
    from app import config
    from app.agent import pipeline

    monkeypatch.setattr(config, "GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    (gemini,) = pipeline.build_llm()
    assert gemini._retry_on_timeout
    assert gemini._retry_timeout_secs == pipeline.GEMINI_FIRST_CHUNK_TIMEOUT_S
    assert gemini._stream_idle_timeout_secs == pipeline.GEMINI_STREAM_IDLE_TIMEOUT_S


def test_edge_tts_decodes_mp3_at_its_original_level():
    """The other TTS tests stub the decoder out, so this one runs a real MP3 through it.

    PyAV's bare mp3 CodecContext returns s16p, not the fltp a container gives, and averaging
    the channels promotes both to float64 - so a conversion that assumes floats in -1..1 keeps
    only each sample's sign and the voice comes out as a full-scale square wave.
    """
    import av
    import numpy as np

    rate, amplitude = 24000, 0.5
    t = np.arange(rate) / rate
    pcm = (np.sin(2 * np.pi * 440 * t) * amplitude * 32767).astype(np.int16)

    # A bare encoder, so the bytes are the raw mp3 stream edge-tts sends, with no ID3 wrapper.
    encoder = av.CodecContext.create("mp3", "w")
    encoder.sample_rate, encoder.layout, encoder.format = rate, "mono", "fltp"
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
    source = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")
    source.sample_rate = rate
    packets = []
    for frame in resampler.resample(source) + resampler.resample(None):
        packets += encoder.encode(frame)
    packets += encoder.encode(None)
    mp3 = b"".join(bytes(p) for p in packets)

    tts = EdgeTTSService(voice="en-US-AvaNeural")
    tts._sample_rate = rate
    decoder = av.CodecContext.create("mp3", "r")

    async def collect():
        out = bytearray()
        for packet in decoder.parse(mp3):
            for frame in await tts._decode(decoder, packet, "ctx"):
                out += frame.audio
        for frame in await tts._decode(decoder, None, "ctx"):
            out += frame.audio
        return bytes(out)

    decoded = np.frombuffer(asyncio.run(collect()), dtype=np.int16).astype(np.float64) / 32768.0
    assert len(decoded) >= rate * 0.9, "the sine should survive decoding roughly intact"
    voiced = decoded[np.abs(decoded) > 1e-4]
    assert np.abs(decoded).max() < 0.95, "nothing should be pushed to full scale"
    # A sine at 0.5 has an RMS of 0.354; reduced to its sign it would be about 0.87.
    assert 0.28 < np.sqrt((voiced**2).mean()) < 0.42
