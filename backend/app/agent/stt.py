"""Groq Whisper with language auto-detection for mixed English/Urdu shoppers.

Pipecat's GroqSTTService always sends a language, and Whisper then translates other speech
into it: Urdu said to an English-locked session arrived as English and the agent never
switched voices. Without a language Whisper keeps each segment in the language spoken, but it
often labels spoken Urdu as Hindi (the two sound nearly identical) and writes Devanagari, so
those segments are transcribed again as Urdu.
"""

from loguru import logger
from pipecat.services.groq.stt import GroqSTTService

# Whisper verbose_json reports the detected language by name.
URDU_LOOKALIKES = {"hindi", "hi"}


class AutoLanguageGroqSTTService(GroqSTTService):
    async def _transcribe(self, audio: bytes):
        response = await self._request(audio, language=None)
        if (getattr(response, "language", "") or "").lower() in URDU_LOOKALIKES:
            logger.debug(f"Whisper heard Hindi ({response.text.strip()!r}); transcribing as Urdu")
            response = await self._request(audio, language="ur")
        return response

    async def _request(self, audio: bytes, language: str | None):
        kwargs = {
            "file": ("audio.wav", audio, "audio/wav"),
            "model": self._settings.model,
            "response_format": "verbose_json",
        }
        if language:
            kwargs["language"] = language
        if self._settings.prompt is not None:
            kwargs["prompt"] = self._settings.prompt
        if self._settings.temperature is not None:
            kwargs["temperature"] = self._settings.temperature
        return await self._client.audio.transcriptions.create(**kwargs)
