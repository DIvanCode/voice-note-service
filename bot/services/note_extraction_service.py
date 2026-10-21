from __future__ import annotations

import asyncio
from collections.abc import Callable

from bot.models.note import Note
from extractor.app.extractor import extract_text


class NoteExtractionService:
    """Temporary replacement for the future LLM/ML note extraction model.

    Until the real model is connected, the recognized text is returned as the
    note body and the remaining fields contain explicit test values. This keeps
    the complete Telegram flow usable without pretending that extraction has
    already been implemented.

    ``extract_text`` is a blocking call (HTTP request to llama.cpp that can take
    up to ``UPSTREAM_TIMEOUT`` seconds), so it is executed in a worker thread
    via ``asyncio.to_thread`` and does not block the event loop, the same way
    ``SpeechToTextService`` runs Whisper. The extraction function may be
    injected in tests to avoid calling llama.cpp.
    """

    def __init__(
        self,
        extract_fn: Callable[[str], dict[str, str | None]] = extract_text,
    ):
        self.extract_fn = extract_fn

    async def extract(self, text: str) -> Note:
        text = text.strip()
        if not text:
            raise ValueError("Transcribed text is empty")

        return await asyncio.to_thread(self._extract_sync, text)

    def _extract_sync(self, text: str) -> Note:
        result = self.extract_fn(text)

        body = "\n".join(
            f"{key}: {value}"
            for key, value in result.items()
            if value is not None
        )
        return Note(
            note=body,
            full_name="Тестовый Клиент",
            phone="+79990000000",
            topic="Тестовая тема",
        )