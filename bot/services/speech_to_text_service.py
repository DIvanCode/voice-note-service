from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class SpeechToTextService:
    """Adapter around a local OpenAI Whisper model.

    Telegram voice messages arrive as OGG/Opus bytes. Whisper accepts an audio
    file path and uses ffmpeg to decode/resample it, so the adapter writes the
    payload to a temporary ``.ogg`` file, calls ``model.transcribe(...)`` in a
    worker thread and always deletes the file afterwards.

    The model is loaded once when the service is created, not for every voice
    message. A model object may be injected in tests to avoid loading Whisper.
    """

    def __init__(self, model_name: str = "large", model: Any | None = None):
        self.model_name = model_name

        if model is not None:
            self.model = model
            return

        import whisper

        self.model = whisper.load_model(model_name)

    async def transcribe(self, audio: bytes) -> str:
        if not audio:
            raise ValueError("Audio payload is empty")

        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
                temp_file.write(audio)
                temp_path = Path(temp_file.name)

            return await asyncio.to_thread(self._transcribe_file, temp_path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _transcribe_file(self, audio_path: Path) -> str:
        result = self.model.transcribe(str(audio_path))
        text = result.get("text")

        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Whisper returned empty transcription")

        return text.strip()
