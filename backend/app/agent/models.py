"""Locations of locally run voice models."""

from pathlib import Path

# Same cache Pipecat's KokoroTTSService reads from.
KOKORO_DIR = Path.home() / ".cache" / "pipecat" / "kokoro-onnx"
_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO_FILES = [
    (f"{_RELEASE}/kokoro-v1.0.onnx", KOKORO_DIR / "kokoro-v1.0.onnx"),
    (f"{_RELEASE}/voices-v1.0.bin", KOKORO_DIR / "voices-v1.0.bin"),
]


def kokoro_ready() -> bool:
    return all(dest.exists() for _, dest in KOKORO_FILES)
