"""Time-to-first-audio and total synthesis time for Kokoro (local) vs edge-tts.

Run from backend/:  python -m scripts.bench_tts
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipecat.frames.frames import TTSAudioRawFrame  # noqa: E402

from app import config  # noqa: E402
from app.agent.edge_tts_service import EdgeTTSService  # noqa: E402
from app.agent.models import kokoro_ready  # noqa: E402

SENTENCES = [
    "I found three lovely gardening gifts under fifty dollars.",
    "The second one, a ceramic herb planter set, arrives by Thursday if you order today.",
    "آپ کی والدہ کے لیے یہ تحفہ بہت خوبصورت رہے گا۔",
]


async def bench(name: str, service, sentences: list[str], sample_rate: int = 24000) -> None:
    service._sample_rate = sample_rate  # normally set by StartFrame
    for text in sentences:
        start = time.perf_counter()
        first = None
        audio_bytes = 0
        async for frame in service.run_tts(text, "bench"):
            if isinstance(frame, TTSAudioRawFrame):
                first = first or time.perf_counter()
                audio_bytes += len(frame.audio)
        total = time.perf_counter() - start
        audio_s = audio_bytes / 2 / sample_rate
        ttfa = f"{(first - start) * 1000:.0f} ms" if first else "no audio"
        print(f"{name:7} first audio {ttfa:>9} | total {total * 1000:5.0f} ms | {audio_s:4.1f} s audio | {text[:40]}")


async def main() -> None:
    if kokoro_ready():
        from pipecat.services.kokoro.tts import KokoroTTSService

        kokoro = KokoroTTSService(settings=KokoroTTSService.Settings(voice=config.KOKORO_VOICE))
        await bench("kokoro", kokoro, SENTENCES[:1])  # warm-up (model load, JIT)
        await bench("kokoro", kokoro, SENTENCES[:2])
    else:
        print("Kokoro model not downloaded; run python -m scripts.download_models")
    edge = EdgeTTSService(voice=config.EDGE_VOICE_EN)
    await bench("edge", edge, SENTENCES[:2])
    edge_ur = EdgeTTSService(voice=config.EDGE_VOICE_UR)
    await bench("edge-ur", edge_ur, SENTENCES[2:])


if __name__ == "__main__":
    asyncio.run(main())
